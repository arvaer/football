#!/usr/bin/env python3
"""
Test the transition analysis pipeline with a specific player.

Demonstrates the full workflow: analyze player -> get transitions -> lookup stratum stats.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph_builder.transition_analyzer import PlayerTransitionAnalyzer
from graph_builder.transition_stats_loader import get_transition_stats_loader


def test_player(player_tm_id: str):
    """Test transition analysis for a specific player."""
    
    print("=" * 80)
    print(f"Testing Player Transition Analysis: {player_tm_id}")
    print("=" * 80)
    
    # Analyze player
    analyzer = PlayerTransitionAnalyzer()
    transitions = analyzer.analyze_player(player_tm_id)
    
    if not transitions:
        print(f"No transitions found for player {player_tm_id}")
        return
    
    print(f"\nFound {len(transitions)} transitions\n")
    
    # Show first few transitions
    print("--- Sample Transitions ---")
    for i, trans in enumerate(transitions[:5], 1):
        print(f"\n#{i}")
        print(f"  Date: {trans.d0} -> {trans.d1} ({trans.dt_days} days)")
        print(f"  Age: {trans.age_at_d0} | Position: {trans.position}")
        print(f"  Value: €{trans.v0:.2f}M -> €{trans.v1:.2f}M")
        print(f"  Log Return: {trans.log_return:.6f}")
        print(f"  Rate/Day: {trans.rate_per_day:.8f}")
        print(f"  Move: {trans.move_label}")
        if trans.from_club and trans.to_club:
            print(f"  Clubs: {trans.from_club} -> {trans.to_club}")
        if trans.from_tier and trans.to_tier:
            print(f"  Tiers: {trans.from_tier} -> {trans.to_tier}")
    
    # Load stratum stats
    loader = get_transition_stats_loader()
    
    print("\n\n--- Stratum Statistics Lookup ---")
    for trans in transitions[:3]:
        stats = loader.get_stratum_stats(
            age=trans.age_at_d0,
            position=trans.position,
            move_label=trans.move_label
        )
        
        if stats:
            print(f"\nStratum: {stats.stratum_key}")
            print(f"  Sample size: n={stats.n}")
            print(f"  μ(log_return) = {stats.mu_log_return:.6f}")
            print(f"  σ(log_return) = {stats.sigma_log_return:.6f}")
            print(f"  μ(rate/day) = {stats.mu_rate_per_day:.8f}")
            print(f"  σ(rate/day) = {stats.sigma_rate_per_day:.8f}")
            print(f"  Median Δt = {stats.dt_days_median} days")
            
            # Compare this transition to stratum
            z_score = (trans.log_return - stats.mu_log_return) / stats.sigma_log_return if stats.sigma_log_return > 0 else 0
            print(f"  This transition's z-score: {z_score:.2f}")
        else:
            print(f"\nNo stats found for stratum: age={trans.age_at_d0}, pos={trans.position}, move={trans.move_label}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test transition analysis with a player"
    )
    parser.add_argument(
        'player_id',
        nargs='?',
        default='315969',  # Scott McTominay
        help='Transfermarkt player ID (default: 315969 - Scott McTominay)'
    )
    
    args = parser.parse_args()
    test_player(args.player_id)


if __name__ == '__main__':
    main()
