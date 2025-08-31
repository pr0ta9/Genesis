"""
Path Generator - Core pathfinding algorithm for Type-Based Routing
Contains the main algorithm that discovers all possible tool paths between types
"""

from typing import List, Set, Dict, Any, Type, Union, Tuple
import json
from .registry import ToolRegistry
from .metadata import PathToolMetadata, WorkflowType


# =============================================================================
# TYPE COMPATIBILITY CHECKING FUNCTIONS
# =============================================================================

def is_type_compatible(output_type: Type, input_type: Type) -> bool:
    """
    Check if output_type can be used as input_type
    
    Only supports class-based type checking
    """
    if not isinstance(output_type, type) or not isinstance(input_type, type):
        raise ValueError(f"Only type classes supported. Got: {output_type}, {input_type}")
    
    # Check if it's a WorkflowType with is_compatible_with method
    if hasattr(output_type, 'is_compatible_with'):
        try:
            return output_type.is_compatible_with(input_type)
        except Exception as e:
            raise ValueError(
                f"Error checking compatibility between {output_type.__name__} "
                f"and {input_type.__name__}: {str(e)}"
            )
    
    # For regular Python types, use simple equality
    return output_type == input_type


def check_dict_key_compatibility(output_tool: PathToolMetadata, input_tool: PathToolMetadata) -> bool:
    """
    Check if output tool's dict output contains the key needed by input tool
    
    This is used when:
    1. Output tool returns a dict
    2. Input tool expects a specific value from that dict
    """
    # Check if both tools work with dicts
    out_type = output_tool.param_types.get(output_tool.output_key)
    output_is_dict = (out_type == dict or 
                      (hasattr(out_type, '__name__') and 
                       'dict' in str(out_type).lower()))
    
    if not output_is_dict:
        return False
    
    # If output specifies a key (output_key != "return"), 
    # then that's the value being passed, not the whole dict
    if output_tool.output_key != "return":
        # Output tool provides a specific value from dict
        # Check if types are compatible
        out_type = output_tool.param_types.get(output_tool.output_key)
        in_type = input_tool.param_types.get(input_tool.input_key)
        return is_type_compatible(out_type, in_type)
    
    # If output returns whole dict, we cannot verify compatibility without runtime inspection
    # This is an error in tool design - tools should specify output keys
    raise ValueError(
        f"Cannot verify compatibility: Tool '{output_tool.name}' returns entire dict "
        f"but '{input_tool.name}' expects specific type '{input_tool.param_types[input_tool.input_key]}'. "
        f"Use @pathtool(output='key_name') to specify which dict value to pass."
    )


def get_type_info(workflow_type: Type[WorkflowType]) -> Dict[str, Any]:
    """
    Extract basic information from a WorkflowType class
    
    Returns:
        Dictionary with type information for debugging/display
    """
    info = {
        'type_name': workflow_type.__name__,
        'base_type': workflow_type.__bases__[0].__name__ if workflow_type.__bases__ else 'WorkflowType'
    }
    
    # File type information
    if hasattr(workflow_type, 'valid_extensions'):
        info['valid_extensions'] = list(workflow_type.valid_extensions)
    
    return info


def validate_tool_data_flow(tools: List[PathToolMetadata]) -> List[Dict[str, Any]]:
    """
    Validate that data can flow through a sequence of tools
    
    Returns:
        List of validation results for each connection in the path
    """
    if len(tools) < 2:
        return []
    
    validation_results = []
    
    for i in range(len(tools) - 1):
        current_tool = tools[i]
        next_tool = tools[i + 1]
        
        in_type = next_tool.param_types.get(next_tool.input_key)
        out_type = current_tool.param_types.get(current_tool.output_key)
        result = {
            'from_tool': current_tool.name,
            'to_tool': next_tool.name,
            'output_type': out_type,
            'input_type': in_type,
            'compatible': is_type_compatible(out_type, in_type)
        }
        
        validation_results.append(result)
    
    return validation_results


