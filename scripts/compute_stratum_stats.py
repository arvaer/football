#!/usr/bin/env python3
"""
Compute stratified statistics (μ, σ) from transition data.

Reads transition JSONL file and computes summary statistics grouped by
(age_band, position, move_label) strata.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
import statistics

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_age_band(age: float) -> str:
    """
    Convert age to coarse band label.
    
    Bands: U21, 21-24, 25-28, 29+
    """
    if age < 21:
        return 'U21'
    elif age < 25:
        return '21-24'
    elif age < 29:
        return '25-28'
    else:
        return '29+'


def load_transitions(file_path: Path) -> List[Dict]:
    """Load all transition records from JSONL file."""
    transitions = []
    
    print(f"Loading transitions from {file_path.name}...")
    with open(file_path, 'r') as f:
        for line in f:
            try:
                record = json.loads(line)
                transitions.append(record)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line: {e}")
                continue
    
    print(f"Loaded {len(transitions)} transitions")
    return transitions


def compute_stratum_stats(transitions: List[Dict], use_granular_position: bool = False) -> List[Dict]:
    """
    Compute statistics grouped by (age_band, position_group, moved).
    
    Args:
        transitions: List of transition dictionaries
        use_granular_position: If True, use specific position; if False, use position_group
    
    Returns:
        List of stratum statistics dictionaries
    """
    # Group transitions by stratum
    strata = defaultdict(list)
    
    for trans in transitions:
        # Use pre-computed fields from transition analyzer
        age_band = trans.get('age_band', get_age_band(trans.get('age_at_d0', 0)))
        position = trans.get('position_group', 'UNK') if not use_granular_position else trans.get('position', 'UNK')
        
        # Primary stratification: moved (boolean)
        moved = trans.get('moved', False)
        move_label = 'moved' if moved else 'stay'
        
        stratum_key = (age_band, position, move_label)
        
        strata[stratum_key].append(trans)
    
    print(f"\nFound {len(strata)} unique strata")
    
    # Compute statistics for each stratum
    stratum_stats = []
    
    for (age_band, position, move_label), trans_list in strata.items():
        n = len(trans_list)
        
        # Extract metrics
        log_returns = [t['log_return'] for t in trans_list]
        rates_per_day = [t['rate_per_day'] for t in trans_list]
        rates_per_30day = [t.get('rate_per_30day', t['rate_per_day'] * 30) for t in trans_list]
        dt_days_list = [t['dt_days'] for t in trans_list]
        
        # Count mapping success (for moved transitions)
        if move_label == 'moved':
            mapping_ok_count = sum(1 for t in trans_list if t.get('mapping_ok', False))
            mapping_ok_pct = 100 * mapping_ok_count / n if n > 0 else 0
        else:
            mapping_ok_count = None
            mapping_ok_pct = None
        
        # Compute statistics
        stats = {
            'stratum_key': f"{age_band}_{position}_{move_label}",
            'age_band': age_band,
            'position': position,
            'move_label': move_label,
            'n': n,
            
            # Log return statistics
            'mu_log_return': round(statistics.mean(log_returns), 6),
            
            # Rate per 30-day statistics (normalized horizon)
            'mu_rate_per_30day': round(statistics.mean(rates_per_30day), 6),
            'sigma_rate_per_30day': round(statistics.stdev(rates_per_30day), 6) if n > 1 else 0.0,
            'median_rate_per_30day': round(statistics.median(rates_per_30day), 6),
            
            # Mapping success (for moved transitions)
            'mapping_ok_count': mapping_ok_count,
            'mapping_ok_pct': round(mapping_ok_pct, 1) if mapping_ok_pct is not None else None,
            'sigma_log_return': round(statistics.stdev(log_returns), 6) if n > 1 else 0.0,
            'median_log_return': round(statistics.median(log_returns), 6),
            'min_log_return': round(min(log_returns), 6),
            'max_log_return': round(max(log_returns), 6),
            
            # Rate per day statistics
            'mu_rate_per_day': round(statistics.mean(rates_per_day), 8),
            'sigma_rate_per_day': round(statistics.stdev(rates_per_day), 8) if n > 1 else 0.0,
            'median_rate_per_day': round(statistics.median(rates_per_day), 8),
            
            # Time delta statistics
            'dt_days_median': int(statistics.median(dt_days_list)),
            'dt_days_mean': round(statistics.mean(dt_days_list), 1),
            'dt_days_p25': int(statistics.quantiles(dt_days_list, n=4)[0]) if n >= 4 else min(dt_days_list),
            'dt_days_p75': int(statistics.quantiles(dt_days_list, n=4)[2]) if n >= 4 else max(dt_days_list),
            'dt_days_p90': int(statistics.quantiles(dt_days_list, n=10)[8]) if n >= 10 else max(dt_days_list),
            'dt_days_min': min(dt_days_list),
            'dt_days_max': max(dt_days_list),
        }
        
        stratum_stats.append(stats)
    
    # Print summary inline
    total_transitions = sum(len(trans_list) for trans_list in strata.values())
    
    # Group by move type
    move_type_counts = defaultdict(int)
    mapped_moves = 0
    total_moves = 0
    
    for s in stratum_stats:
        move_type_counts[s['move_label']] += s['n']
        if s['move_label'] == 'moved':
            total_moves += s['n']
            if s.get('mapping_ok_count'):
                mapped_moves += s['mapping_ok_count']
    
    print("\n--- Move Type Distribution ---")
    for move_type, count in sorted(move_type_counts.items(), key=lambda x: x[1], reverse=True):
        pct = 100 * count / total_transitions
        print(f"  {move_type:30s}: {count:6,} ({pct:5.1f}%)")
    
    if total_moves > 0:
        print(f"\n--- Transfer Mapping Coverage ---")
        print(f"  Total moves: {total_moves:,}")
        print(f"  Mapped to leagues: {mapped_moves:,} ({100*mapped_moves/total_moves:.1f}%)")
        print(f"  Mapping failed: {total_moves - mapped_moves:,} ({100*(total_moves-mapped_moves)/total_moves:.1f}%)")
    
    # Top 20 largest strata
    print("\n--- Top 20 Largest Strata ---")
    print(f"{'Age Band':<10} {'Pos':<5} {'Moved':<8} {'N':>6} {'μ(r/30d)':>10} {'σ(r/30d)':>10} {'dt_med':>8} {'Map%':>6}")
    print("-" * 80)
    
    for s in stratum_stats[:20]:
        map_pct = f"{s['mapping_ok_pct']:.1f}" if s['mapping_ok_pct'] is not None else "N/A"
        print(f"{s['age_band']:<10} {s['position']:<5} {s['move_label']:<8} "
              f"{s['n']:6,} {s['mu_rate_per_30day']:10.4f} {s['sigma_rate_per_30day']:10.4f} "
              f"{s['dt_days_median']:8d} {map_pct:>6}")
    
    # Flag low-n strata
    low_n_strata = [s for s in stratum_stats if s['n'] < 10]
    print(f"\n--- Low Sample Size Alert ---")
    print(f"Strata with n < 10: {len(low_n_strata)}")
    
    if low_n_strata:
        print("\nSample of low-n strata:")
        for s in low_n_strata[:5]:
            print(f"  {s['stratum_key']}: n={s['n']}")
    
    # Sort by sample size (largest first)
    stratum_stats.sort(key=lambda x: x['n'], reverse=True)
    
    return stratum_stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compute stratified statistics from transition data"
    )
    parser.add_argument(
        'input_file',
        type=Path,
        nargs='?',
        help='Input transition JSONL file (default: most recent mv_transitions_*.jsonl)'
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        help='Output file path (default: data/extracted/stratum_stats_YYYY-MM-DD.jsonl)'
    )
    parser.add_argument(
        '--granular-position',
        action='store_true',
        help='Use granular position (CM, CF, etc.) instead of position groups (DEF, MID, FWD)'
    )
    
    args = parser.parse_args()
    
    # Determine input file
    if args.input_file:
        input_file = args.input_file
    else:
        data_dir = Path("data/extracted")
        transition_files = list(data_dir.glob("mv_transitions_*.jsonl"))
        
        if not transition_files:
            print("Error: No transition files found")
            sys.exit(1)
        
        input_file = max(transition_files, key=lambda p: p.stat().st_mtime)
        print(f"Using most recent transition file: {input_file.name}")
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    # Determine output file
    if args.output:
        output_file = args.output
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        output_file = Path(f"data/extracted/stratum_stats_{today}.jsonl")
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print("=== Stratum Statistics Computation ===\n")
    
    # Load and process
    transitions = load_transitions(input_file)
    stratum_stats = compute_stratum_stats(transitions, use_granular_position=args.granular_position)
    
    # Write output
    print(f"\nWriting statistics to {output_file.name}...")
    with open(output_file, 'w') as f:
        for stat in stratum_stats:
            f.write(json.dumps(stat) + '\n')
    
    print(f"Wrote {len(stratum_stats)} stratum statistics")
    
    print(f"\n✓ Output: {output_file}")


if __name__ == '__main__':
    main()
