"""Command-line interface for the valuation pathway simulator.

Orchestrates config loading, model instantiation, simulation execution,
and artifact generation.
"""

import argparse
import logging
from pathlib import Path

from valuation_pathways.config.loader import load_config
from valuation_pathways.model import get_model
from valuation_pathways.model.regimes import RegimeParameters
from valuation_pathways.data.sources.synthetic_source import ConfigScenarioProvider
from valuation_pathways.engine.simulator import run_simulation
from valuation_pathways.report.artifacts import write_artifacts


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """Run the valuation pathway simulator CLI."""
    parser = argparse.ArgumentParser(
        description="Simulate player valuation pathways across exposure regimes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--V0",
        type=float,
        help="Initial valuation in millions (overrides config default)",
    )
    parser.add_argument(
        "--months",
        type=int,
        help="Simulation horizon in months (overrides config default)",
    )
    parser.add_argument(
        "--N",
        type=int,
        help="Number of Monte Carlo paths per scenario (overrides config default)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducibility (overrides config default)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="out",
        help="Output directory for artifacts",
    )
    
    args = parser.parse_args()
    
    # Load and validate configuration
    logger.info(f"Loading configuration from {args.config}")
    config = load_config(args.config)
    
    # Apply CLI overrides or use defaults
    V0 = args.V0 if args.V0 is not None else config.defaults["V0"]
    months = args.months if args.months is not None else int(config.defaults["months"])
    N = args.N if args.N is not None else int(config.defaults["N"])
    seed = args.seed if args.seed is not None else int(config.defaults["seed"])
    
    logger.info(f"Simulation parameters: V0={V0:.2f}M, months={months}, N={N}, seed={seed}")
    
    # Get dynamics model from registry
    logger.info(f"Initializing model: {config.model}")
    ModelClass = get_model(config.model)
    
    # Convert config regimes to model parameters
    regime_params = {
        name: RegimeParameters(mu=regime.mu, sigma=regime.sigma)
        for name, regime in config.regimes.items()
    }
    model = ModelClass(regime_params)
    
    # Get scenario definitions
    scenario_provider = ConfigScenarioProvider(config, months)
    scenario_paths = scenario_provider.get_scenarios()
    
    logger.info(f"Running simulation for {len(scenario_paths)} scenarios...")
    for scenario_name in scenario_paths:
        logger.info(f"  - {scenario_name}")
    
    # Run simulation
    result = run_simulation(
        V0=V0,
        scenario_paths=scenario_paths,
        model=model,
        months=months,
        n_paths=N,
        seed=seed,
    )
    
    # Write artifacts
    logger.info(f"Writing artifacts to {args.outdir}/")
    write_artifacts(result, args.outdir, V0, months)
    
    logger.info("✓ Simulation complete!")
    logger.info(f"  - Results: {args.outdir}/results.csv")
    logger.info(f"  - Summary: {args.outdir}/summary.json")
    logger.info(f"  - Histogram: {args.outdir}/hist.png")
    logger.info(f"  - Report: {args.outdir}/report.md")


if __name__ == "__main__":
    main()