class PathGenerator:
    """Generates all possible paths between input and output types"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        
    def find_all_paths(self, input_type: Type, output_type: Type, max_depth: int = 5) -> List[List[PathToolMetadata]]:
        """
        Find all valid paths from input_type to output_type
        Uses DFS to avoid infinite loops and ensures no tool is used twice in a path
        
        Args:
            input_type: Starting type class for the transformation
            output_type: Target type class to reach
            max_depth: Maximum number of tools in a path
            
        Returns:
            List of paths, where each path is a list of PathToolMetadata objects
        """
        all_paths: List[List[PathToolMetadata]] = []

        # DFS over a set of available types (enables multi-input prerequisites)
        def dfs_available(
            available_types: Set[Type],
            current_path: List[PathToolMetadata],
            visited_tools: Set[str]
        ) -> None:
            # Goal check: if desired output type is available
            if output_type in available_types and current_path:
                all_paths.append(current_path.copy())
                # Do not return immediately; allow discovering alternative continuations
            
            # Depth limit
            if len(current_path) >= max_depth:
                return

            # Try all tools; they can run if their main input type is available
            for tool in self.registry.tools.values():
                if tool.name in visited_tools:
                    continue

                # Main input compatibility: any available type must satisfy tool's input type
                in_type = tool.param_types.get(tool.input_key)
                if not any(is_type_compatible(av_t, in_type) for av_t in available_types):
                    continue

                # Check additional required inputs types are present
                if tool.required_inputs:
                    # All required input types must be present in available_types
                    missing = [p for p, t in tool.required_inputs.items()
                               if not any(is_type_compatible(av_t, t) for av_t in available_types)]
                    if missing:
                        # Cannot execute this tool yet
                        continue

                # If previous step outputs a dict key, compatibility was already handled by type check above

                # Apply tool: add its output type to available types
                next_available: Set[Type] = set(available_types)
                out_type = tool.param_types.get(tool.output_key)
                next_available.add(out_type)

                dfs_available(
                    next_available,
                    current_path + [tool],
                    visited_tools | {tool.name}
                )

        # Start with the initial available type set containing the input type
        dfs_available({input_type}, [], set())
        return all_paths
    
    def find_shortest_path(self, input_type: Type, output_type: Type) -> List[PathToolMetadata]:
        """Find the shortest path between two types"""
        all_paths = self.find_all_paths(input_type, output_type)
        if not all_paths:
            return []
        return min(all_paths, key=len)
    
    def find_paths_with_tool(self, input_type: Type, output_type: Type, required_tool: str) -> List[List[PathToolMetadata]]:
        """Find all paths that include a specific tool"""
        all_paths = self.find_all_paths(input_type, output_type)
        return [path for path in all_paths if any(tool.name == required_tool for tool in path)]
    
    def get_path_summary(self, path: List[PathToolMetadata]) -> Dict[str, Any]:
        """Get a summary of a path including types and tools"""
        if not path:
            return {"tools": [], "types": [], "length": 0}
        
        tools = [tool.name for tool in path]
        def _type_name(t: Any) -> str:
            try:
                return t if isinstance(t, str) else getattr(t, '__name__', str(t))
            except Exception:
                return str(t)
        first_in = path[0].param_types.get(path[0].input_key)
        types = [first_in] + [t.param_types.get(t.output_key) for t in path]
        types_str = [_type_name(t) for t in types]
        
        return {
            "tools": tools,
            "types": types_str,
            "length": len(path),
            "tool_chain": " → ".join(tools),
            "type_flow": " → ".join(types_str)
        }
    
    def paths_to_dict(self, paths: List[List[PathToolMetadata]]) -> List[List[Dict[str, Any]]]:
        """Convert paths to dictionary format as specified in yoruzuya.md"""
        return [
            [tool.to_dict() for tool in path]
            for path in paths
        ]
    
    def validate_path_with_types(self, path: List[PathToolMetadata]) -> Dict[str, Any]:
        """
        Validate a path using the new type system
        
        Returns detailed validation information including type compatibility
        """
        if not path:
            return {'valid': True, 'details': 'Empty path'}
        
        validation_results = validate_tool_data_flow(path)
        
        # Overall path validity
        all_compatible = all(result['compatible'] for result in validation_results)
        
        return {
            'valid': all_compatible,
            'connection_count': len(validation_results),
            'connections': validation_results,
            'path_summary': {
                'tool_chain': [tool.name for tool in path],
                'type_chain': [path[0].param_types.get(path[0].input_key)] + [
                    t.param_types.get(t.output_key) for t in path
                ]
            }
        }
    
    def analyze_workflow_complexity(self, input_type: Type, output_type: Type) -> Dict[str, Any]:
        """Analyze the complexity of workflows between two types"""
        paths = self.find_all_paths(input_type, output_type)
        
        if not paths:
            return {
                "possible": False,
                "path_count": 0,
                "min_steps": 0,
                "max_steps": 0,
                "avg_steps": 0
            }
        
        path_lengths = [len(path) for path in paths]
        
        return {
            "possible": True,
            "path_count": len(paths),
            "min_steps": min(path_lengths),
            "max_steps": max(path_lengths),
            "avg_steps": sum(path_lengths) / len(path_lengths),
            "direct_tools": len([p for p in paths if len(p) == 1]),
            "complexity": "Simple" if max(path_lengths) <= 2 else "Complex"
        }


def setup_tool_registry() -> ToolRegistry:
    """
    Setup the tool registry with auto-discovery of decorated tools
    
    Returns:
        Configured ToolRegistry instance
    """
    registry = ToolRegistry()
    
    # Auto-register all decorated tools from the tools module
    registry.auto_register_from_module('decorated_tools')
    
    return registry


def demonstrate_path_generation():
    """
    Demonstration function showing path generation capabilities
    
    Note: This is a demo function. For production use, call setup_tool_registry()
    and create PathGenerator instances directly.
    """
    from .registry import ToolRegistry
    from .metadata import AudioFile, ImageFile, TextFile
    
    registry = setup_tool_registry()
    generator = PathGenerator(registry)
    
    # Example usage - find paths between types
    audio_paths = generator.find_all_paths(AudioFile, AudioFile)
    image_paths = generator.find_all_paths(ImageFile, ImageFile)
    
    return {
        'registry': registry,
        'generator': generator,
        'example_paths': {
            'audio_to_audio': audio_paths,
            'image_to_image': image_paths
        }
    }
