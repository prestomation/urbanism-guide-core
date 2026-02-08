#!/usr/bin/env python3
"""
Check for broken external links in content files.

Detects both HTTP 404 responses and soft 404s (HTTP 200 with "Page Not Found" content).
Uses concurrent requests for faster checking.
"""

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
}


def find_external_urls(repo_root: Path) -> dict[str, list[tuple[int, str]]]:
    """
    Find all external URLs in the repository.

    Returns:
        dict mapping file paths to list of (line_number, url) tuples
    """
    # Two patterns to catch URLs:
    # 1. Markdown links: [text](url) - handles URLs with balanced parens like (a-z)
    # 2. YAML urls: url: "https://..." - captures URL inside quotes
    # 3. Bare URLs ending at whitespace
    # For markdown, match URL chars including balanced parens: (text) groups
    markdown_link = re.compile(r'\]\((https?://(?:[^()\s]|\([^)]*\))+)\)')
    yaml_url = re.compile(r'url:\s*["\']?(https?://[^\s"\']+)["\']?')
    bare_url = re.compile(r'(?<![(\["\'])(https?://[^\s"\'<>\)\]]+)')
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
            with urlopen(req, timeout=30) as response:
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
                        if f'<title>{pattern}' in content or \
                           f'<h1>{pattern}' in content or \
                           f'<h1 class' in content and pattern in content[:5000]:
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
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return False, f"Connection error: {e.reason}"

        except Exception as e:
            return False, f"Error: {str(e)}"

    return False, "Max retries exceeded"


def main():
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    print("Checking external links for broken URLs...")
    print()

    # Find all URLs
    url_map = find_external_urls(repo_root)

    if not url_map:
        print("No external URLs found in the repository.")
        sys.exit(0)

    # Deduplicate URLs while tracking their locations
    unique_urls: dict[str, list[tuple[str, int]]] = {}
    for file_path, urls in url_map.items():
        for line_num, url in urls:
            if url not in unique_urls:
                unique_urls[url] = []
            unique_urls[url].append((file_path, line_num))

    print(f"Found {len(unique_urls)} unique external URLs across {len(url_map)} files")
    print(f"Checking with {MAX_WORKERS} concurrent workers...")
    print()

    # Check URLs concurrently
    broken_links = []
    checked = 0
    total = len(unique_urls)

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

            if not is_valid:
                broken_links.append((url, error, locations))
                print(f"  [{checked}/{total}] BROKEN: {display_url}")
                print(f"           {error}")
            else:
                print(f"  [{checked}/{total}] OK: {display_url}")

    print()

    # Report results
    if broken_links:
        print("=" * 60)
        print(f"BROKEN LINKS FOUND: {len(broken_links)}")
        print("=" * 60)
        print()

        for url, error, locations in broken_links:
            print(f"URL: {url}")
            print(f"Error: {error}")
            print("Found in:")
            for file_path, line_num in locations:
                print(f"  - {file_path}:{line_num}")
            print()

        sys.exit(1)
    else:
        print(f"All {len(unique_urls)} external links are valid!")
        sys.exit(0)


if __name__ == "__main__":
    main()
