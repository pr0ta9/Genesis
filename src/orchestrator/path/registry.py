"""
Tool Registry - Minimal implementation for path tools
Fast AST-based discovery without importing heavy dependencies
"""

from typing import Dict, List, Optional, Any
import ast
from pathlib import Path
import importlib
from .metadata import PathToolMetadata
from . import metadata as _metadata_module


class ToolRegistry:
    """Registry for path tools with lazy loading via AST parsing"""
    
    def __init__(self):
        self.tools: Dict[str, PathToolMetadata] = {}
        self.type_graph: Dict[str, List[str]] = {}  # input_type -> [tool_names]
        
    def register_tool(self, tool_meta: PathToolMetadata):
        """Register a tool in the registry"""
        self.tools[tool_meta.name] = tool_meta
        
        # Update type graph for path finding
        input_type = tool_meta.param_types.get(tool_meta.input_key)
        if input_type:
            if input_type not in self.type_graph:
                self.type_graph[input_type] = []
            self.type_graph[input_type].append(tool_meta.name)
    
    def get_tools_for_input_type(self, input_type: str) -> List[PathToolMetadata]:
        """Get all tools that can process a given input type"""
        tool_names = self.type_graph.get(input_type, [])
        return [self.tools[name] for name in tool_names]
    
    def get_tool(self, name: str) -> Optional[PathToolMetadata]:
        """Get tool metadata by name"""
        return self.tools.get(name)
    
    def get_executable_function(self, tool_name: str):
        """Load the actual function when needed for execution"""
        tool = self.tools.get(tool_name)
        if not tool:
            raise KeyError(f"Tool '{tool_name}' not registered")
        
        # Only import when actually executing
        if tool.function is None:
            if not hasattr(tool, '_module_name'):
                raise RuntimeError(f"Tool '{tool_name}' has no module information")
            
            module = importlib.import_module(tool._module_name)
            tool.function = getattr(module, tool.name)
        
        return tool.function
    
    def auto_register_from_directory(self, directory: str, recursive: bool = True):
        """Scan directory for tools using AST parsing - no imports"""
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"Warning: Directory {directory} does not exist")
            return
            
        pattern = "**/*.py" if recursive else "*.py"
        
        for py_file in dir_path.glob(pattern):
            if py_file.name.startswith("_"):
                continue
                
            tools = self._extract_tools_from_source(py_file)
            for tool_meta in tools:
                try:
                    self._register_tool_from_ast(tool_meta)
                    print(f"  Registered tool: {tool_meta['name']}")
                except Exception as e:
                    print(f"  Error registering {tool_meta.get('name', 'unknown')}: {e}")

    def _extract_tools_from_source(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Python file and extract tool metadata"""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            return []

        tools = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorator_info = self._get_decorator_info(node)
                if decorator_info is not None:
                    meta = self._build_tool_metadata(node, file_path, decorator_info)
                    if meta:
                        tools.append(meta)
        return tools

    def _get_decorator_info(self, func_node: ast.FunctionDef) -> Optional[Dict[str, Any]]:
        """Check if function has @pathtool or @tool decorator"""
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id in ("pathtool", "tool"):
                    return self._extract_decorator_args(decorator)
            elif isinstance(decorator, ast.Name) and decorator.id in ("pathtool", "tool"):
                return {}  # Decorator with no arguments
        return None

    def _extract_decorator_args(self, decorator: ast.Call) -> Dict[str, Any]:
        """Extract keyword arguments from decorator"""
        args = {}
        for kw in decorator.keywords:
            if not kw.arg:
                continue
            
            # Handle 'requires' dict specially
            if kw.arg == "requires" and isinstance(kw.value, ast.Dict):
                reqs = {}
                for k, v in zip(kw.value.keys, kw.value.values):
                    if isinstance(k, ast.Constant):
                        key = k.value
                    else:
                        continue
                    reqs[key] = self._ast_to_string(v)
                args[kw.arg] = reqs
            else:
                try:
                    args[kw.arg] = ast.literal_eval(kw.value)
                except Exception:
                    args[kw.arg] = self._ast_to_string(kw.value)
        return args

    def _build_tool_metadata(self, func_node: ast.FunctionDef, file_path: Path, decorator_args: Dict) -> Dict[str, Any]:
        """Build tool metadata from AST node"""
        # Extract parameters and their types
        params = []
        param_types = {}
        
        for arg in func_node.args.args:
            params.append(arg.arg)
            if arg.annotation:
                param_types[arg.arg] = self._ast_to_string(arg.annotation)
        
        # Extract return type
        return_type = None
        if func_node.returns:
            return_type = self._ast_to_string(func_node.returns)
        
        # Determine input/output keys
        input_key = decorator_args.get("input", params[0] if params else None)
        output_key = decorator_args.get("output", "return")
        
        return {
            "name": func_node.name,
            "module_name": self._path_to_module(file_path),
            "description": ast.get_docstring(func_node) or f"Execute {func_node.name}",
            "params": params,
            "param_types": param_types,
            "return_type": return_type,
            "input_key": input_key,
            "output_key": output_key,
            "requires": decorator_args.get("requires", {}),
        }

    def _ast_to_string(self, node: ast.AST) -> str:
        """Convert AST node to string representation"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        if hasattr(ast, "unparse"):
            return ast.unparse(node)
        return "Any"

    def _path_to_module(self, path: Path) -> str:
        """Convert file path to module name"""
        parts = path.resolve().parts
        try:
            idx = parts.index("src")
            module_parts = list(parts[idx:])
            module_parts[-1] = Path(module_parts[-1]).stem
            return ".".join(module_parts)
        except ValueError:
            return path.stem

    def _resolve_type(self, type_name: str) -> Optional[type]:
        """Resolve type string to actual type"""
        if not type_name:
            return None
            
        # Check builtins
        builtins = {"dict": dict, "str": str, "int": int, "float": float, "bool": bool, "list": list}
        if type_name in builtins:
            return builtins[type_name]
        
        # Check metadata module for WorkflowType subclasses
        try:
            return getattr(_metadata_module, type_name, None)
        except AttributeError:
            return None

    def _register_tool_from_ast(self, meta: Dict[str, Any]):
        """Create and register PathToolMetadata from AST metadata"""
        # Prepare parameters
        params = meta["params"]
        input_key = meta["input_key"]
        
        # Ensure input_key is first in params
        if input_key and input_key in params and params[0] != input_key:
            params.remove(input_key)
            params.insert(0, input_key)
        
        # Resolve types
        param_types = {}
        for param, type_str in meta["param_types"].items():
            resolved = self._resolve_type(type_str)
            if resolved:
                param_types[param] = resolved
        
        # Handle return type
        if meta["output_key"] == "return" and meta.get("return_type"):
            resolved = self._resolve_type(meta["return_type"])
            if resolved:
                param_types["return"] = resolved
        
        # Resolve required inputs
        required_inputs = {}
        for param, type_str in meta.get("requires", {}).items():
            resolved = self._resolve_type(type_str)
            if resolved:
                required_inputs[param] = resolved
        
        # Extract default values for parameters (predefined params)
        default_params: Dict[str, Any] = {}
        # We can recover defaults from AST by matching function args and defaults
        # Re-parse defaults here using the original file for this function node is already parsed
        # The meta dict does not include defaults, so reconstruct by locating the function again
        # Simpler approach: read the file again and parse only this function signature
        # Note: For robustness, ignore failures and leave defaults empty
        try:
            file_path = Path(self._module_name_to_path(meta["module_name"]))
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == meta["name"]:
                    args = node.args
                    # Align defaults to the end of positional args
                    pos_args = list(args.args)
                    defaults = list(args.defaults)
                    if defaults and pos_args:
                        start = len(pos_args) - len(defaults)
                        for i, d in enumerate(defaults):
                            param_name = pos_args[start + i].arg
                            try:
                                value = ast.literal_eval(d)
                            except Exception:
                                value = self._ast_to_string(d)
                            default_params[param_name] = value
                    # Keyword-only defaults
                    for kw, d in zip(getattr(args, 'kwonlyargs', []), getattr(args, 'kw_defaults', []) or []):
                        if d is not None:
                            try:
                                value = ast.literal_eval(d)
                            except Exception:
                                value = self._ast_to_string(d)
                            default_params[kw.arg] = value
                    break
        except Exception:
            default_params = {}

        # Create metadata object
        tool_metadata = PathToolMetadata(
            name=meta["name"],
            function=None,  # Lazy load later
            description=meta["description"],
            input_key=input_key,
            output_key=meta["output_key"],
            input_params=params,
            output_params=[meta["output_key"]] if meta["output_key"] != "return" else ["return"],
            param_types=param_types,
            required_inputs=required_inputs,
            default_params=default_params,
        )
        
        # Store module info for lazy loading
        tool_metadata._module_name = meta["module_name"]
        self.register_tool(tool_metadata)

    def _module_name_to_path(self, module_name: str) -> str:
        parts = module_name.split('.')
        # Assume project structure with top-level 'src'
        try:
            idx = parts.index('src')
            relative = Path(*parts[idx:])
        except ValueError:
            relative = Path(*parts)

        # Detect project root containing the top-level 'src' directory
        def _detect_project_root() -> Path:
            here = Path(__file__).resolve()
            for parent in here.parents:
                if (parent / 'src').exists():
                    return parent
            # Fallback to current working directory
            return Path.cwd()

        project_root = _detect_project_root()
        abs_path = (project_root / relative).with_suffix('.py')
        print(f"[Registry Debug] _module_name_to_path -> module='{module_name}' abs='{abs_path}' exists={abs_path.exists()}")
        return str(abs_path)