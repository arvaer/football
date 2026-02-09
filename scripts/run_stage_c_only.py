#!/usr/bin/env python3
"""Run only Stage C on existing Stage A/B data.

This script reads existing league tier data and enriches it with club statistics.

Usage:
    python scripts/run_stage_c_only.py <input_jsonl> [--limit N] [--concurrent N]
    
Example:
    python scripts/run_stage_c_only.py data/extracted/league_index_rows_2026-02-08.jsonl --limit 10
"""

import asyncio
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.workers.league_tier_clubs_extractor import (
    enrich_competitions_batch,
    write_clubs_enriched_jsonl,
    generate_stage_c_report,
)
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


def load_jsonl(input_path: Path) -> list:
    """Load JSONL file into list of dicts."""
    rows = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


async def main():
    parser = argparse.ArgumentParser(description='Run Stage C club extraction')
    parser.add_argument('input_file', help='Input JSONL file from Stage A/B')
    parser.add_argument('--limit', type=int, help='Limit to first N competitions')
    parser.add_argument('--concurrent', type=int, default=3, help='Max concurrent requests (default: 3)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between batches in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
    
    print("\n" + "="*80)
    print("STAGE C: Club Statistics Extraction")
    print("="*80)
    
    # Load input data
    print(f"\nLoading from: {input_path}")
    all_rows = load_jsonl(input_path)
    print(f"Loaded {len(all_rows)} competitions")
    
    # Apply limit if specified
    if args.limit:
        rows_to_process = all_rows[:args.limit]
        print(f"Limiting to first {args.limit} competitions")
    else:
        rows_to_process = all_rows
        print(f"\nWARNING: Processing ALL {len(all_rows)} competitions")
        print(f"Estimated time: ~{len(all_rows) * (args.delay + 0.5) / 60:.1f} minutes")
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return 0
    
    print(f"\nSettings:")
    print(f"  Concurrent requests: {args.concurrent}")
    print(f"  Delay between batches: {args.delay}s")
    print(f"  Competitions to process: {len(rows_to_process)}")
    
    # Run Stage C
    start_time = datetime.utcnow()
    print(f"\nStarting extraction at {start_time.strftime('%H:%M:%S')}...\n")
    
    enriched_rows = await enrich_competitions_batch(
        rows_to_process,
        max_concurrent=args.concurrent,
        delay_between=args.delay
    )
    
    # Write output
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    output_dir = Path('data/extracted')
    output_path = output_dir / f'league_clubs_enriched_{date_str}.jsonl'
    
    write_clubs_enriched_jsonl(output_path, enriched_rows)
    
    # Generate report
    report = generate_stage_c_report(enriched_rows)
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*80)
    print("STAGE C COMPLETE")
    print("="*80)
    print(f"Duration: {duration:.2f}s ({duration/60:.1f} minutes)")
    print(f"\nResults:")
    print(f"  Competitions processed: {report['total_competitions']}")
    print(f"  Successful: {report['successful_extractions']}")
    print(f"  Failed: {report['failed_extractions']}")
    print(f"  Success rate: {report['success_rate']}%")
    print(f"\nClubs:")
    print(f"  Total clubs extracted: {report['total_clubs_extracted']}")
    print(f"  Competitions with summary: {report['competitions_with_summary']}")
    print(f"\nBy tier:")
    for tier, stats in report['by_tier'].items():
        print(f"  Tier {tier}: {stats['competitions']} comps, "
              f"{stats['total_clubs']} clubs "
              f"(avg {stats['avg_clubs_per_competition']}/comp)")
    print(f"\nOutput: {output_path}")
    print("="*80 + "\n")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
