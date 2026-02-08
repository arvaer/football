"""Protocol definitions for dynamics models.

This module defines the interface that all valuation dynamics models must implement,
enabling swappable model implementations (regime-switching, HMM, GBM, etc.).
"""

from typing import Protocol
import numpy as np


class DynamicsModel(Protocol):
    """Protocol for valuation dynamics models.
    
    Any dynamics model must implement simulate_path to generate stochastic
    valuation trajectories under a given regime sequence.
    """
    
    def simulate_path(
        self,
        V0: float,
        regime_sequence: list[str],
        months: int,
        seed: int,
    ) -> np.ndarray:
        """Simulate a single valuation path.
        
        Args:
            V0: Initial valuation (in millions)
            regime_sequence: Ordered list of regime labels, length = months
            months: Number of monthly steps to simulate
            seed: Random seed for reproducibility
            
        Returns:
            Array of valuations [V0, V1, ..., V_T] with length = months + 1
        """
        ...
