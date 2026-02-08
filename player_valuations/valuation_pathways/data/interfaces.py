"""Data provider protocol definitions.

Defines interfaces for accessing regimes, parameters, scenarios, and valuations.
These abstractions enable future swapping of data sources (CSV, database, API, etc.).
"""

from typing import Protocol
from valuation_pathways.model.regimes import RegimeParameters


class RegimeProvider(Protocol):
    """Provides regime labels for players at specific timesteps."""
    
    def get_regime(self, player_id: str, timestep: int) -> str:
        """Get the regime for a player at a given timestep.
        
        Args:
            player_id: Player identifier
            timestep: Time index (0 = initial)
            
        Returns:
            Regime label (e.g., "ecuador", "brazil", "europe")
        """
        ...


class ParameterProvider(Protocol):
    """Provides regime-specific model parameters."""
    
    def get_parameters(self, regime: str) -> RegimeParameters:
        """Get drift and volatility parameters for a regime.
        
        Args:
            regime: Regime label
            
        Returns:
            RegimeParameters with mu and sigma
        """
        ...


class ScenarioProvider(Protocol):
    """Provides scenario definitions for simulation."""
    
    def get_scenarios(self) -> dict[str, list[str]]:
        """Get all scenario definitions as expanded regime sequences.
        
        Returns:
            Mapping from scenario name to regime sequence
        """
        ...


class ValuationProvider(Protocol):
    """Provides initial valuations for players."""
    
    def get_valuation(self, player_id: str) -> float:
        """Get the initial valuation for a player.
        
        Args:
            player_id: Player identifier
            
        Returns:
            Valuation in millions
        """
        ...
