"""Discrete-time regime-switching log-value dynamics.

Implements the core valuation model:
    log V_{t+1} = log V_t + mu_{s_t} + sigma_{s_t} * epsilon_t
where epsilon_t ~ N(0, 1) and s_t is the regime at time t.
"""

import numpy as np
from valuation_pathways.model.interfaces import DynamicsModel
from valuation_pathways.model.regimes import RegimeParameters


class RegimeSwitchingLogModel(DynamicsModel):
    """Discrete-time regime-switching log-normal dynamics.
    
    Generates valuation paths where drift and volatility depend on the
    current regime. The model is deterministic given a fixed seed.
    """
    
    def __init__(self, regime_params: dict[str, RegimeParameters]):
        """Initialize the model with regime parameters.
        
        Args:
            regime_params: Mapping from regime name to (mu, sigma) parameters
        """
        self.regime_params = regime_params
    
    def simulate_path(
        self,
        V0: float,
        regime_sequence: list[str],
        months: int,
        seed: int,
    ) -> np.ndarray:
        """Simulate a single valuation path under a regime sequence.
        
        Args:
            V0: Initial valuation (in millions)
            regime_sequence: Ordered list of regime labels, length = months
            months: Number of monthly steps to simulate
            seed: Random seed for reproducibility
            
        Returns:
            Array of valuations [V0, V1, ..., V_T] with length = months + 1
            
        Raises:
            ValueError: If regime_sequence length doesn't match months
            KeyError: If a regime in the sequence is not in regime_params
        """
        if len(regime_sequence) != months:
            raise ValueError(
                f"regime_sequence length ({len(regime_sequence)}) must match "
                f"months ({months})"
            )
        
        # Validate all regimes are known
        for regime in regime_sequence:
            if regime not in self.regime_params:
                available = ", ".join(self.regime_params.keys())
                raise KeyError(
                    f"Unknown regime '{regime}'. Available: {available}"
                )
        
        # Initialize random state
        rng = np.random.RandomState(seed)
        
        # Simulate in log-space
        log_V = np.zeros(months + 1)
        log_V[0] = np.log(V0)
        
        for t in range(months):
            regime = regime_sequence[t]
            params = self.regime_params[regime]
            
            epsilon = rng.randn()
            log_V[t + 1] = log_V[t] + params.mu + params.sigma * epsilon
        
        # Convert back to levels
        return np.exp(log_V)
