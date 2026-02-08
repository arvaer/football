"""Configuration file loading and parsing.

Loads and validates YAML configuration files using Pydantic schemas.
"""

import yaml
from pathlib import Path
from valuation_pathways.config.schema import SimulationConfig


def load_config(config_path: str | Path) -> SimulationConfig:
    """Load and validate simulation configuration from YAML file.
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        Validated SimulationConfig object
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is malformed
        pydantic.ValidationError: If config doesn't match schema
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)
    
    return SimulationConfig(**raw_config)
