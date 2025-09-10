from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SimplePath(BaseModel):
    """Simple path step from LLM with just name and param_values."""
    name: str
    param_values: Dict[str, Any] = Field(default_factory=dict)


class PathItem(BaseModel):
    """Complete path step with all metadata populated from registry."""
    name: str
    description: str
    function: Optional[Any] = None  # Will be resolved during execution
    input_params: List[str]
    output_params: List[str]
    param_values: Dict[str, Any]
    param_types: Dict[str, Any]


__all__ = ["SimplePath", "PathItem"]


