"""Dynamics models and regime definitions."""

from valuation_pathways.model.dynamics import RegimeSwitchingLogModel

# Model registry for string-based lookup
MODEL_REGISTRY: dict[str, type] = {
    "regime_switching_log": RegimeSwitchingLogModel,
}


def get_model(model_name: str):
    """Get a dynamics model class by name.
    
    Args:
        model_name: Name of the model (e.g., "regime_switching_log")
        
    Returns:
        Model class from registry
        
    Raises:
        ValueError: If model name not found in registry
    """
    if model_name not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(
            f"Unknown model '{model_name}'. Available models: {available}"
        )
    return MODEL_REGISTRY[model_name]
