#!/usr/bin/env python3
"""
CLI tool to search Polymarket using the public-search endpoint with category filtering.

This is a convenience wrapper around the PolymarketClient.search_events_by_category method.

Usage:
    python scripts/search_polymarket_by_category.py --keyword "nvidia" --category "finance"
    python scripts/search_polymarket_by_category.py --keyword "bitcoin" --category "crypto" --limit 5
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.polymarket.client import PolymarketClient


# Category mapping
CATEGORIES = {
    "finance": {"id": "120", "label": "Finance"},
    "crypto": {"id": "21", "label": "Crypto"},
    "politics": {"id": "2", "label": "Politics"},
    "tech": {"id": "1401", "label": "Tech"},
    "business": {"id": "107", "label": "Business"},
    "sports": {"id": "5", "label": "Sports"},
}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Search Polymarket events by keyword and filter by category"
    )
    parser.add_argument(
        "--keyword",
        required=True,
        help="Search query string (e.g., 'nvidia', 'bitcoin')"
    )
    parser.add_argument(
        "--category",
        choices=list(CATEGORIES.keys()),
        help=f"Category to filter by. Options: {', '.join(CATEGORIES.keys())}"
    )
    parser.add_argument(
        "--tag-id",
        help="Filter by tag ID directly (e.g., '120' for Finance)"
    )
    parser.add_argument(
        "--tag-label",
        help="Filter by tag label directly (e.g., 'finance'), case-insensitive"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10)"
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Include closed markets in results"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Determine tag_id and tag_label
    tag_id = args.tag_id
    tag_label = args.tag_label

    if args.category:
        category_info = CATEGORIES[args.category]
        tag_id = tag_id or category_info["id"]
        tag_label = tag_label or category_info["label"].lower()

    # Search using the client
    client = PolymarketClient()
    events = client.search_events_by_category(
        keyword=args.keyword,
        tag_id=tag_id,
        tag_label=tag_label,
        limit=args.limit,
        include_closed=args.include_closed
    )

    # Parse events
    parsed_events = [client.parse_event_data(e) for e in events]

    # Output results
    if args.json:
        result = {
            "keyword": args.keyword,
            "category": args.category,
            "tag_filter": {},
            "results_found": len(parsed_events),
            "events": parsed_events
        }
        if tag_id:
            result["tag_filter"]["id"] = tag_id
        if tag_label:
            result["tag_filter"]["label"] = tag_label

        print(json.dumps(result, indent=2))
    else:
        print_formatted_results(args.keyword, args.category, parsed_events)


def print_formatted_results(keyword: str, category: str, events: list):
    """Print results in a human-readable format."""
    print(f"\n{'='*80}")
    print(f"Search Results for: {keyword}")

    if category:
        print(f"Category: {category.title()}")

    print(f"Results Found: {len(events)}")
    print(f"{'='*80}\n")

    if len(events) == 0:
        print("No matching events found.\n")
        return

    for i, event in enumerate(events, 1):
        print(f"{i}. {event['title']}")
        print(f"   Volume: ${event['volume']:,.2f}")
        if event['url']:
            print(f"   URL: {event['url']}")
        if event['tags']:
            print(f"   Tags: {', '.join(event['tags'][:5])}")
        if event['closed']:
            print(f"   Status: CLOSED")
        print()


if __name__ == "__main__":
    main()
