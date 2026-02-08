"""Tests for synthetic data sources."""

import pytest
from valuation_pathways.config.schema import SimulationConfig, RegimeConfig, ScenarioConfig, ScenarioSegment
from valuation_pathways.data.sources.synthetic_source import (
    StaticParameterProvider,
    ConfigScenarioProvider,
    ManualValuationProvider,
)


def test_static_parameter_provider():
    """Test StaticParameterProvider returns correct parameters."""
    config = SimulationConfig(
        regimes={
            "ecuador": RegimeConfig(mu=0.01, sigma=0.1),
            "brazil": RegimeConfig(mu=0.02, sigma=0.08),
        },
        scenarios={
            "test": ScenarioConfig(segments=[ScenarioSegment(regime="ecuador", months=6)])
        }
    )
    
    provider = StaticParameterProvider(config)
    
    ecuador_params = provider.get_parameters("ecuador")
    assert ecuador_params.mu == 0.01
    assert ecuador_params.sigma == 0.1
    
    with pytest.raises(KeyError, match="Unknown regime"):
        provider.get_parameters("unknown")


def test_config_scenario_provider():
    """Test ConfigScenarioProvider expands scenarios correctly."""
    config = SimulationConfig(
        regimes={"ecuador": RegimeConfig(mu=0.01, sigma=0.1)},
        scenarios={
            "test": ScenarioConfig(
                segments=[
                    ScenarioSegment(regime="ecuador", months=2),
                    ScenarioSegment(regime="ecuador", months=4),
                ]
            )
        }
    )
    
    provider = ConfigScenarioProvider(config, months=6)
    scenarios = provider.get_scenarios()
    
    assert "test" in scenarios
    assert scenarios["test"] == ["ecuador"] * 6
