"""Pure simulation engine.

Core simulation logic that is deterministic, dependency-injected, and
agnostic to I/O operations.
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from valuation_pathways.model.interfaces import DynamicsModel
from valuation_pathways.engine.metrics import compute_summary_metrics


class SimulationResult(BaseModel):
    """Container for simulation results.
    
    Attributes:
        final_values: DataFrame with columns [scenario, path_id, V_T]
        summary: Nested dict {scenario_name: {metric: value}}
        stratum_info: Optional metadata about the stratum used for the simulation
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    final_values: pd.DataFrame
    summary: dict[str, dict[str, float]]
    stratum_info: dict | None = None


def run_simulation(
    V0: float,
    scenario_paths: dict[str, list[str]],
    model: DynamicsModel,
    months: int,
    n_paths: int,
    seed: int,
) -> SimulationResult:
    """Run Monte Carlo simulation across multiple scenarios.
    
    This is the pure core of the simulator: deterministic given inputs,
    no I/O, dependency-injected model.
    
    Args:
        V0: Initial valuation (in millions)
        scenario_paths: Mapping from scenario name to full regime sequence
        model: Dynamics model implementing DynamicsModel protocol
        months: Simulation horizon in months
        n_paths: Number of Monte Carlo paths per scenario
        seed: Base random seed for reproducibility
        
    Returns:
        SimulationResult containing final values DataFrame and summary stats
        
    Raises:
        ValueError: If scenario paths have incorrect length
    """
    # Validate scenario path lengths
    for scenario_name, regime_seq in scenario_paths.items():
        if len(regime_seq) != months:
            raise ValueError(
                f"Scenario '{scenario_name}' has {len(regime_seq)} regimes, "
                f"but months={months}"
            )
    
    # Storage for results
    results_data = []
    summaries = {}
    
    # Run simulations for each scenario
    for scenario_name, regime_sequence in scenario_paths.items():
        final_vals = np.zeros(n_paths)
        
        for path_id in range(n_paths):
            # Unique seed per scenario-path combination
            path_seed = seed + hash((scenario_name, path_id)) % (2**31)
            
            # Simulate path
            path = model.simulate_path(V0, regime_sequence, months, path_seed)
            final_vals[path_id] = path[-1]  # V_T
            
            # Store result
            results_data.append({
                "scenario": scenario_name,
                "path_id": path_id,
                "V_T": path[-1],
            })
        
        # Compute summary metrics
        summaries[scenario_name] = compute_summary_metrics(final_vals, V0)
    
    # Build result dataframe
    df = pd.DataFrame(results_data)
    
    return SimulationResult(final_values=df, summary=summaries)
