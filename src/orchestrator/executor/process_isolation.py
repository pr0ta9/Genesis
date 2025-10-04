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
import threading
from pathlib import Path
from typing import Any, Dict, Tuple, Set
from ..path.models import PathItem  # type: ignore
import uuid
from langgraph.config import get_stream_writer
from ..core.logging_utils import build_step_file_prefix, open_log_writers


# Tools that should be isolated in SMART mode
ISOLATED_TOOL_MAP: Dict[str, Tuple[str, str]] = {
    "erase": ("src.orchestrator.tools.path_tools.erase", "erase"),
    "image_ocr": ("src.orchestrator.tools.path_tools.ocr", "image_ocr"),
    "translate": ("src.orchestrator.tools.path_tools.translate", "translate"),
    "inpaint_text": ("src.orchestrator.tools.path_tools.inpaint_text", "inpaint_text"),
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
    
    # Build kwargs loading code (include all provided params, not just input_params)
    kwargs_setup = []
    for param, value in (param_values or {}).items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            # Reference to another tool's output
            ref = value[2:-1]  # Remove ${ and }
            kwargs_setup.append(f'kwargs["{param}"] = state_store.get("{ref}")')
        elif param in non_serializable_params:
            # Skip non-serializable params (like LLM models) - tools will create their own
            # Tools should have default/fallback logic for these parameters
            kwargs_setup.append(f'# Skipping non-serializable param: {param} (tool will use default)')
            kwargs_setup.append(f'kwargs["{param}"] = None')
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

# Add project root to path for imports
sys.path.insert(0, r"{str(workspace_dir.parent.parent)}")

# Avoid OMP/MKL issues
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Import StateStore using absolute import
from src.orchestrator.executor.process_isolation import StateStore

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
    writer = None,
    extra_env: Dict[str, str] | None = None,
    chat_id: str = "unknown",
    message_id: str = "unknown",
    step_index: int = 0,
) -> Any:
    """Execute a tool in an isolated subprocess using file-based state.
    
    Args:
        tool_spec: Complete tool specification including function reference
        workspace_dir: Directory for state files
        project_root: Filesystem path to repo root
        writer: Optional stream writer for events
        extra_env: Optional extra environment variables
        chat_id: Chat/conversation ID for output path resolution
        message_id: Message ID for output path resolution
        step_index: Step index for output path resolution
        
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
    
    # Initialize state store (non-serializable params are skipped - tools create their own)
    state_store = StateStore(workspace_dir)
    param_values = tool_spec.param_values if isinstance(tool_spec, PathItem) else tool_spec.get("param_values", {})
    if param_values is None:
        param_values = {}
    
    # Note: Non-serializable params (like LLM models) are intentionally NOT stored
    # Tools must create their own instances when run in isolated processes
    
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
    # Build subprocess environment (isolated from parent process)
    env = os.environ.copy()
    py_path = env.get("PYTHONPATH", "")
    if project_root and project_root not in py_path:
        env["PYTHONPATH"] = project_root + (os.pathsep + py_path if py_path else "")
    if extra_env:
        env.update(extra_env)
    
    # Set chat/message IDs in subprocess env (NOT parent process!)
    # This ensures each concurrent request has isolated context
    env["GENESIS_CONVERSATION_ID"] = str(chat_id)
    env["GENESIS_MESSAGE_ID"] = str(message_id)
    env["GENESIS_STEP_INDEX"] = str(step_index)
    
    # Prepare log writers if context is available
    stdout_file = stderr_file = None
    if chat_id != "unknown" and message_id != "unknown":
        prefix = build_step_file_prefix(chat_id, message_id, step_index, tool_name)
        _, _, stdout_file, stderr_file = open_log_writers(prefix)

    # Execute script with streaming stdout/stderr
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=project_root or None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    def _reader(stream, is_stdout: bool, queue):
        """Read stream lines into queue - no writer calls from thread"""
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                try:
                    if is_stdout and stdout_file:
                        stdout_file.write(line)
                    if (not is_stdout) and stderr_file:
                        stderr_file.write(line)
                except Exception:
                    pass
                # Add to queue for main thread to emit (avoids threading/context issues)
                queue.put(('stdout' if is_stdout else 'stderr', line.rstrip("\n")))
        finally:
            try:
                stream.close()
            except Exception:
                pass
            queue.put(None)  # Signal completion

    # Create queue for thread-safe communication
    import queue
    output_queue = queue.Queue()
    
    threads = []
    if proc.stdout is not None:
        t_out = threading.Thread(target=_reader, args=(proc.stdout, True, output_queue), daemon=True)
        threads.append(t_out)
        t_out.start()
    if proc.stderr is not None:
        t_err = threading.Thread(target=_reader, args=(proc.stderr, False, output_queue), daemon=True)
        threads.append(t_err)
        t_err.start()

    # Stream output from queue while process runs
    threads_done = 0
    total_threads = len(threads)
    
    while threads_done < total_threads or proc.poll() is None:
        try:
            # Non-blocking get with short timeout
            item = output_queue.get(timeout=0.1)
            if item is None:
                threads_done += 1
            else:
                stream_type, line = item
                # Emit immediately from main thread (has context)
                if writer:
                    try:
                        writer({"tool_name": tool_name, "stdout": line})
                    except Exception as e:
                        print(f"[PROCESS_ISOLATION] Failed to emit line: {e}")
        except queue.Empty:
            continue
    
    # Drain any remaining items in queue
    while not output_queue.empty():
        try:
            item = output_queue.get_nowait()
            if item is not None:
                stream_type, line = item
                if writer:
                    try:
                        writer({"tool_name": tool_name, "stdout": line})
                    except Exception as e:
                        print(f"[PROCESS_ISOLATION] Failed to emit final line: {e}")
        except queue.Empty:
            break
    
    rc = proc.wait()
    for t in threads:
        try:
            t.join(timeout=0.2)
        except Exception:
            pass
    if stdout_file:
        try:
            stdout_file.flush(); stdout_file.close()
        except Exception:
            pass
    if stderr_file:
        try:
            stderr_file.flush(); stderr_file.close()
        except Exception:
            pass

    if rc != 0:
        raise RuntimeError(
            f"Isolated tool '{tool_name}' failed (rc={rc})"
        )
    
    # Return the output from state store
    output_params = (tool_spec.output_params if isinstance(tool_spec, PathItem) else tool_spec.get("output_params", [])) or []
    if not output_params:
        return None
    elif len(output_params) == 1:
        main_key = output_params[0]
        value = state_store.get(f"{tool_name}.{main_key}")
        # Optionally write a preview for non-file results, but always return the true value for chaining
        try:
            if chat_id != "unknown" and message_id != "unknown" and not (isinstance(value, str) and Path(value).exists()):
                prefix = build_step_file_prefix(chat_id, message_id, step_index, tool_name)
                txt_path = prefix.with_suffix(".txt")
                txt_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    content = json.dumps(value, indent=2, ensure_ascii=False)
                except Exception:
                    content = str(value)
                txt_path.write_text(content, encoding="utf-8")
        except Exception:
            pass
        return value
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
                
                # Always run in isolated process
                result = run_tool_isolated(
                    tool_spec=tool_spec.model_dump(),
                    workspace_dir=self.workspace_dir,
                    project_root=self.project_root
                )
                
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
    