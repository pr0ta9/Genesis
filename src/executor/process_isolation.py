"""
process_isolation.py
Enhanced Process Isolation with File-Based State
================================================

Runs tools in separate processes using JSON file for state persistence,
with special handling for non-serializable objects like LLM instances.
"""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import json
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, Set
from ..path.models import PathItem  # type: ignore
import uuid


# Tools that should be isolated in SMART mode
ISOLATED_TOOL_MAP: Dict[str, Tuple[str, str]] = {
    "erase": ("src.tools.path_tools.erase", "erase"),
    "image_ocr": ("src.tools.path_tools.ocr", "image_ocr"),
    "translate": ("src.tools.path_tools.translate", "translate"),
    "inpaint_text": ("src.tools.path_tools.inpaint_text", "inpaint_text"),
}

# Parameter types that cannot be serialized to JSON
NON_SERIALIZABLE_TYPES = {
    "BaseChatModel",
    "BaseLanguageModel", 
    "LLM",
    "ChatOpenAI",
    "ChatAnthropic",
}


class StateStore:
    """Manages file-based state persistence between tool executions."""
    
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.state_file = workspace_dir / "execution_state.json"
        self.pickled_objects_dir = workspace_dir / "pickled_objects"
        self.pickled_objects_dir.mkdir(exist_ok=True)
        
        # Initialize empty state
        if not self.state_file.exists():
            self._save_state({})
    
    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save state to JSON file."""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from JSON file."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}
    
    def get(self, key: str) -> Any:
        """Get value from state store."""
        state = self._load_state()
        return state.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in state store."""
        state = self._load_state()
        
        # Check if value is JSON-serializable
        try:
            json.dumps(value)
            state[key] = value
        except (TypeError, ValueError):
            # For non-serializable objects, store a reference
            pickle_id = str(uuid.uuid4())
            pickle_path = self.pickled_objects_dir / f"{pickle_id}.pkl"
            with open(pickle_path, 'wb') as f:
                pickle.dump(value, f)
            state[key] = {"__pickle_ref__": str(pickle_path)}
        
        self._save_state(state)
    
    def get_pickled(self, key: str) -> Any:
        """Get a pickled object from store."""
        state = self._load_state()
        value = state.get(key)
        if isinstance(value, dict) and "__pickle_ref__" in value:
            with open(value["__pickle_ref__"], 'rb') as f:
                return pickle.load(f)
        return value


def resolve_isolation_mode() -> str:
    """Return isolation mode from environment: none | smart | all."""
    mode = os.environ.get("GENESIS_ISOLATION_MODE", "smart").strip().lower()
    if mode not in {"none", "smart", "all"}:
        mode = "smart"
    return mode


def should_isolate(tool_name: str) -> bool:
    """Decide whether to isolate a given tool based on the policy."""
    mode = resolve_isolation_mode()
    if mode == "all":
        return True
    if mode == "smart":
        return tool_name in ISOLATED_TOOL_MAP
    return False


def identify_non_serializable_params(tool_spec: Dict[str, Any]) -> Set[str]:
    """Identify parameters that cannot be JSON-serialized (dict-based helper for isolation)."""
    non_serializable = set()
    param_types = tool_spec.get("param_types", {})
    
    for param_name, param_type in param_types.items():
        # Check if it's a known non-serializable type
        type_str = str(param_type) if not isinstance(param_type, str) else param_type
        for non_ser_type in NON_SERIALIZABLE_TYPES:
            if non_ser_type in type_str:
                non_serializable.add(param_name)
                break
    
    return non_serializable


