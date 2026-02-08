#!/usr/bin/env python3
"""
Validate that timeline.yaml entries are in reverse chronological order.

This script ensures timeline entries are ordered from newest to oldest,
which is the expected format for the urbanism-guide timeline display.
"""

import sys
import yaml
from pathlib import Path


def validate_timeline(timeline_path: str) -> tuple[bool, list[str]]:
    """
    Validate timeline entries are in reverse chronological order.

    Returns:
        tuple: (is_valid, list of error messages)
    """
    errors = []

    try:
        with open(timeline_path, 'r') as f:
            entries = yaml.safe_load(f)
    except FileNotFoundError:
        return False, [f"Timeline file not found: {timeline_path}"]
    except yaml.YAMLError as e:
        return False, [f"Invalid YAML syntax: {e}"]

    if not entries:
        return False, ["Timeline file is empty"]

    if not isinstance(entries, list):
        return False, ["Timeline must be a list of entries"]

    # Check each entry has a year
    for i, entry in enumerate(entries):
        if 'year' not in entry:
            errors.append(f"Entry {i + 1} is missing 'year' field")
        elif not isinstance(entry['year'], int):
            errors.append(f"Entry {i + 1}: 'year' must be an integer, got {type(entry['year']).__name__}")

    if errors:
        return False, errors

    # Check reverse chronological order
    years = [entry['year'] for entry in entries]

    for i in range(len(years) - 1):
        if years[i] < years[i + 1]:
            entry_title = entries[i].get('title', 'Unknown')
            next_title = entries[i + 1].get('title', 'Unknown')
            errors.append(
                f"Order violation: '{entry_title}' ({years[i]}) appears before "
                f"'{next_title}' ({years[i + 1]}). "
                f"Timeline must be in reverse chronological order (newest first)."
            )

    return len(errors) == 0, errors


def main():
    # Find the timeline file relative to this script or repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    timeline_path = repo_root / "data" / "timeline.yaml"

    # Allow override via command line argument
    if len(sys.argv) > 1:
        timeline_path = Path(sys.argv[1])

    print(f"Validating timeline: {timeline_path}")

    is_valid, errors = validate_timeline(str(timeline_path))

    if is_valid:
        # Count entries for info
        with open(timeline_path, 'r') as f:
            entries = yaml.safe_load(f)
        years = [e['year'] for e in entries]
        print(f"Timeline is valid: {len(entries)} entries, {max(years)}-{min(years)}")
        sys.exit(0)
    else:
        print("Timeline validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
