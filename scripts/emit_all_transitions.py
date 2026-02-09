#!/usr/bin/env python3
"""
Batch process all players to emit market value transition records.

Reads all enriched player profiles and generates transition rows for
each player, writing results to a datestamped JSONL file.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph_builder.transition_analyzer import PlayerTransitionAnalyzer, TransitionRow


def load_all_players(file_path: Path) -> List[Dict]:
    """Load all player records from enriched profile file."""
    players = []
    
    print(f"Loading players from {file_path.name}...")
    with open(file_path, 'r') as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get('success'):
                    players.append(record)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line: {e}")
                continue
    
    print(f"Loaded {len(players)} players")
    return players


def emit_all_transitions(output_file: Path, sample_size: Optional[int] = None):
    """
    Process all players and emit transitions to JSONL file.
    
    Args:
        output_file: Path to output JSONL file
        sample_size: If provided, only process this many players (for testing)
    """
    # Find most recent enriched profile file
    data_dir = Path("data/extracted")
    profile_files = list(data_dir.glob("player_profile_*_enriched.jsonl"))
    
    if not profile_files:
        print("Error: No enriched player profile files found")
        return
    
    latest_file = max(profile_files, key=lambda p: p.stat().st_mtime)
    print(f"Using {latest_file.name}")
    
    # Load all players
    all_players = load_all_players(latest_file)
    
    if sample_size:
        import random
        all_players = random.sample(all_players, min(sample_size, len(all_players)))
        print(f"Sampled {len(all_players)} players for processing")
    
    # Initialize analyzer
    analyzer = PlayerTransitionAnalyzer()
    
    # Process all players
    total_transitions = 0
    players_processed = 0
    players_with_transitions = 0
    
    with open(output_file, 'w') as out_f:
        for i, player_record in enumerate(all_players, 1):
            player_info = player_record.get('data', {}).get('player', {})
            player_tm_id = player_info.get('tm_id')
            player_name = player_info.get('name', 'Unknown')
            
            if not player_tm_id:
                continue
            
            # Analyze player
            transitions = analyzer.analyze_player(player_tm_id, player_record)
            
            if transitions:
                players_with_transitions += 1
                for transition in transitions:
                    out_f.write(json.dumps(transition.to_dict()) + '\n')
                    total_transitions += 1
            
            players_processed += 1
            
            if i % 100 == 0:
                print(f"Processed {i}/{len(all_players)} players, "
                      f"{total_transitions} transitions so far...")
    
    print("\n=== Emission Complete ===")
    print(f"Players processed: {players_processed}")
    print(f"Players with transitions: {players_with_transitions}")
    print(f"Total transitions emitted: {total_transitions}")
    print(f"Average transitions per player: {total_transitions / players_processed:.2f}")
    print(f"Output: {output_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Emit all player market value transitions to JSONL"
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        help='Output file path (default: data/extracted/mv_transitions_YYYY-MM-DD.jsonl)'
    )
    parser.add_argument(
        '--sample',
        '-n',
        type=int,
        help='Sample size (number of random players to process for testing)'
    )
    
    args = parser.parse_args()
    
    # Determine output file
    if args.output:
        output_file = args.output
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        output_file = Path(f"data/extracted/mv_transitions_{today}.jsonl")
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print("=== Player Transition Emission ===\n")
    emit_all_transitions(output_file, sample_size=args.sample)


if __name__ == '__main__':
    main()
