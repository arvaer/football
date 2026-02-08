"""Pydantic configuration schemas.

Defines validated data structures for regimes, scenarios, and simulation config.
"""

from pydantic import BaseModel, Field, field_validator


class RegimeConfig(BaseModel):
    """Configuration for a single regime.
    
    Attributes:
        mu: Monthly log-drift (expected log-return)
        sigma: Monthly log-volatility (standard deviation)
    """
    
    mu: float = Field(..., description="Monthly log drift")
    sigma: float = Field(..., ge=0, description="Monthly log volatility (must be >= 0)")


class ScenarioSegment(BaseModel):
    """A segment of a scenario with a single regime for a duration.
    
    Attributes:
        regime: Name of the regime for this segment
        months: Duration in months for this segment
    """
    
    regime: str = Field(..., description="Regime name")
    months: int = Field(..., gt=0, description="Duration in months (must be > 0)")


class ScenarioConfig(BaseModel):
    """Configuration for a pathway scenario.
    
    Attributes:
        segments: List of regime segments that make up the full pathway
    """
    
    segments: list[ScenarioSegment] = Field(..., min_length=1)
    
    def expand_to_sequence(self, total_months: int) -> list[str]:
        """Expand compact segments into a full regime sequence.
        
        Args:
            total_months: Total simulation horizon
            
        Returns:
            List of regime names with length = total_months
            
        Raises:
            ValueError: If segment durations don't sum to total_months
        """
        sequence = []
        for segment in self.segments:
            sequence.extend([segment.regime] * segment.months)
        
        if len(sequence) != total_months:
            raise ValueError(
                f"Scenario segments sum to {len(sequence)} months, "
                f"but total_months is {total_months}"
            )
        
        return sequence


class SimulationConfig(BaseModel):
    """Top-level simulation configuration.
    
    Attributes:
        model: Name of the dynamics model to use
        regimes: Mapping from regime name to parameters
        scenarios: Mapping from scenario name to pathway definition
        defaults: Default simulation parameters
    """
    
    model: str = Field(default="regime_switching_log", description="Dynamics model name")
    regimes: dict[str, RegimeConfig] = Field(..., min_length=1)
    scenarios: dict[str, ScenarioConfig] = Field(..., min_length=1)
    defaults: dict[str, float | int] = Field(
        default_factory=lambda: {"V0": 2.0, "months": 6, "N": 1000, "seed": 0}
    )
    
    @field_validator("scenarios")
    @classmethod
    def validate_scenario_regimes(cls, scenarios, info):
        """Ensure all scenario regimes reference defined regimes."""
        if "regimes" not in info.data:
            return scenarios
        
        regime_names = set(info.data["regimes"].keys())
        for scenario_name, scenario in scenarios.items():
            for segment in scenario.segments:
                if segment.regime not in regime_names:
                    raise ValueError(
                        f"Scenario '{scenario_name}' references undefined regime "
                        f"'{segment.regime}'. Available: {', '.join(regime_names)}"
                    )
        
        return scenarios