def _build_isolated_script(
    module_path: str,
    function_name: str,
    tool_name: str,
    input_params: list,
    output_params: list,
    param_values: Dict[str, Any],
    workspace_dir: Path,
    non_serializable_params: Set[str]
) -> str:
    """Generate Python script for isolated tool execution."""
    
    # Build kwargs loading code
    kwargs_setup = []
    for param in input_params:
        if param in param_values:
            value = param_values[param]
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # Reference to another tool's output
                ref = value[2:-1]  # Remove ${ and }
                kwargs_setup.append(f'kwargs["{param}"] = state_store.get("{ref}")')
            elif param in non_serializable_params:
                # Non-serializable object - use pickled reference
                kwargs_setup.append(f'kwargs["{param}"] = state_store.get_pickled("{tool_name}.{param}")')
            else:
                # Direct value
                kwargs_setup.append(f'kwargs["{param}"] = {repr(value)}')
    
    kwargs_code = "\n".join(kwargs_setup) if kwargs_setup else "pass"
    
    # Build output storage code
    output_storage = []
    if len(output_params) == 1:
        output_storage.append(f'state_store.set("{tool_name}.{output_params[0]}", result)')
    else:
        output_storage.append('if isinstance(result, dict):')
        for param in output_params:
            output_storage.append(f'    state_store.set("{tool_name}.{param}", result.get("{param}"))')
        output_storage.append('elif isinstance(result, (list, tuple)):')
        for i, param in enumerate(output_params):
            output_storage.append(f'    if len(result) > {i}:')
            output_storage.append(f'        state_store.set("{tool_name}.{param}", result[{i}])')
    
    output_code = "\n".join(output_storage) if output_storage else "pass"
    
    return f"""
import os, sys, json, importlib
from pathlib import Path

# Add workspace to path for StateStore
sys.path.insert(0, r"{str(workspace_dir.parent.parent)}")

# Avoid OMP/MKL issues
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Import StateStore
from src.executor.process_isolation import StateStore

# Initialize state store
state_store = StateStore(Path(r"{str(workspace_dir)}"))

# Build kwargs from state
kwargs = {{}}
{kwargs_code}

# Import and execute tool
module = importlib.import_module("{module_path}")
func = getattr(module, "{function_name}")

print(f"Executing {{func.__name__}} with kwargs: {{list(kwargs.keys())}}")
result = func(**kwargs)
print(f"{{func.__name__}} completed successfully")

# Store outputs
{output_code}

# Store execution path
exec_path = state_store.get("execution_path") or []
exec_path.append("{tool_name}")
state_store.set("execution_path", exec_path)
"""


