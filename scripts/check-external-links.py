#!/usr/bin/env python3
"""
Resilient external link checker with state tracking.

Detects both HTTP 404 responses and soft 404s (HTTP 200 with "Page Not Found"
content). Uses concurrent requests for faster checking.

Key behavior:
  - **New links** (added in the current diff or absent from prior state) must
    be reachable on the very first check.  A failure is an immediate build
    error so broken URLs never enter the codebase.
  - **Existing links** are allowed to fail transiently.  Only after N
    consecutive CI failures (default 3) does the build break.
  - State is persisted to a JSON file between runs so the failure counter
    survives across builds.

Usage:
  # Basic (no state, all failures are immediate — legacy behavior)
  python3 scripts/check-external-links.py

  # With state tracking (recommended in CI)
  python3 scripts/check-external-links.py \\
      --state-file .link-state.json \\
      --threshold 3

  # With git-diff awareness for PR builds
  python3 scripts/check-external-links.py \\
      --state-file .link-state.json \\
      --threshold 3 \\
      --diff-base origin/main
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

MAX_WORKERS = 10

# Domains to skip (internal, always valid, or known to block bots)
SKIP_DOMAINS = {
    'localhost',
    '127.0.0.1',
    'example.com',
    'example.org',
    # GitHub - their bot detection causes false positives
    'github.com',
    'raw.githubusercontent.com',
    # Social media sites that block bots
    'twitter.com',
    'x.com',
    'facebook.com',
    'linkedin.com',
    # Org sites that block automated requests (503)
    'amtrak.com',
    # 'commuteseattle.com',  # Example: Seattle-specific
    # 'urbanleague.org',  # Example: Seattle-specific
    # 'feetfirst.org',  # Example: Seattle-specific
}


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------

def find_external_urls(repo_root: Path) -> dict[str, list[tuple[int, str]]]:
    """
    Find all external URLs in the repository.

    Returns:
        dict mapping file paths to list of (line_number, url) tuples
    """
    # Two patterns to catch URLs:
    # 1. Markdown links: [text](url) - handles URLs with balanced parens like (a-z)
    # 2. YAML urls: url: "https://..." - captures URL inside quotes
    # 3. Bare URLs (e.g. in YAML comments) - also handles balanced parens like (a-z)
    # For markdown, match URL chars including balanced parens: (text) groups
    markdown_link = re.compile(r'\]\((https?://(?:[^()\s]|\([^)]*\))+)\)')
    yaml_url = re.compile(r'url:\s*["\']?(https?://[^\s"\']+)["\']?')
    # Handles balanced parens so URLs like /codes-we-enforce-(a-z)/foo are not truncated
    bare_url = re.compile(r'(?<![(\["\'])(https?://(?:[^\s"\'<>()\[\]]|\([^\s"\'<>()\[\]]*\))+)')
    results = {}

    # Search in content and data directories
    search_paths = [
        repo_root / "content",
        repo_root / "data",
    ]

    extensions = {'.md', '.yaml', '.yml', '.html'}

    for search_path in search_paths:
        if not search_path.exists():
            continue

        for file_path in search_path.rglob('*'):
            if file_path.suffix not in extensions:
                continue
            if not file_path.is_file():
                continue

            try:
                content = file_path.read_text(encoding='utf-8')
            except Exception:
                continue

            file_urls = []
            for line_num, line in enumerate(content.splitlines(), 1):
                urls_found = []
                # Try markdown links first (highest priority, captures full URL in parens)
                for match in markdown_link.finditer(line):
                    urls_found.append(match.group(1).rstrip('.,;:'))
                # Try YAML url fields
                for match in yaml_url.finditer(line):
                    urls_found.append(match.group(1).rstrip('.,;:'))
                # Fall back to bare URLs for anything not caught by markdown/yaml
                for match in bare_url.finditer(line):
                    url = match.group(1).rstrip('.,;:')
                    # Skip if this URL is a prefix of an already-found URL
                    # (means markdown pattern got the full URL with parens)
                    if not any(found_url.startswith(url) and found_url != url for found_url in urls_found):
                        # Also skip if already found
                        if url not in urls_found:
                            urls_found.append(url)

                for url in urls_found:
                    # Skip internal/problematic domains
                    if not should_skip_url(url):
                        file_urls.append((line_num, url))

            if file_urls:
                rel_path = str(file_path.relative_to(repo_root))
                results[rel_path] = file_urls

    return results


def should_skip_url(url: str) -> bool:
    """Check if URL should be skipped based on domain."""
    for domain in SKIP_DOMAINS:
        if domain in url:
            return True
    return False


# ---------------------------------------------------------------------------
# Git diff detection
# ---------------------------------------------------------------------------

def get_diff_added_urls(repo_root: Path, diff_base: str) -> set[str]:
    """
    Return the set of URLs that appear in *added* lines relative to diff_base.

    Only looks at content/ and data/ files with relevant extensions.
    """
    # Handles balanced parens so URLs like /codes-we-enforce-(a-z)/foo are not truncated
    url_pattern = re.compile(r'https?://(?:[^\s"\'<>()\[\]]|\([^\s"\'<>()\[\]]*\))+')
    added_urls: set[str] = set()

    try:
        result = subprocess.run(
            ['git', 'diff', '--unified=0', '--diff-filter=ACMR',
             diff_base, '--', 'content/', 'data/'],
            capture_output=True, text=True, cwd=repo_root, timeout=30,
        )
        if result.returncode != 0:
            print(f"WARNING: git diff failed ({result.stderr.strip()}); "
                  f"treating all links as new")
            return set()  # empty → caller falls back to "all are new"
    except Exception as exc:
        print(f"WARNING: git diff failed ({exc}); treating all links as new")
        return set()

    for line in result.stdout.splitlines():
        if not line.startswith('+') or line.startswith('+++'):
            continue
        for match in url_pattern.finditer(line):
            url = match.group(0).rstrip('.,;:')
            if not should_skip_url(url):
                added_urls.add(url)

    return added_urls


# ---------------------------------------------------------------------------
# URL checking
# ---------------------------------------------------------------------------

def check_url(url: str, retries: int = 2) -> tuple[bool, str]:
    """
    Check if a URL is valid (not a 404 or soft 404).

    Returns:
        tuple: (is_valid, error_message or empty string)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=45) as response:
                content = response.read().decode('utf-8', errors='ignore')

                # Check for soft 404 indicators in the page content
                soft_404_patterns = [
                    'Page Not Found',
                    'page not found',
                    '404 - Not Found',
                    "Sorry, we couldn't find",
                    'This page doesn\'t exist',
                    'Nothing was found',
                    'Oops! That page can\'t be found',
                ]

                for pattern in soft_404_patterns:
                    if pattern in content:
                        # Check if it's in the title or main content area
                        # to avoid false positives from sidebar/footer text
                        if (f'<title>{pattern}' in content or
                                f'<h1>{pattern}' in content or
                                (f'<h1 class' in content and pattern in content[:5000])):
                            return False, f"Soft 404 detected (page contains '{pattern}')"

                return True, ""

        except HTTPError as e:
            if e.code == 404:
                return False, "HTTP 404 Not Found"
            elif e.code == 403:
                # Some sites block bots - treat as OK
                return True, ""
            elif e.code in (406, 429, 503):  # Not acceptable, rate limited, or unavailable
                if attempt < retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return False, f"HTTP {e.code} (after {retries + 1} attempts)"
            else:
                return False, f"HTTP {e.code}"

        except URLError as e:
            # Retry SSL certificate errors with a relaxed context.
            # Some .gov sites have misconfigured certificate chains;
            # we only need to confirm the page exists, not exchange secrets.
            # Note: CERT_NONE is intentional here — this is a *link existence*
            # check, not a security-sensitive connection. The fallback is only
            # triggered after a certificate verification failure, and only for
            # that specific URL on that specific retry attempt.
            if 'CERTIFICATE_VERIFY_FAILED' in str(e.reason):
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE  # nosec B501 — link existence check only
                    req2 = Request(url, headers=headers)
                    with urlopen(req2, timeout=45, context=ctx) as response:  # nosec B310
                        response.read()
                    return True, ""
                except Exception:
                    pass  # Fall through to normal retry/failure logic

            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return False, f"Connection error: {e.reason}"

        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return False, f"Error: {str(e)}"

    return False, "Max retries exceeded"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state(state_path: Path) -> dict:
    """Load the previous link-check state from disk."""
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state_path: Path, state: dict) -> None:
    """Persist the updated state to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# GitHub Actions summary
# ---------------------------------------------------------------------------

def _write_github_summary(
    summary_path: str,
    broken_new: list,
    broken_existing: list,
    warned: list,
    threshold: int,
    total: int,
) -> None:
    """Append a Markdown summary to $GITHUB_STEP_SUMMARY."""
    lines: list[str] = []

    ok_count = total - len(broken_new) - len(broken_existing) - len(warned)

    if not broken_new and not broken_existing:
        lines.append(f"### :white_check_mark: All {ok_count} external links OK")
        if warned:
            lines.append("")
            lines.append(f"{len(warned)} link(s) warned (below "
                         f"{threshold}-failure threshold).")
    else:
        lines.append("### :x: External link check failed")
        lines.append("")

    if broken_new:
        lines.append(f"#### New links that failed ({len(broken_new)})")
        lines.append("")
        lines.append("> New links must pass on the first check. "
                     "Fix the URL or verify the site is reachable.")
        lines.append("")
        lines.append("| URL | Error | Locations |")
        lines.append("|-----|-------|-----------|")
        for url, error, locations in broken_new:
            locs = ", ".join(f"`{f}:{ln}`" for f, ln in locations)
            lines.append(f"| {url} | {error} | {locs} |")
        lines.append("")

    if broken_existing:
        lines.append(f"#### Existing links that exceeded {threshold} "
                     f"consecutive failures ({len(broken_existing)})")
        lines.append("")
        lines.append("> These links were already in the codebase but have "
                     f"failed {threshold}+ consecutive CI runs.")
        lines.append("")
        lines.append("| URL | Error | Failures | Locations |")
        lines.append("|-----|-------|----------|-----------|")
        for url, error, locations, count in broken_existing:
            locs = ", ".join(f"`{f}:{ln}`" for f, ln in locations)
            lines.append(f"| {url} | {error} | {count}/{threshold} | {locs} |")
        lines.append("")

    if warned:
        lines.append(f"<details><summary>{len(warned)} warned link(s) "
                     f"(below threshold)</summary>")
        lines.append("")
        lines.append("| URL | Error | Failures |")
        lines.append("|-----|-------|----------|")
        for url, error, locations, count in warned:
            lines.append(f"| {url} | {error} | {count}/{threshold} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    try:
        with open(summary_path, "a") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass  # Non-critical; don't break the build over summary output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Check external links with optional state tracking.")
    parser.add_argument(
        '--state-file', type=Path, default=None,
        help='Path to the JSON state file for tracking consecutive failures.')
    parser.add_argument(
        '--threshold', type=int, default=3,
        help='Number of consecutive failures before an existing link fails '
             'the build (default: 3).')
    parser.add_argument(
        '--diff-base', type=str, default=None,
        help='Git ref to diff against (e.g. origin/main). URLs that appear '
             'only in added lines are treated as new and must pass immediately.')
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    use_state = args.state_file is not None
    threshold = args.threshold

    print("Checking external links for broken URLs...")
    if use_state:
        print(f"  State file: {args.state_file}")
        print(f"  Failure threshold for existing links: {threshold}")
    if args.diff_base:
        print(f"  Diff base: {args.diff_base}")
    print()

    # ---- Load previous state ----
    state = load_state(args.state_file) if use_state else {}

    # ---- Identify newly-added URLs via git diff ----
    diff_added_urls: set[str] | None = None
    if args.diff_base:
        diff_added_urls = get_diff_added_urls(repo_root, args.diff_base)
        if diff_added_urls:
            print(f"Detected {len(diff_added_urls)} URLs in added lines "
                  f"(will require immediate pass)")
        else:
            print("No new URLs detected in diff (or diff unavailable)")
        print()

    # ---- Find all URLs ----
    url_map = find_external_urls(repo_root)

    if not url_map:
        print("No external URLs found in the repository.")
        if use_state:
            save_state(args.state_file, {})
        sys.exit(0)

    # Deduplicate URLs while tracking their locations
    unique_urls: dict[str, list[tuple[str, int]]] = {}
    for file_path, urls in url_map.items():
        for line_num, url in urls:
            if url not in unique_urls:
                unique_urls[url] = []
            unique_urls[url].append((file_path, line_num))

    print(f"Found {len(unique_urls)} unique external URLs across "
          f"{len(url_map)} files")
    print(f"Checking with {MAX_WORKERS} concurrent workers...")
    print()

    # ---- Check URLs concurrently ----
    broken_new: list[tuple[str, str, list[tuple[str, int]]]] = []
    broken_existing: list[tuple[str, str, list[tuple[str, int]], int]] = []
    warned: list[tuple[str, str, list[tuple[str, int]], int]] = []
    checked = 0
    total = len(unique_urls)

    now = datetime.now(timezone.utc).isoformat()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(check_url, url): (url, locations)
            for url, locations in unique_urls.items()
        }

        for future in as_completed(future_to_url):
            url, locations = future_to_url[future]
            checked += 1
            display_url = url[:70] + "..." if len(url) > 70 else url

            is_valid, error = future.result()

            if is_valid:
                # Reset failure counter on success
                if use_state and url in state:
                    del state[url]
                print(f"  [{checked}/{total}] OK: {display_url}")
                continue

            # ---- Link is broken ----

            # Determine whether this URL is "new"
            is_new_url = False
            if not use_state:
                # No state tracking → every broken link is treated as fatal
                is_new_url = True
            elif diff_added_urls is not None and url in diff_added_urls:
                # Appears in the git diff as an added line
                is_new_url = True
            elif diff_added_urls is None and url not in state:
                # No diff info available AND never tracked in state —
                # only treat as new when we have no diff to consult
                # (local runs without --diff-base).  When --diff-base
                # is provided, the diff is the source of truth for
                # "new"; URLs simply absent from state are seeded into
                # the failure counter instead.
                is_new_url = True

            if is_new_url:
                broken_new.append((url, error, locations))
                print(f"  [{checked}/{total}] BROKEN (new): {display_url}")
                print(f"           {error}")
            else:
                # Existing link — increment failure counter
                prev = state.get(url, {})
                consecutive = prev.get('consecutive_failures', 0) + 1
                state[url] = {
                    'consecutive_failures': consecutive,
                    'first_failure': prev.get('first_failure', now),
                    'last_failure': now,
                    'last_error': error,
                }

                if consecutive >= threshold:
                    broken_existing.append(
                        (url, error, locations, consecutive))
                    print(f"  [{checked}/{total}] BROKEN ({consecutive}/"
                          f"{threshold}): {display_url}")
                    print(f"           {error}")
                else:
                    warned.append((url, error, locations, consecutive))
                    print(f"  [{checked}/{total}] WARN ({consecutive}/"
                          f"{threshold}): {display_url}")
                    print(f"           {error}")

    # ---- Prune URLs from state that no longer exist in the repo ----
    if use_state:
        stale_keys = [u for u in state if u not in unique_urls]
        for key in stale_keys:
            del state[key]
        save_state(args.state_file, state)
        print()
        print(f"State saved to {args.state_file} "
              f"({len(state)} URLs with active failure counters)")

    print()

    # ---- Report ----
    has_failures = bool(broken_new or broken_existing)

    if warned:
        print("=" * 60)
        print(f"WARNINGS: {len(warned)} existing link(s) failing "
              f"(below threshold)")
        print("=" * 60)
        print()
        for url, error, locations, count in warned:
            print(f"  URL: {url}")
            print(f"  Error: {error}")
            print(f"  Consecutive failures: {count}/{threshold}")
            print(f"  Found in:")
            for file_path, line_num in locations:
                print(f"    - {file_path}:{line_num}")
            print()

    if broken_new:
        print("=" * 60)
        print(f"FAILURES: {len(broken_new)} newly added broken link(s)")
        print("=" * 60)
        print()
        for url, error, locations in broken_new:
            print(f"  URL: {url}")
            print(f"  Error: {error}")
            print(f"  Found in:")
            for file_path, line_num in locations:
                print(f"    - {file_path}:{line_num}")
            print()

    if broken_existing:
        print("=" * 60)
        print(f"FAILURES: {len(broken_existing)} existing link(s) exceeded "
              f"failure threshold ({threshold})")
        print("=" * 60)
        print()
        for url, error, locations, count in broken_existing:
            print(f"  URL: {url}")
            print(f"  Error: {error}")
            print(f"  Consecutive failures: {count}")
            print(f"  Found in:")
            for file_path, line_num in locations:
                print(f"    - {file_path}:{line_num}")
            print()

    # ---- GitHub Actions summary ----
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        _write_github_summary(
            summary_path, broken_new, broken_existing, warned, threshold,
            total)

    if has_failures:
        parts = []
        if broken_new:
            parts.append(f"{len(broken_new)} newly added link(s) "
                         f"(new links must pass immediately)")
        if broken_existing:
            parts.append(f"{len(broken_existing)} existing link(s) "
                         f"exceeded {threshold} consecutive failures")
        print(f"BUILD FAILED: {' + '.join(parts)}")
        sys.exit(1)
    else:
        ok_count = total - len(warned)
        print(f"All {ok_count} external links are valid"
              f"{f' ({len(warned)} warned)' if warned else ''}!")
        sys.exit(0)


if __name__ == "__main__":
    main()
