"""
Tool Registry - Tool storage and discovery system
Discovers @pathtool/@tool decorated functions and converts them to ToolMetadata objects
"""

from typing import Dict, List, Optional, Callable, Any
import importlib
import inspect
from .metadata import PathToolMetadata, WorkflowType


class ToolRegistry:
    """Registry for all available tools with their metadata"""
    
    def __init__(self):
        self.tools: Dict[str, PathToolMetadata] = {}
        self.type_graph: Dict[str, List[str]] = {}  # input_type -> [tool_names]
        
    def register_tool(self, tool_meta: PathToolMetadata):
        """Register a tool in the registry"""
        self.tools[tool_meta.name] = tool_meta
        
        # Update type graph
        input_type = tool_meta.param_types[tool_meta.input_key]
        if input_type not in self.type_graph:
            self.type_graph[input_type] = []
        self.type_graph[input_type].append(tool_meta.name)
        
    def get_tools_for_input_type(self, input_type: str) -> List[PathToolMetadata]:
        """Get all tools that can process a given input type"""
        tool_names = self.type_graph.get(input_type)
        if tool_names is None:
            # No tools found for this type
            return []
        return [self.tools[name] for name in tool_names]
    
    def get_tool(self, name: str) -> Optional[PathToolMetadata]:
        """Get tool metadata by name"""
        return self.tools.get(name)
    
    def _create_tool_metadata(self, func: Callable) -> PathToolMetadata:
        """Convert a @pathtool/@tool decorated function into PathToolMetadata"""
        # Extract information attached by the @tool decorator
        input_key = func._tool_input_key
        output_key = func._tool_output_key
        
        # Validate output_key
        if not output_key or output_key.strip() == "":
            raise ValueError(
                f"Tool '{func.__name__}' has empty or missing output_key. "
                f"Specify @pathtool(output='return') or @pathtool(output='key_name')"
            )
        
        # Analyze function signature
        sig = inspect.signature(func)
        type_hints = getattr(func, '__annotations__', {})
        param_names = list(sig.parameters.keys())
        
        # Validate main input type presence in annotations
        if input_key:
            if type_hints.get(input_key) is None:
                raise ValueError(
                    f"Tool '{func.__name__}' parameter '{input_key}' missing type annotation. "
                    f"Add type hint: def {func.__name__}({input_key}: YourType, ...)"
                )
        else:
            raise ValueError(
                f"Tool '{func.__name__}' has no input_key. This should not happen."
            )
        
        # Validate main output type is resolvable
        if output_key == "return":
            if type_hints.get('return') is None:
                raise ValueError(
                    f"Tool '{func.__name__}' missing return type annotation. "
                    f"Add return type: def {func.__name__}(...) -> YourType:"
                )
        else:
            # When output is a key in returned dict, we MUST have explicit type info
            if not (hasattr(func, '_tool_output_key_types') and output_key in func._tool_output_key_types):
                raise ValueError(
                    f"Tool '{func.__name__}' specifies output_key='{output_key}' but missing "
                    f"output_key_types specification. When returning a dict key, you must specify "
                    f"the type: @pathtool(output='{output_key}', output_key_types={{'{output_key}': YourType}})"
                )

        # Determine input/output parameters
        input_params = [input_key] if input_key else []
        other_params = [name for name in param_names if name != input_key]
        input_params.extend(other_params)
        
        output_params = [output_key] if output_key != "return" else ["return"]
        
        # Get parameter types
        param_types = {}
        for param_name in param_names:
            param = sig.parameters[param_name]
            param_type = type_hints.get(param_name)
            
            # For required parameters (no default), type annotation is mandatory
            if param.default == inspect.Parameter.empty and param_type is None:
                raise ValueError(
                    f"Tool '{func.__name__}' parameter '{param_name}' missing type annotation. "
                    f"Add type hint or provide default value."
                )
            
            # For optional parameters, we can infer type from default if no annotation
            if param_type is None and param.default != inspect.Parameter.empty:
                param_type = type(param.default)
            
            if param_type is not None:
                param_types[param_name] = param_type
        
        # Add return type
        if "return" in output_params:
            return_type = type_hints.get('return')
            if return_type is None:
                raise ValueError(
                    f"Tool '{func.__name__}' missing return type annotation. "
                    f"Add return type: def {func.__name__}(...) -> YourType:"
                )
            param_types["return"] = return_type

        # Capture declared additional required inputs (multi-input)
        required_inputs: Dict[str, Any] = {}
        if hasattr(func, '_tool_required_inputs'):
            # Validate that required inputs exist in signature and types match
            declared: Dict[str, Any] = getattr(func, '_tool_required_inputs')
            for req_param, req_type in declared.items():
                if req_param not in param_names:
                    raise ValueError(
                        f"Tool '{func.__name__}' declares required input '{req_param}' "
                        f"but it is not a parameter of the function. "
                        f"Available parameters: {param_names}"
                    )
                annotated_type = type_hints.get(req_param)
                if annotated_type is None:
                    raise ValueError(
                        f"Tool '{func.__name__}' required input '{req_param}' must have a type annotation."
                    )
                if annotated_type is not req_type:
                    raise ValueError(
                        f"Tool '{func.__name__}' required input '{req_param}' type mismatch. "
                        f"Declared {getattr(req_type,'__name__',req_type)}, annotated "
                        f"{getattr(annotated_type,'__name__',annotated_type)}"
                    )
                required_inputs[req_param] = req_type
        
        return PathToolMetadata(
            name=func.__name__,
            function=func,
            description=func.__doc__ or f"Execute {func.__name__}",
            input_key=input_key,
            output_key=output_key,
            input_params=input_params,
            output_params=output_params,
            param_types=param_types,
            required_inputs=required_inputs
        )
    
    def auto_register_from_module(self, module_name: str):
        """Discover @pathtool/@tool decorated functions and convert them to PathToolMetadata"""
        try:
            module = importlib.import_module(module_name)
            
            # Find all functions in the module that are decorated as tools
            for name in dir(module):
                obj = getattr(module, name)
                if (callable(obj) and hasattr(obj, '_is_tool')):
                    # Convert decorated function to full PathToolMetadata
                    tool_metadata = self._create_tool_metadata(obj)
                    self.register_tool(tool_metadata)
                    print(f"  Auto-registered tool: {tool_metadata.name}")
        except ImportError as e:
            print(f"Could not import module {module_name}: {e}")
        except AttributeError as e:
            print(f"Error processing tool in {module_name}: {e}")
    
    def list_tools(self) -> Dict[str, str]:
        """Get a summary of all registered tools"""
        return {
            name: f"{meta.param_types[meta.input_key].__name__} → {meta.param_types[meta.output_key].__name__}"
            for name, meta in self.tools.items()
        }
    
    def get_available_types(self) -> List[str]:
        """Get all available input and output types"""
        types = set()
        for tool in self.tools.values():
            # Convert types to strings for sorting
            input_type = tool.param_types[tool.input_key]
            output_type = tool.param_types[tool.output_key]
            input_type_str = getattr(input_type, '__name__', str(input_type))
            output_type_str = getattr(output_type, '__name__', str(output_type))
            types.add(input_type_str)
            types.add(output_type_str)
        return sorted(list(types))
    
    def get_tools_by_type_pair(self, input_type: str, output_type: str) -> List[PathToolMetadata]:
        """Get all tools that directly transform input_type to output_type"""
        return [
            tool for tool in self.tools.values()
            if tool.param_types[tool.input_key] == input_type and tool.param_types[tool.output_key] == output_type
        ]
    
    def export_type_graph(self) -> Dict[str, Dict[str, List[str]]]:
        """Export the complete type transformation graph"""
        graph = {}
        for input_type, tool_names in self.type_graph.items():
            graph[input_type] = {}
            for tool_name in tool_names:
                tool = self.tools[tool_name]
                output_type = tool.param_types[tool.output_key]
                if output_type not in graph[input_type]:
                    graph[input_type][output_type] = []
                graph[input_type][output_type].append(tool_name)
        return graph
