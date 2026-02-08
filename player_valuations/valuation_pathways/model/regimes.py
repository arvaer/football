"""Regime definitions and parameter storage.

Regimes represent different exposure contexts (leagues, markets) with
associated drift and volatility parameters.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeParameters:
    """Parameters for a single regime.
    
    Attributes:
        mu: Monthly log-drift (expected log-return)
        sigma: Monthly log-volatility (standard deviation of log-returns)
    """
    
    mu: float
    sigma: float
    
    def __post_init__(self):
        """Validate parameter ranges."""
        if self.sigma < 0:
            raise ValueError(f"sigma must be non-negative, got {self.sigma}")
