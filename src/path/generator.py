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
        Provenance-aware path enumeration from input_type to output_type.
        1) enumerating sequences while recording which provider supplies each required type
        2) filtering to strict-contribution paths (every earlier tool is actually consumed)
        3) canonicalizing sequences by provider→consumer DAG with the final tool fixed last
        4) deduplicating canonical paths

        Returns a list of paths where each path is a list of PathToolMetadata objects
        ordered by the canonical topological order.
        """
        START = "__START__"

        # Helper: choose a concrete available type to satisfy a required type deterministically
        def _select_provider_type(available_types: Set[Type], required_type: Type) -> Type:
            # Prefer exact type match if present; otherwise fall back to a deterministic choice
            if required_type in available_types:
                return required_type
            compatible = [t for t in available_types if is_type_compatible(t, required_type)]
            if not compatible:
                raise RuntimeError("No compatible available type to satisfy requirement")
            # Deterministic tie-breaker: type name then repr
            compatible.sort(key=lambda t: (getattr(t, '__name__', str(t)), str(t)))
            return compatible[0]

        # Helper: strict contribution check (final tool must output target; all earlier tools used later)
        def _contributes(seq: List[PathToolMetadata], bindings: List[Dict[str, str]]) -> bool:
            if not seq:
                return False
            final_out = seq[-1].param_types.get(seq[-1].output_key)
            if final_out != output_type:
                return False
            n = len(seq)
            for i, tool in enumerate(seq[:-1]):
                used_later = any(tool.name in bindings[j].values() for j in range(i + 1, n))
                if not used_later:
                    return False
            return True

        # Helper: canonicalize by dependency DAG induced from actual bindings
        def _canonicalize_by_edges(seq: List[PathToolMetadata], bindings: List[Dict[str, str]]) -> List[str]:
            import heapq
            names = [t.name for t in seq]
            final_name = names[-1]

            # Build edges provider→consumer (exclude START)
            edges: Set[Tuple[str, str]] = set()
            for j, tool in enumerate(seq):
                for prov in bindings[j].values():
                    if prov != START:
                        edges.add((prov, tool.name))

            # Topo sort excluding the final node (we will append it last)
            nodes_set = set(names)
            nodes_set.discard(final_name)

            in_deg: Dict[str, int] = {u: 0 for u in nodes_set}
            adj: Dict[str, List[str]] = {u: [] for u in nodes_set}
            for u, v in edges:
                if v == final_name:
                    continue
                if u in nodes_set and v in nodes_set:
                    adj[u].append(v)
                    in_deg[v] += 1

            heap = [u for u, d in in_deg.items() if d == 0]
            heapq.heapify(heap)
            order: List[str] = []
            while heap:
                u = heapq.heappop(heap)
                order.append(u)
                for w in adj.get(u, []):
                    in_deg[w] -= 1
                    if in_deg[w] == 0:
                        heapq.heappush(heap, w)

            if len(order) != len(nodes_set):
                # Fallback to original order if something unexpected happens
                order = [n for n in names if n != final_name]

            order.append(final_name)
            return order

        # Enumerate sequences with provenance bindings
        enumerated: List[Tuple[List[PathToolMetadata], List[Dict[str, str]]]] = []

        # Use a fixed list of remaining tools to mirror the "no reuse" constraint
        all_tools: List[PathToolMetadata] = list(self.registry.tools.values())

        def dfs(
            available_types: Set[Type],
            provider_of: Dict[Type, str],
            remaining_tools: List[PathToolMetadata],
            seq: List[PathToolMetadata],
            binds: List[Dict[str, str]]
        ) -> None:
            # Record completed path only if the last tool outputs the target type
            if seq:
                last_out = seq[-1].param_types.get(seq[-1].output_key)
                if last_out == output_type:
                    enumerated.append((seq[:], [b.copy() for b in binds]))

            # Depth limit
            if len(seq) >= max_depth:
                return

            # Determine ready tools
            ready: List[PathToolMetadata] = []
            for tool in remaining_tools:
                in_type = tool.param_types.get(tool.input_key)
                # Must have at least one available type compatible with main input
                if not any(is_type_compatible(av_t, in_type) for av_t in available_types):
                    continue
                # All required inputs must be satisfiable by current available types
                req_types: List[Type] = list(tool.required_inputs.values()) if tool.required_inputs else []
                if any(not any(is_type_compatible(av_t, req_t) for av_t in available_types) for req_t in req_types):
                    continue
                ready.append(tool)

            # Deterministic order by tool name
            ready.sort(key=lambda t: t.name)

            for tool in ready:
                in_type = tool.param_types.get(tool.input_key)

                # Bind to current providers for required types using a deterministic selection
                try:
                    bound_main_type = _select_provider_type(available_types, in_type)
                except Exception:
                    continue
                consumption: Dict[str, str] = {getattr(in_type, '__name__', str(in_type)): provider_of[bound_main_type]}

                if tool.required_inputs:
                    for req_param, req_t in tool.required_inputs.items():
                        try:
                            bound_req_type = _select_provider_type(available_types, req_t)
                        except Exception:
                            bound_req_type = None
                        if bound_req_type is None:
                            consumption[getattr(req_t, '__name__', str(req_t))] = START
                        else:
                            consumption[getattr(req_t, '__name__', str(req_t))] = provider_of[bound_req_type]

                # Apply tool: latest-wins provider and extend available types
                next_available = set(available_types)
                out_type = tool.param_types.get(tool.output_key)
                next_available.add(out_type)
                next_provider = dict(provider_of)
                next_provider[out_type] = tool.name

                next_remaining = [t for t in remaining_tools if t is not tool]
                dfs(next_available, next_provider, next_remaining, seq + [tool], binds + [consumption])

        dfs({input_type}, {input_type: START}, all_tools[:], [], [])

        # Filter to strict-contribution paths
        filtered: List[Tuple[List[PathToolMetadata], List[Dict[str, str]]]] = [
            (seq, b) for (seq, b) in enumerated if _contributes(seq, b)
        ]

        # Canonicalize and deduplicate
        seen: Set[Tuple[str, ...]] = set()
        canonical_paths: List[List[PathToolMetadata]] = []
        for seq, b in filtered:
            order = _canonicalize_by_edges(seq, b)
            key = tuple(order)
            if key in seen:
                continue
            seen.add(key)
            # Reorder the actual tool objects to match canonical order
            name_to_tool: Dict[str, PathToolMetadata] = {t.name: t for t in seq}
            canonical_paths.append([name_to_tool[n] for n in order])

        # Sort by (length, tool name list) for stable output
        def _sort_key(path: List[PathToolMetadata]):
            return (len(path), [t.name for t in path])

        canonical_paths.sort(key=_sort_key)
        return canonical_paths
    
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
