"""
Tool Decorators - @pathtool/@tool decorator template for user tool definitions
Provides a lightweight decorator for users to mark functions as tools
"""

from typing import Any, Dict, Callable, Optional
import inspect


def pathtool(input: Optional[str] = None, 
             output: str = "return", 
             output_key_types: Optional[Dict[str, Any]] = None,
             requires: Optional[Dict[str, Any]] = None):
    """
    Decorator to mark functions as path tools and specify their type information
    
    This decorator attaches only minimal information (main input/output names and
    optional fixed params). The registry will infer types from annotations and
    build full PathToolMetadata objects.
    
    Usage:
    @pathtool(input="audio_path", output="return")
    def denoise(audio_path: AudioFile) -> AudioFile:
        ...
    
    Args:
        input: The primary input parameter name (auto-detected if None)
        output: The primary output parameter name or "return" (default)
        output_key_types: Optional type hints for dict output keys
        requires: Optional mapping of additional required inputs (param name -> type)
    
    Returns:
        Function with attached type information for registry discovery
    """
    def decorator(func: Callable) -> Callable:
        # Get function signature for validation
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        
        # Auto-detect main input parameter if not specified
        if input is None:
            detected_input = param_names[0] if param_names else None
        else:
            # Validate that specified parameter actually exists
            if input not in param_names:
                raise ValueError(
                    f"input '{input}' not found in function '{func.__name__}'. "
                    f"Available parameters: {param_names}"
                )
            detected_input = input
        
        # Note: output can be 'return' (use function return) or a key within a
        # returned mapping (e.g., TypedDict or dict). We do not enforce presence here.
        
        # Attach basic tool information (registry will create full metadata)
        func._tool_input_key = detected_input
        func._tool_output_key = output
        if output_key_types:
            func._tool_output_key_types = dict(output_key_types)
        if requires:
            func._tool_required_inputs = dict(requires)
        func._is_tool = True
        
        return func
    return decorator

# Backwards-compatible alias
tool = pathtool

