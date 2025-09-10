"""
Flow State Generation
flow_state.py
====================

Generates dynamic state schemas based on tool parameter specifications.
This module creates state definitions using actual parameter names from tools.

Simple and focused: takes parameter names, creates state fields.
Type validation happens elsewhere during path generation.
"""

from typing import Any, Dict, List, Optional, TypedDict
from ..path.models import PathItem  # type: ignore


class StateGenerator:
    """
    Generates state schemas and initial states based on tool parameter specifications.
    
    Stores the schema internally for easy access and consistent state operations.
    Similar to LangGraph's StateGraph pattern.
    """
    
    def __init__(self, path_object: List[PathItem]):
        """
        Initialize the state generator with a path object.
        
        Args:
            path_object: Path object from path generation step
                        Format: [
                            {
                                "name": "denoise",
                                "description": "create a denoised version of the input audio file",
                                "input_params": ["input_file", "random_flag"], 
                                "output_params": ["output_file"],
                                "param_values": {"random_flag": false},  # Fixed values from path
                                "param_types": {"input_file": str, "random_flag": bool, "output_file": str}  # Actual types
                            }, ...
                        ]
        """
        self.path_object = path_object
        self.state_class, self.initial_state = self._setup_state_schema()
    
    def _setup_state_schema(self) -> tuple[type, Dict[str, Any]]:
        """Setup TypedDict class and initial state in one efficient loop."""
        # Build type annotations for TypedDict
        type_annotations = {
            "error_info": Optional[Dict[str, Any]],
            "execution_path": List[str],
            # Namespaced outputs cache for cross-step references like ${step.output}
            "outputs": Dict[str, Dict[str, Any]]
        }
        state: Dict[str, Any] = {
            "error_info": None,
            "execution_path": [],
            "outputs": {}
        }
        
        for tool_spec in self.path_object:
            # PathItem-based specs only
            param_types = tool_spec.param_types or {}
            param_values = tool_spec.param_values or {}
            input_params = tool_spec.input_params or []
            output_params = tool_spec.output_params or []

            # Process all parameters (input + output) in one loop
            all_params = input_params + output_params
            
            for param_name in all_params:
                # Get type (default to Any if not specified)
                param_type = param_types.get(param_name, Any)
                # Avoid forward-ref strings like 'BaseChatModel' causing NameError in get_type_hints
                if isinstance(param_type, str):
                    param_type = Any
                type_annotations[param_name] = param_type  # Add to TypedDict annotations
                
                # Set value with non-destructive semantics:
                # - If a fixed value is provided now, always apply it
                # - Otherwise, initialize to None only if the key is not present yet
                if param_name in param_values:
                    state[param_name] = param_values[param_name]
                else:
                    if param_name not in state:
                        state[param_name] = None
        
        # Create the actual TypedDict class using Method 1
        DynamicStateClass = TypedDict('DynamicState', type_annotations)
        
        return DynamicStateClass, state
    
    @property
    def state_schema(self) -> type:
        """
        Get the current state schema as a TypedDict class.
        
        Returns:
            TypedDict class with proper type annotations
        """
        return self.state_class
    
    @property
    def state_annotations(self) -> Dict[str, Any]:
        """
        Get the type annotations dictionary.
        
        Returns:
            Dictionary mapping parameter names to their types
        """
        return self.state_class.__annotations__.copy()
    
    @property
    def ready_state(self) -> Dict[str, Any]:
        """
        Get the initial state ready for execution.
        
        Returns:
            Initial state with all values from path object
        """
        return self.initial_state.copy()
    
    def get_final_output(self, state: Dict[str, Any]) -> Any:
        """
        Extract final output from completed state.
        
        Args:
            state: Completed execution state
            
        Returns:
            Value of the last tool's output parameter
        """
        if not self.path_object:
            return None
            
        # Get last tool's output parameter
        last_spec = self.path_object[-1]
        last_tool_outputs = last_spec.output_params or []
        if last_tool_outputs:
            return state.get(last_tool_outputs[0])
        
        return None


# Export the main class for LangGraph-style usage
__all__ = ['StateGenerator']