def run_tool_isolated(
    tool_spec: Dict[str, Any],
    workspace_dir: Path,
    project_root: str,
    extra_env: Dict[str, str] | None = None
) -> Any:
    """Execute a tool in an isolated subprocess using file-based state.
    
    Args:
        tool_spec: Complete tool specification including function reference
        workspace_dir: Directory for state files
        project_root: Filesystem path to repo root
        extra_env: Optional extra environment variables
        
    Returns:
        The function's return value (from state store)
    """
    tool_name = tool_spec.name if isinstance(tool_spec, PathItem) else tool_spec["name"]
    
    # Get module and function info
    if tool_name in ISOLATED_TOOL_MAP:
        module_path, function_name = ISOLATED_TOOL_MAP[tool_name]
    else:
        # Try to extract from function object
        func = tool_spec.function if isinstance(tool_spec, PathItem) else tool_spec.get("function")
        if func:
            module_path = getattr(func, "__module__", None)
            function_name = getattr(func, "__name__", None)
            if not module_path or not function_name:
                raise RuntimeError(f"Cannot resolve module/function for '{tool_name}'")
        else:
            raise RuntimeError(f"No function reference for tool '{tool_name}'")
    
    # Identify non-serializable parameters
    non_serializable_params = identify_non_serializable_params(tool_spec)
    
    # Initialize state store and save non-serializable objects
    state_store = StateStore(workspace_dir)
    param_values = tool_spec.param_values if isinstance(tool_spec, PathItem) else tool_spec.get("param_values", {})
    if param_values is None:
        param_values = {}
    
    for param in non_serializable_params:
        if param in param_values:
            # Store non-serializable object with pickled reference
            state_store.set(f"{tool_name}.{param}", param_values[param])
    
    # Create script
    script_path = workspace_dir / f"run_{tool_name}.py"
    script = _build_isolated_script(
        module_path=module_path,
        function_name=function_name,
        tool_name=tool_name,
        input_params=(tool_spec.input_params if isinstance(tool_spec, PathItem) else tool_spec.get("input_params", [])) or [],
        output_params=(tool_spec.output_params if isinstance(tool_spec, PathItem) else tool_spec.get("output_params", [])) or [],
        param_values=param_values,
        workspace_dir=workspace_dir,
        non_serializable_params=non_serializable_params
    )
    
    script_path.write_text(script, encoding="utf-8")
    
    # Prepare environment
    env = os.environ.copy()
    py_path = env.get("PYTHONPATH", "")
    if project_root and project_root not in py_path:
        env["PYTHONPATH"] = project_root + (os.pathsep + py_path if py_path else "")
    if extra_env:
        env.update(extra_env)
    
    # Execute script
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=project_root or None,
        env=env,
        capture_output=True,
        text=True
    )
    
    if proc.returncode != 0:
        raise RuntimeError(
            f"Isolated tool '{tool_name}' failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    
    # Return the output from state store
    output_params = (tool_spec.output_params if isinstance(tool_spec, PathItem) else tool_spec.get("output_params", [])) or []
    if not output_params:
        return None
    elif len(output_params) == 1:
        return state_store.get(f"{tool_name}.{output_params[0]}")
    else:
        # Return dict of all outputs
        return {param: state_store.get(f"{tool_name}.{param}") for param in output_params}


class IsolatedGraphExecutor:
    """Executes graph with complete process isolation for each tool."""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.workspace_dir = None
    
    def execute_path(self, path_object: list[PathItem], initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute path with each tool in a separate process.
        
        Args:
            path_object: List of tool specifications
            initial_state: Initial state values
            
        Returns:
            Final state after execution
        """
        # Create workspace directory under repo tmp dir
        tmp_root = Path(self.project_root) / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.workspace_dir = Path(tempfile.mkdtemp(prefix="genesis_exec_", dir=str(tmp_root)))
        state_store = StateStore(self.workspace_dir)
        
        try:
            # Initialize state with initial values
            for key, value in initial_state.items():
                if key not in ["error_info", "execution_path", "outputs"]:
                    state_store.set(key, value)
            
            # Execute each tool
            for tool_spec in path_object:
                tool_name = tool_spec.name
                print(f"\n=== Executing tool: {tool_name} ===")
                
                if should_isolate(tool_name):
                    # Run in isolated process
                    result = run_tool_isolated(
                        tool_spec=tool_spec.model_dump(),
                        workspace_dir=self.workspace_dir,
                        project_root=self.project_root
                    )
                else:
                    # Run directly (for non-isolated tools)
                    result = self._run_tool_direct(tool_spec, state_store)
                
                print(f"Tool {tool_name} completed")
            
            # Build final state
            final_state = state_store._load_state()
            final_state["error_info"] = None
            
            return final_state
            
        except Exception as e:
            # Handle errors
            error_info = {
                "error": str(e),
                "error_type": type(e).__name__,
                "execution_failed": True
            }
            return {"error_info": error_info}
            
        finally:
            # Clean up workspace unless explicitly kept
            keep = os.environ.get("GENESIS_KEEP_WORKSPACE", "0").strip()
            if keep not in {"1", "true", "True", "yes", "YES"}:
                if self.workspace_dir and self.workspace_dir.exists():
                    shutil.rmtree(self.workspace_dir, ignore_errors=True)
    
    def _run_tool_direct(self, tool_spec: PathItem, state_store: StateStore) -> Any:
        """Run a tool directly without isolation (for tools with non-serializable inputs)."""
        func = tool_spec.function
        input_params = tool_spec.input_params or []
        output_params = tool_spec.output_params or []
        param_values = tool_spec.param_values or {}
        tool_name = tool_spec.name
        
        # Build kwargs
        kwargs = {}
        for param in input_params:
            if param in param_values:
                value = param_values[param]
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    # Reference to another tool's output
                    ref = value[2:-1]
                    kwargs[param] = state_store.get(ref)
                else:
                    kwargs[param] = value
        
        # Execute
        result = func(**kwargs)
        
        # Store outputs
        if len(output_params) == 1:
            state_store.set(f"{tool_name}.{output_params[0]}", result)
        else:
            if isinstance(result, dict):
                for param in output_params:
                    state_store.set(f"{tool_name}.{param}", result.get(param))
            elif isinstance(result, (list, tuple)):
                for i, param in enumerate(output_params):
                    if i < len(result):
                        state_store.set(f"{tool_name}.{param}", result[i])
        
        return result