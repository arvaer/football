"""Summary metrics computation.

Computes distributional statistics (mean, percentiles, downside probability)
from simulation results.
"""

import numpy as np


def compute_summary_metrics(
    final_values: np.ndarray,
    V0: float,
) -> dict[str, float]:
    """Compute summary statistics for a set of final valuations.
    
    Args:
        final_values: Array of final valuations V_T from N simulations
        V0: Initial valuation (for computing downside probability)
        
    Returns:
        Dictionary with keys:
            - mean: Mean final valuation
            - p10: 10th percentile
            - p50: 50th percentile (median)
            - p90: 90th percentile
            - prob_down: Probability that V_T < V0
    """
    return {
        "mean": float(np.mean(final_values)),
        "p10": float(np.percentile(final_values, 10)),
        "p50": float(np.percentile(final_values, 50)),
        "p90": float(np.percentile(final_values, 90)),
        "prob_down": float(np.mean(final_values < V0)),
    }
