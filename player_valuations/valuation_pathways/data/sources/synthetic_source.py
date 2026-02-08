"""Synthetic data providers for MVP.

Simple concrete implementations of data provider protocols using
configuration-based sources.
"""

from valuation_pathways.model.regimes import RegimeParameters
from valuation_pathways.config.schema import SimulationConfig


class StaticParameterProvider:
    """Provides regime parameters from a static configuration."""
    
    def __init__(self, config: SimulationConfig):
        """Initialize with simulation configuration.
        
        Args:
            config: Validated SimulationConfig
        """
        self.params = {
            name: RegimeParameters(mu=regime.mu, sigma=regime.sigma)
            for name, regime in config.regimes.items()
        }
    
    def get_parameters(self, regime: str) -> RegimeParameters:
        """Get parameters for a regime.
        
        Args:
            regime: Regime name
            
        Returns:
            RegimeParameters for the regime
            
        Raises:
            KeyError: If regime is not defined
        """
        if regime not in self.params:
            available = ", ".join(self.params.keys())
            raise KeyError(
                f"Unknown regime '{regime}'. Available: {available}"
            )
        return self.params[regime]


class ConfigScenarioProvider:
    """Provides scenario definitions from configuration."""
    
    def __init__(self, config: SimulationConfig, months: int):
        """Initialize with simulation configuration and horizon.
        
        Args:
            config: Validated SimulationConfig
            months: Total simulation horizon in months
        """
        self.config = config
        self.months = months
    
    def get_scenarios(self) -> dict[str, list[str]]:
        """Get all scenarios as expanded regime sequences.
        
        Returns:
            Mapping from scenario name to full regime sequence
        """
        return {
            name: scenario.expand_to_sequence(self.months)
            for name, scenario in self.config.scenarios.items()
        }


class ManualValuationProvider:
    """Provides a single fixed valuation (for CLI usage)."""
    
    def __init__(self, V0: float):
        """Initialize with a fixed valuation.
        
        Args:
            V0: Initial valuation in millions
        """
        self.V0 = V0
    
    def get_valuation(self, player_id: str) -> float:
        """Get the fixed valuation.
        
        Args:
            player_id: Player identifier (ignored)
            
        Returns:
            The fixed V0
        """
        return self.V0
