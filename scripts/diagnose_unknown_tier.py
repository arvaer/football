#!/usr/bin/env python3
"""
Diagnose unknown_tier transitions to identify join failures.

Root cause analysis for league mapping failures.
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph_builder.league_tier_mapper import get_league_tier_mapper


def diagnose_unknown_tier():
    """Audit unknown_tier transitions to find mapping failures."""
    
    # Load transitions
    data_dir = Path("data/extracted")
    transition_files = list(data_dir.glob("mv_transitions_*.jsonl"))
    
    if not transition_files:
        print("Error: No transition files found")
        return
    
    latest_file = max(transition_files, key=lambda p: p.stat().st_mtime)
    print(f"Analyzing: {latest_file.name}\n")
    
    transitions = []
    with open(latest_file, 'r') as f:
        for line in f:
            transitions.append(json.loads(line))
    
    # Get league mapper
    mapper = get_league_tier_mapper()
    
    # Separate by move type
    unknown_tier = [t for t in transitions if t['move_label'] == 'unknown_tier']
    stay = [t for t in transitions if t['move_label'] == 'stay']
    known_moves = [t for t in transitions if t['move_label'] not in ['unknown_tier', 'stay']]
    
    print("=" * 80)
    print("DATASET OVERVIEW")
    print("=" * 80)
    print(f"Total transitions: {len(transitions):,}")
    print(f"  Stay: {len(stay):,} ({100*len(stay)/len(transitions):.1f}%)")
    print(f"  Known moves: {len(known_moves):,} ({100*len(known_moves)/len(transitions):.1f}%)")
    print(f"  Unknown tier: {len(unknown_tier):,} ({100*len(unknown_tier)/len(transitions):.1f}%)")
    
    print("\n" + "=" * 80)
    print("UNKNOWN_TIER ROOT CAUSE ANALYSIS")
    print("=" * 80)
    
    # Analyze unknown_tier failures
    from_club_missing = 0
    to_club_missing = 0
    from_league_missing = 0
    to_league_missing = 0
    both_clubs_present = 0
    both_leagues_missing = 0
    
    failure_patterns = Counter()
    sample_failures = []
    
    for trans in unknown_tier:
        from_club = trans.get('from_club')
        to_club = trans.get('to_club')
        
        # Check club presence
        has_from_club = bool(from_club)
        has_to_club = bool(to_club)
        
        if not has_from_club:
            from_club_missing += 1
        if not has_to_club:
            to_club_missing += 1
        
        # Check league mapping
        from_league = mapper.get_league_info(from_club) if from_club else None
        to_league = mapper.get_league_info(to_club) if to_club else None
        
        has_from_league = bool(from_league)
        has_to_league = bool(to_league)
        
        if not has_from_league:
            from_league_missing += 1
        if not has_to_league:
            to_league_missing += 1
        
        if has_from_club and has_to_club:
            both_clubs_present += 1
        
        if not has_from_league and not has_to_league:
            both_leagues_missing += 1
        
        # Pattern analysis
        pattern = f"from_club={'Y' if has_from_club else 'N'}, " \
                  f"to_club={'Y' if has_to_club else 'N'}, " \
                  f"from_league={'Y' if has_from_league else 'N'}, " \
                  f"to_league={'Y' if has_to_league else 'N'}"
        failure_patterns[pattern] += 1
        
        # Collect samples
        if len(sample_failures) < 20:
            sample_failures.append({
                'player_id': trans.get('player_id'),
                'age': trans.get('age_at_d0'),
                'position': trans.get('position'),
                'from_club': from_club,
                'to_club': to_club,
                'has_from_league': has_from_league,
                'has_to_league': has_to_league,
                'd0': trans.get('d0'),
                'd1': trans.get('d1'),
                'v0': trans.get('v0'),
                'v1': trans.get('v1'),
            })
    
    print(f"\nTotal unknown_tier transitions: {len(unknown_tier):,}")
    print(f"\nMissing Data Summary:")
    print(f"  Transitions with both club IDs present: {both_clubs_present:,} ({100*both_clubs_present/len(unknown_tier):.1f}%)")
    print(f"  from_club missing: {from_club_missing:,} ({100*from_club_missing/len(unknown_tier):.1f}%)")
    print(f"  to_club missing: {to_club_missing:,} ({100*to_club_missing/len(unknown_tier):.1f}%)")
    print(f"  from_league not found: {from_league_missing:,} ({100*from_league_missing/len(unknown_tier):.1f}%)")
    print(f"  to_league not found: {to_league_missing:,} ({100*to_league_missing/len(unknown_tier):.1f}%)")
    print(f"  Both leagues missing: {both_leagues_missing:,} ({100*both_leagues_missing/len(unknown_tier):.1f}%)")
    
    print(f"\n--- Top 10 Failure Patterns ---")
    for pattern, count in failure_patterns.most_common(10):
        pct = 100 * count / len(unknown_tier)
        print(f"  {pattern}: {count:,} ({pct:.1f}%)")
    
    print(f"\n--- Sample of 20 Unknown Tier Transitions ---")
    print(f"{'Player':<10} {'Age':>5} {'Pos':<4} {'From Club':<15} {'To Club':<15} {'From Lg':>7} {'To Lg':>7} {'Date Range':<25}")
    print("-" * 120)
    
    for sample in sample_failures[:20]:
        from_club_display = (sample['from_club'] or 'NULL')[:15]
        to_club_display = (sample['to_club'] or 'NULL')[:15]
        date_range = f"{sample['d0'][:10]} -> {sample['d1'][:10]}"
        
        print(f"{sample['player_id']:<10} {sample['age']:5.1f} {sample['position']:<4} "
              f"{from_club_display:<15} {to_club_display:<15} "
              f"{'Y' if sample['has_from_league'] else 'N':>7} "
              f"{'Y' if sample['has_to_league'] else 'N':>7} "
              f"{date_range:<25}")
    
    # Check specific club IDs that aren't mapped
    print("\n--- Sample of Unmapped Club IDs ---")
    unmapped_clubs = Counter()
    
    for trans in unknown_tier:
        from_club = trans.get('from_club')
        to_club = trans.get('to_club')
        
        if from_club and not mapper.get_league_info(from_club):
            unmapped_clubs[from_club] += 1
        if to_club and not mapper.get_league_info(to_club):
            unmapped_clubs[to_club] += 1
    
    print(f"\nTop 20 unmapped club IDs (by frequency):")
    for club_id, count in unmapped_clubs.most_common(20):
        print(f"  Club ID {club_id}: appears {count} times")
    
    # Mapper statistics
    print("\n" + "=" * 80)
    print("LEAGUE MAPPER STATISTICS")
    print("=" * 80)
    stats = mapper.get_stats()
    print(f"Clubs mapped by name: {stats['total_clubs_by_name']:,}")
    print(f"Clubs mapped by tm_id: {stats['total_clubs_by_id']:,}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if both_clubs_present == len(unknown_tier):
        print("✓ All unknown_tier transitions have both club IDs")
        print("✗ Issue: Club IDs are not in the league mapping")
        print("\nLikely causes:")
        print("  1. Club plays in a league not in league_clubs_enriched data")
        print("  2. Club ID format mismatch (name vs tm_id)")
        print("  3. Historical clubs (retired/dissolved)")
        print("\nNext steps:")
        print("  - Check if unmapped clubs are in lower leagues not scraped")
        print("  - Consider adding fallback: unknown_tier -> 'moved_unknown_league'")
        print("  - Or: expand league coverage in scraping")
    else:
        print("✗ Some transitions are missing club ID data")
        print("\nNext steps:")
        print("  - Verify market_values array has 'club' field populated")
        print("  - Check data quality in player_profile enrichment")


if __name__ == '__main__':
    diagnose_unknown_tier()
