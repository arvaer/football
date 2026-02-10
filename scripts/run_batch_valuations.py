#!/usr/bin/env python3
"""
Batch Valuation Processing Script

Processes all stratum statistics and runs valuation pathway simulations
for each stratum. Stores aggregated results in data/summary/<date>/ for
dashboard consumption.

Similar to the CLI tool but runs across all strata systematically.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph_builder.transition_stats_loader import get_transition_stats_loader
from player_valuations.valuation_pathways.model import RegimeSwitchingLogModel
from player_valuations.valuation_pathways.model.regimes import RegimeParameters
from player_valuations.valuation_pathways.engine.simulator import run_simulation
from player_valuations.valuation_pathways.report.artifacts import write_artifacts


def run_stratum_simulation(
    stratum_key: str,
    mu_stay: float,
    sigma_stay: float,
    mu_move: float,
    sigma_move: float,
    V0: float = 2.0,
    months: int = 6,
    n_paths: int = 1000,
    seed: int = 42,
):
    """
    Run valuation simulation for a single stratum.
    
    Args:
        stratum_key: Stratum identifier (e.g., "21-24_DEF_stay")
        mu_stay: Drift parameter for stay regime
        sigma_stay: Volatility parameter for stay regime
        mu_move: Drift parameter for move regime
        sigma_move: Volatility parameter for move regime
        V0: Initial valuation
        months: Simulation horizon
        n_paths: Number of Monte Carlo paths
        seed: Random seed
    
    Returns:
        SimulationResult object
    """
    # Create regime parameters
    regime_params = {
        "stay": RegimeParameters(mu=mu_stay, sigma=sigma_stay),
        "moved": RegimeParameters(mu=mu_move, sigma=sigma_move),
    }
    
    model = RegimeSwitchingLogModel(regime_params)
    
    # Define scenarios
    half_months = months // 2
    scenario_paths = {
        f"stay_{months}m": ["stay"] * months,
        f"move_{months}m": ["moved"] * months,
        f"stay_{half_months}m_move_{months-half_months}m": 
            ["stay"] * half_months + ["moved"] * (months - half_months),
    }
    
    # Run simulation
    result = run_simulation(
        V0=V0,
        scenario_paths=scenario_paths,
        model=model,
        months=months,
        n_paths=n_paths,
        seed=seed,
    )
    
    return result


def process_all_strata(
    V0: float = 2.0,
    months: int = 6,
    n_paths: int = 1000,
    seed: int = 42,
    min_sample_size: int = 10,
):
    """
    Process all strata and generate batch valuation results.
    
    Args:
        V0: Initial valuation (default 2.0M)
        months: Simulation horizon
        n_paths: Number of Monte Carlo paths per scenario
        seed: Random seed
        min_sample_size: Minimum sample size to include stratum
    
    Returns:
        DataFrame with all results
    """
    loader = get_transition_stats_loader()
    all_stats = loader.get_all_stratum_stats()
    
    print(f"=== Batch Valuation Processing ===\n")
    print(f"Total strata: {len(all_stats)}")
    print(f"V0: {V0:.2f}M, Horizon: {months} months, Paths: {n_paths}\n")
    
    # Group strata by base (age_band, position)
    stratum_groups = {}
    for key, stats in all_stats.items():
        if stats.n < min_sample_size:
            continue
        
        base_key = f"{stats.age_band}_{stats.position}"
        if base_key not in stratum_groups:
            stratum_groups[base_key] = {}
        
        stratum_groups[base_key][stats.move_label] = stats
    
    # Filter groups that have both stay and moved data
    complete_groups = {
        k: v for k, v in stratum_groups.items()
        if 'stay' in v and 'moved' in v
    }
    
    print(f"Complete stratum groups (with stay & moved): {len(complete_groups)}")
    print(f"Skipped {len(all_stats) - len(complete_groups) * 2} strata (incomplete or low-n)\n")
    
    all_results = []
    
    for i, (base_key, group) in enumerate(complete_groups.items(), 1):
        age_band, position = base_key.split('_', 1)
        
        stay_stats = group['stay']
        move_stats = group['moved']
        
        print(f"[{i}/{len(complete_groups)}] Processing {base_key}...")
        print(f"  Stay:  n={stay_stats.n:5d}, μ={stay_stats.mu_rate_per_30day:7.4f}, σ={stay_stats.sigma_rate_per_30day:7.4f}")
        print(f"  Moved: n={move_stats.n:5d}, μ={move_stats.mu_rate_per_30day:7.4f}, σ={move_stats.sigma_rate_per_30day:7.4f}")
        
        # Run simulation
        result = run_stratum_simulation(
            stratum_key=base_key,
            mu_stay=stay_stats.mu_rate_per_30day,
            sigma_stay=stay_stats.sigma_rate_per_30day,
            mu_move=move_stats.mu_rate_per_30day,
            sigma_move=move_stats.sigma_rate_per_30day,
            V0=V0,
            months=months,
            n_paths=n_paths,
            seed=seed,
        )
        
        # Add metadata to results
        for scenario in result.final_values['scenario'].unique():
            scenario_summary = result.summary[scenario]
            
            all_results.append({
                'stratum': base_key,
                'age_band': age_band,
                'position': position,
                'scenario': scenario,
                'n_stay': stay_stats.n,
                'n_moved': move_stats.n,
                'mu_stay': stay_stats.mu_rate_per_30day,
                'sigma_stay': stay_stats.sigma_rate_per_30day,
                'mu_moved': move_stats.mu_rate_per_30day,
                'sigma_moved': move_stats.sigma_rate_per_30day,
                'V0': V0,
                'mean_VT': scenario_summary['mean'],
                'median_VT': scenario_summary['p50'],
                'p10_VT': scenario_summary['p10'],
                'p90_VT': scenario_summary['p90'],
                'prob_down': scenario_summary['prob_down'],
            })
    
    print(f"\n✓ Completed {len(complete_groups)} strata")
    
    return pd.DataFrame(all_results)


def main():
    """Run batch valuation processing."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Batch valuation processing across all strata",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--V0",
        type=float,
        default=2.0,
        help="Initial valuation in millions",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="Simulation horizon in months",
    )
    parser.add_argument(
        "--N",
        type=int,
        default=1000,
        help="Number of Monte Carlo paths per scenario",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=10,
        help="Minimum stratum sample size to include",
    )
    
    args = parser.parse_args()
    
    # Run processing
    results_df = process_all_strata(
        V0=args.V0,
        months=args.months,
        n_paths=args.N,
        seed=args.seed,
        min_sample_size=args.min_sample_size,
    )
    
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(f"data/summary/batch_valuations_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save results
    results_path = output_dir / "batch_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\nResults saved to {results_path}")
    
    # Save summary JSON
    summary = {
        "timestamp": timestamp,
        "parameters": {
            "V0": args.V0,
            "months": args.months,
            "n_paths": args.N,
            "seed": args.seed,
            "min_sample_size": args.min_sample_size,
        },
        "stats": {
            "num_strata": len(results_df['stratum'].unique()),
            "num_scenarios": len(results_df),
        },
    }
    
    summary_path = output_dir / "summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to {summary_path}")
    
    # Print quick stats
    print(f"\n=== Summary Statistics ===")
    print(f"Strata processed: {len(results_df['stratum'].unique())}")
    print(f"Total scenario results: {len(results_df)}")
    
    print(f"\n=== Top 10 Scenarios by Mean Return ===")
    top_results = results_df.nlargest(10, 'mean_VT')[
        ['stratum', 'scenario', 'mean_VT', 'prob_down']
    ]
    print(top_results.to_string(index=False))
    
    print(f"\n=== Top 10 Riskiest Scenarios (Highest Prob Down) ===")
    risky_results = results_df.nlargest(10, 'prob_down')[
        ['stratum', 'scenario', 'mean_VT', 'prob_down']
    ]
    print(risky_results.to_string(index=False))
    
    print(f"\n✓ Batch processing complete!")


if __name__ == "__main__":
    main()
