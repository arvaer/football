#!/usr/bin/env python3
"""
Enrich player profile JSONL files with market value history from tmapi-alpha.

Reads player profiles from extracted/*.jsonl files, fetches market value history
from the Transfermarkt API, and writes enriched profiles to a new file.
"""

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from tqdm import tqdm


API_TMPL = "https://tmapi-alpha.transfermarkt.technology/player/{player_id}/market-value-history"

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; market-value-bot/0.1; +https://example.com/bot)",
}


def fetch_market_value_history(player_id: int, timeout: float = 20.0) -> Dict[str, Any]:
    """Fetch market value history from API."""
    url = API_TMPL.format(player_id=player_id)
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalize_mv_points(player_id: int, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert the API payload into canonical market value rows.
    
    Args:
        player_id: Transfermarkt player ID
        payload: Raw API response
        
    Returns:
        List of normalized market value data points
    """
    rows: List[Dict[str, Any]] = []

    # Extract the history array from the API response
    # Expected structure: payload["data"]["history"] = [...]
    data = payload.get("data", {})
    history = data.get("history", [])
    
    if not history:
        return rows

    for entry in history:
        # Each entry has structure:
        # {
        #   "playerId": "513245",
        #   "clubId": "8815",
        #   "age": 18,
        #   "marketValue": {
        #     "value": 50000,
        #     "currency": "EUR",
        #     "determined": "2018-12-21"
        #   }
        # }
        market_value = entry.get("marketValue", {})
        
        value = market_value.get("value")
        currency = market_value.get("currency", "EUR")
        date = market_value.get("determined")
        club_id = entry.get("clubId")

        if date is None or value is None:
            continue

        rows.append(
            {
                "value": int(value),
                "currency": currency,
                "date": str(date),
                "club": club_id,
            }
        )

    return rows


def polite_sleep(min_s: float = 0.5, max_s: float = 1.5) -> None:
    """Sleep for a random duration to be polite to API."""
    time.sleep(random.uniform(min_s, max_s))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read all records from a JSONL file."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    """Write records to a JSONL file."""
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def enrich_player_profile(profile: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """
    Enrich a single player profile with market value history.
    
    Args:
        profile: Original player profile record
        verbose: Print debug information
        
    Returns:
        Enriched profile with market_values populated
    """
    # Get player ID from the profile
    player_tm_id = None
    
    # Try different locations for the player ID
    if "data" in profile and "player" in profile["data"]:
        player_tm_id = profile["data"]["player"].get("tm_id")
    elif "players" in profile and len(profile["players"]) > 0:
        player_tm_id = profile["players"][0].get("tm_id")
    
    if not player_tm_id:
        if verbose:
            print(f"⚠️  No player ID found in profile")
        return profile
    
    # Skip if market_values is already populated
    existing_mvs = profile.get("data", {}).get("market_values", [])
    if existing_mvs and any(mv.get("value") is not None for mv in existing_mvs):
        if verbose:
            print(f"✓ Player {player_tm_id} already has market values, skipping")
        return profile
    
    try:
        # Fetch market value history
        if verbose:
            print(f"📡 Fetching market values for player {player_tm_id}...")
        
        payload = fetch_market_value_history(int(player_tm_id))
        market_values = normalize_mv_points(int(player_tm_id), payload)
        
        # Update the profile
        if "data" not in profile:
            profile["data"] = {}
        profile["data"]["market_values"] = market_values
        
        if verbose:
            print(f"✓ Added {len(market_values)} market value points for player {player_tm_id}")
        
        return profile
        
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"⚠️  Failed to fetch market values for player {player_tm_id}: {e}")
        return profile
    except Exception as e:
        if verbose:
            print(f"⚠️  Error processing player {player_tm_id}: {e}")
        return profile


def main():
    parser = argparse.ArgumentParser(
        description="Enrich player profiles with market value history"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input JSONL file with player profiles",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSONL file (default: {input}_enriched.jsonl)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.5,
        help="Minimum delay between API calls in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=1.5,
        help="Maximum delay between API calls in seconds (default: 1.5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process first N players (for testing)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed progress information",
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.input_file.exists():
        print(f"❌ Input file not found: {args.input_file}")
        return 1
    
    # Determine output file
    if args.output:
        output_file = args.output
    else:
        output_file = args.input_file.parent / f"{args.input_file.stem}_enriched.jsonl"
    
    print(f"📖 Reading player profiles from: {args.input_file}")
    profiles = read_jsonl(args.input_file)
    print(f"✓ Loaded {len(profiles)} profiles")
    
    # Limit if requested
    if args.limit:
        profiles = profiles[:args.limit]
        print(f"⚠️  Processing only first {args.limit} profiles (--limit)")
    
    # Enrich profiles
    enriched_profiles = []
    
    print(f"\n🔄 Enriching profiles with market values...")
    for i, profile in enumerate(tqdm(profiles, desc="Processing", disable=args.verbose)):
        enriched = enrich_player_profile(profile, verbose=args.verbose)
        enriched_profiles.append(enriched)
        
        # Be polite to the API (except for last request)
        if i < len(profiles) - 1:
            polite_sleep(args.min_delay, args.max_delay)
        
        write_jsonl(output_file, enriched_profiles)  # Incremental write after each profile
    
    
    # Stats
    profiles_with_mvs = sum(
        1 for p in enriched_profiles
        if p.get("data", {}).get("market_values")
        and any(mv.get("value") is not None for mv in p["data"]["market_values"])
    )
    
    print(f"\n✅ Done!")
    print(f"   Total profiles: {len(enriched_profiles)}")
    print(f"   Profiles with market values: {profiles_with_mvs}")
    print(f"   Output file: {output_file}")
    
    return 0


if __name__ == "__main__":
    exit(main())
