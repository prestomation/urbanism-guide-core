#!/usr/bin/env python3
"""
Count content metrics for the urbanism-guide site.

Outputs counts of guides, glossary terms, timeline entries, blog posts,
and total words/paragraphs across all content. Produces both human-readable
and machine-readable (JSON) output.
"""

import json
import re
import sys
from pathlib import Path


def count_glossary_terms(glossary_dir: Path) -> dict:
    """Count glossary terms across all category files."""
    total = 0
    by_category = {}
    for md_file in sorted(glossary_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        text = md_file.read_text()
        count = len(re.findall(r'<div class="glossary-term"', text))
        category = md_file.stem.replace("-", " ").title()
        by_category[category] = count
        total += count
    return {"total": total, "by_category": by_category}


def count_timeline_entries(timeline_path: Path) -> int:
    """Count entries in timeline.yaml without requiring PyYAML."""
    text = timeline_path.read_text()
    return len(re.findall(r"^- year:", text, re.MULTILINE))


def count_guides(guides_dir: Path) -> int:
    """Count guide pages (excluding _index.md)."""
    return sum(1 for f in guides_dir.glob("*.md") if f.name != "_index.md")


def count_blog_posts(blog_dir: Path) -> int:
    """Count blog posts (excluding _index.md)."""
    if not blog_dir.exists():
        return 0
    return sum(1 for f in blog_dir.glob("*.md") if f.name != "_index.md")


def count_external_links(repo_root: Path) -> int:
    """Count unique external URLs across content and data files."""
    markdown_link = re.compile(r'\]\((https?://(?:[^()\s]|\([^)]*\))+)\)')
    yaml_url = re.compile(r'url:\s*["\']?(https?://[^\s"\']+)["\']?')
    bare_url = re.compile(r'(?<![(\["\'])(https?://[^\s"\'<>\)\]]+)')

    skip_domains = {
        'localhost', '127.0.0.1', 'example.com', 'example.org',
    }

    unique_urls: set[str] = set()
    search_paths = [repo_root / "content", repo_root / "data"]
    extensions = {'.md', '.yaml', '.yml', '.html'}

    for search_path in search_paths:
        if not search_path.exists():
            continue
        for file_path in search_path.rglob('*'):
            if file_path.suffix not in extensions or not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding='utf-8')
            except Exception:
                continue
            for line in content.splitlines():
                urls_found: list[str] = []
                for match in markdown_link.finditer(line):
                    urls_found.append(match.group(1).rstrip('.,;:'))
                for match in yaml_url.finditer(line):
                    urls_found.append(match.group(1).rstrip('.,;:'))
                for match in bare_url.finditer(line):
                    url = match.group(1).rstrip('.,;:')
                    if not any(f.startswith(url) and f != url for f in urls_found):
                        if url not in urls_found:
                            urls_found.append(url)
                for url in urls_found:
                    if not any(d in url for d in skip_domains):
                        unique_urls.add(url)

    return len(unique_urls)


def count_words_and_paragraphs(content_dir: Path) -> dict:
    """Count total words and paragraphs across all Markdown content."""
    total_words = 0
    total_paragraphs = 0

    for md_file in content_dir.rglob("*.md"):
        text = md_file.read_text()

        # Strip YAML front matter
        text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)

        # Strip Hugo shortcodes
        text = re.sub(r"\{\{<.*?>}}", "", text)
        text = re.sub(r"\{\{%.*?%}}", "", text)

        # Strip HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Count words (split on whitespace, filter empty)
        words = [w for w in text.split() if w]
        total_words += len(words)

        # Count paragraphs: non-empty blocks separated by blank lines,
        # excluding lines that are only markdown headings or horizontal rules
        blocks = re.split(r"\n\s*\n", text)
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                continue
            # Skip pure heading lines or horizontal rules
            if re.match(r"^#{1,6}\s", stripped) and "\n" not in stripped:
                continue
            if re.match(r"^-{3,}$", stripped):
                continue
            total_paragraphs += 1

    return {"words": total_words, "paragraphs": total_paragraphs}


def main():
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    content_dir = repo_root / "content"
    glossary_dir = content_dir / "glossary"
    guides_dir = content_dir / "guides"
    blog_dir = content_dir / "blog"
    timeline_path = repo_root / "data" / "timeline.yaml"

    glossary = count_glossary_terms(glossary_dir)
    timeline = count_timeline_entries(timeline_path)
    guides = count_guides(guides_dir)
    blog_posts = count_blog_posts(blog_dir)
    text_stats = count_words_and_paragraphs(content_dir)
    external_links = count_external_links(repo_root)

    metrics = {
        "guides": guides,
        "glossary_terms": glossary["total"],
        "glossary_by_category": glossary["by_category"],
        "timeline_entries": timeline,
        "blog_posts": blog_posts,
        "total_words": text_stats["words"],
        "total_paragraphs": text_stats["paragraphs"],
        "external_links": external_links,
    }

    output_format = "text"
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        output_format = "json"

    if output_format == "json":
        print(json.dumps(metrics))
    else:
        print("Content Metrics")
        print("=" * 40)
        print(f"Guides:           {guides}")
        print(f"Glossary terms:   {glossary['total']}")
        for cat, count in glossary["by_category"].items():
            print(f"  {cat}: {count}")
        print(f"Timeline entries: {timeline}")
        print(f"Blog posts:       {blog_posts}")
        print(f"External links:   {external_links}")
        print(f"Total words:      {text_stats['words']:,}")
        print(f"Total paragraphs: {text_stats['paragraphs']:,}")


if __name__ == "__main__":
    main()
