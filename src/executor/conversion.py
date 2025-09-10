"""
conversion.py
Path to StateGraph Conversion with Enhanced Isolation
=====================================================

Converts path objects into executable LangGraph StateGraphs with
intelligent process isolation for tool execution.
"""

from typing import Any, Dict, List, Callable
from ..path.models import PathItem  # type: ignore
from inspect import signature
from langgraph.graph import StateGraph, END, START
from datetime import datetime
import traceback as _tb
import os
from pathlib import Path
import tempfile
import shutil
from ..streaming import emit_status, StatusType
from ..logging_utils import build_step_file_prefix
import json
from ..path.metadata import WorkflowType  # type: ignore

class StateGraphConverter:
    """
    Converts path objects into executable LangGraph StateGraphs with process isolation.
    """
    
    def __init__(self, use_full_isolation: bool = False):
        """
        Args:
            use_full_isolation: If True, run entire path in isolated mode.
                              If False, use normal StateGraph with selective isolation.
        """
        self.use_full_isolation = use_full_isolation
    
    def convert_to_stategraph(self, 
                            path_object: List[PathItem],
                            state_schema: Dict[str, Any]) -> StateGraph:
        """
        Convert a path object into an executable StateGraph.
        
        For full isolation mode, returns a special StateGraph that delegates
        to the IsolatedGraphExecutor.
        """
        
        if not path_object:
            raise ValueError("Cannot convert empty path object")
        
        if self.use_full_isolation:
            # Create a special StateGraph that runs everything isolated
            return self._create_fully_isolated_graph(path_object, state_schema)
        else:
            # Use selective isolation within normal StateGraph
            return self._create_selective_isolation_graph(path_object, state_schema)
    
    def _create_fully_isolated_graph(self, path_object: List[PathItem], state_schema: Dict[str, Any]) -> StateGraph:
        """Create a StateGraph that runs the entire path in isolated mode."""
        from .process_isolation import IsolatedGraphExecutor
        
        builder = StateGraph(state_schema)
        
        # Single node that executes entire path
        def execute_isolated_path(state: Dict[str, Any]) -> Dict[str, Any]:
            project_root = os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())
            executor = IsolatedGraphExecutor(project_root)
            
            # Execute entire path
            result = executor.execute_path(path_object, state)
            
            # Return the complete state update
            return result
        
        builder.add_node("isolated_execution", execute_isolated_path)
        builder.add_edge(START, "isolated_execution")
        builder.add_edge("isolated_execution", END)
        
        return builder.compile()
    
    def _create_selective_isolation_graph(self, path_object: List[PathItem], state_schema: Dict[str, Any]) -> StateGraph:
        """Create normal StateGraph with selective tool isolation."""
        
        builder = StateGraph(state_schema)
        
        # Add tool nodes with selective isolation
        node_names: List[str] = []
        for i, tool_spec in enumerate(path_object):
            node_name = tool_spec.name
            tool_func = tool_spec.function
            input_params = list(tool_spec.input_params or [])
            output_params = list(tool_spec.output_params or [])
            if tool_func is None or not callable(tool_func):
                raise ValueError(f"Path step {i} missing a callable 'function'")

            step_index = i + 1
            node_func = self._make_hybrid_adapter(node_name, tool_func, input_params, output_params, tool_spec, step_index)
            builder.add_node(node_name, node_func)
            node_names.append(node_name)
        
        # Wire edges
        if node_names:
            builder.add_edge(START, node_names[0])
            for i in range(len(node_names) - 1):
                builder.add_edge(node_names[i], node_names[i + 1])
            builder.add_edge(node_names[-1], END)
        
        return builder.compile()
    
    def _make_hybrid_adapter(self, node_name: str, tool_func: Callable,
                            input_params: List[str], output_params: List[str],
                            tool_spec: PathItem, step_index: int) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        """
        Create adapter that can run tool either directly or in isolation.
        
        Decides based on:
        1. Tool name in ISOLATED_TOOL_MAP
        2. Presence of non-serializable parameters
        """
        from .process_isolation import (
            should_isolate, 
            identify_non_serializable_params,
            StateStore,
            run_tool_isolated
        )
        from .execution import ExecutionNodeError
        
        tool_sig = signature(tool_func)
        accepted_params = set(tool_sig.parameters.keys())
        
        def node(state: Dict[str, Any]) -> Dict[str, Any]:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] DEBUG: Node function called for {node_name}")
            
            # Check if tool needs isolation
            needs_isolation = should_isolate(node_name)
            # Normalize PathItem for isolation helpers
            ts_dict = tool_spec.model_dump()
            non_serializable = identify_non_serializable_params(ts_dict)
            
            # If tool has non-serializable inputs from previous steps, we need special handling
            param_values = tool_spec.param_values or {}
            has_model_param = any(p in non_serializable for p in input_params if p in param_values)
            
            # Helpers for input reference resolution and output path injection
            def _load_input_mapping() -> Dict[str, Dict[str, Any]]:
                conv_id = os.environ.get("GENESIS_CONVERSATION_ID")
                if not conv_id:
                    return {}
                inputs_root = os.environ.get("GENESIS_INPUTS_ROOT") or str(Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "inputs")
                mapping_path = Path(inputs_root) / conv_id / "mapping.json"
                try:
                    if mapping_path.exists():
                        return json.load(open(mapping_path, "r", encoding="utf-8"))
                except Exception:
                    return {}
                return {}

            def _normalize_ref(s: str) -> str:
                s = s.strip().strip("\"'")
                if os.name == 'nt':
                    s = s.lower()
                return s

            def _resolve_input_value(val: Any) -> Any:
                # Only try to resolve simple strings
                if not isinstance(val, str):
                    return val
                # If already absolute or exists, keep
                try:
                    p = Path(val)
                    if p.is_absolute() and p.exists():
                        return val
                    if p.exists():
                        return str(p.resolve())
                except Exception:
                    pass
                # Try mapping
                mapping = _load_input_mapping()
                key = _normalize_ref(val)
                entry = mapping.get(key)
                if entry and "path" in entry:
                    return entry["path"]
                return val

            def _infer_output_ext(resolved_vals: Dict[str, Any], types: Dict[str, Any]) -> str:
                # 0) Prefer required file inputs from tool metadata (e.g., inpaint_text requires image_input)
                try:
                    req = getattr(tool_spec, 'required_inputs', None)
                    if req is None:
                        req = tool_spec.model_dump().get('required_inputs', {})
                    if isinstance(req, dict):
                        for param_name in req.keys():
                            # Consider only params present in resolved values
                            if param_name in resolved_vals and isinstance(resolved_vals[param_name], str):
                                pth = Path(resolved_vals[param_name])
                                if pth.suffix:
                                    return pth.suffix.lower()
                except Exception:
                    pass
                # 1) Derive from input path extension when present
                candidate_input_keys = [
                    "image_input", "audio_input", "video_input", "file_input", "input_path"
                ]
                for k in candidate_input_keys:
                    v = resolved_vals.get(k)
                    if isinstance(v, str):
                        try:
                            ext = Path(v).suffix.lower()
                            if ext:
                                return ext
                        except Exception:
                            pass

                # 2) Derive from explicit format/codec hints
                format_keys = ["output_ext", "format", "output_format", "codec", "image_format"]
                for k in format_keys:
                    v = resolved_vals.get(k)
                    if isinstance(v, str) and v:
                        fmt = v.strip().lower().lstrip('.')
                        if fmt in {"png","jpg","jpeg","webp","bmp","tif","tiff","gif"}:
                            return "." + ("jpg" if fmt == "jpeg" else fmt)
                        if fmt in {"wav","mp3","m4a","ogg","flac"}:
                            return "." + fmt
                        if fmt in {"mp4","mov","avi","mkv"}:
                            return "." + fmt
                        if fmt in {"txt","json"}:
                            return "." + fmt

                # 3) Fall back to type mapping from param_types
                t = str(types.get("output_path", ""))
                if "ImageFile" in t:
                    return ".png"
                if "AudioFile" in t:
                    return ".wav"
                if "VideoFile" in t:
                    return ".mp4"
                if "TextFile" in t:
                    return ".txt"
                return ".bin"

            def _maybe_inject_output_path(resolved_vals: Dict[str, Any]) -> Dict[str, Any]:
                # Inject output_path if the tool accepts it and it's not provided
                if "output_path" in accepted_params and "output_path" not in resolved_vals:
                    conv = os.environ.get("GENESIS_CONVERSATION_ID", "conv")
                    msg = os.environ.get("GENESIS_MESSAGE_ID", "msg")
                    step_idx = len(state.get('execution_path', [])) + 1
                    ext = _infer_output_ext(resolved_vals, tool_spec.param_types or {})
                    prefix = build_step_file_prefix(conv, msg, step_idx, node_name)
                    resolved_vals["output_path"] = str(prefix.with_suffix(ext))
                return resolved_vals

            # Set fixed step index env for logging/artifacts
            try:
                os.environ["GENESIS_STEP_INDEX"] = str(step_index)
            except Exception:
                pass

            if needs_isolation and not has_model_param:
                # Run in isolated process
                print(f"Running {node_name} in isolated process")
                
                # Create temporary workspace under repo tmp dir
                tmp_root = Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "tmp"
                tmp_root.mkdir(parents=True, exist_ok=True)
                workspace_dir = Path(tempfile.mkdtemp(prefix=f"genesis_{node_name}_", dir=str(tmp_root)))
                
                # Emit workspace creation event
                
                emit_status(
                    type=StatusType.EXECUTION_EVENT,
                    node=node_name,
                    event={
                        "status": "workspace_created",
                        "workspace_dir": str(workspace_dir),
                        "tool_name": node_name
                    }
                )
                
                try:
                    # Prepare tool spec dict with resolved values
                    resolved_spec = tool_spec.model_dump()
                    resolved_values = {}
                    
                    original_vals_snapshot = {}
                    for name in input_params:
                        if name in param_values:
                            v = param_values[name]
                            original_vals_snapshot[name] = v
                            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                                # Resolve reference from state
                                ref = v[2:-1]
                                step, out_key = ref.split('.', 1)
                                outputs = state.get('outputs') or {}
                                resolved_values[name] = ((outputs.get(step) or {}).get(out_key))
                            else:
                                resolved_values[name] = _resolve_input_value(v)
                        elif name in state:
                            original_vals_snapshot[name] = state.get(name)
                            resolved_values[name] = _resolve_input_value(state.get(name))
                    
                    resolved_values = _maybe_inject_output_path(resolved_values)
                    # Emit debug for input resolution
                    try:
                        mapping_debug = list(_load_input_mapping().keys())
                        for pname, orig in original_vals_snapshot.items():
                            if isinstance(orig, str) and not (orig.startswith("${") and orig.endswith("}")):
                                newv = resolved_values.get(pname)
                                if newv != orig:
                                    emit_status(
                                        type=StatusType.EXECUTION_EVENT,
                                        node=node_name,
                                        event={
                                            "status": "input_resolution",
                                            "tool_name": node_name,
                                            "param": pname,
                                            "original": str(orig),
                                            "resolved": str(newv),
                                            "mapping_keys": mapping_debug
                                        }
                                    )
                    except Exception:
                        pass
                    resolved_spec['param_values'] = resolved_values
                    
                    # Initialize state store with current state
                    state_store = StateStore(workspace_dir)
                    for step_name, step_outputs in (state.get('outputs') or {}).items():
                        for out_key, out_val in step_outputs.items():
                            state_store.set(f"{step_name}.{out_key}", out_val)
                    
                    # Run isolated
                    project_root = os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())
                    result = run_tool_isolated(
                        tool_spec=resolved_spec,
                        workspace_dir=workspace_dir,
                        project_root=project_root
                    )
                    
                    # Emit tool execution completed event
                    emit_status(
                        type=StatusType.EXECUTION_EVENT,
                        node=node_name,
                        event={
                            "status": "execution_complete",
                            "workspace_dir": str(workspace_dir),
                            "tool_name": node_name,
                            "isolated": True,
                            "success": True
                        }
                    )
                    
                except Exception as err:
                    # Emit error event
                    emit_status(
                        type=StatusType.ERROR,
                        node=node_name,
                        content=f"Isolated tool execution failed: {str(err)}"
                    )
                    raise  # Re-raise the exception
                    
                finally:
                    # Clean up unless explicitly kept
                    keep = os.environ.get("GENESIS_KEEP_WORKSPACE", "0").strip()
                    if keep not in {"1", "true", "True", "yes", "YES"}:
                        shutil.rmtree(workspace_dir, ignore_errors=True)
                
            else:
                # Run directly (either not isolated or has non-serializable params)
                if needs_isolation and has_model_param:
                    print(f"Running {node_name} directly due to non-serializable parameters")
                
                
                # Helper functions for reference resolution
                def _is_ref(value: Any) -> bool:
                    return isinstance(value, str) and value.startswith("${") and value.endswith("}")

                def _resolve_ref(value: str) -> Any:
                    try:
                        ref = value[2:-1]
                        step, out_key = ref.split('.', 1)
                    except Exception:
                        return None
                    outputs = state.get('outputs') or {}
                    return ((outputs.get(step) or {}).get(out_key))

                # Build kwargs
                kwargs: Dict[str, Any] = {}
                original_vals_snapshot = {}
                for name in input_params:
                    if name not in accepted_params:
                        continue
                    if name in param_values:
                        v = param_values[name]
                        v = _resolve_ref(v) if _is_ref(v) else v
                        original_vals_snapshot[name] = v
                        kwargs[name] = _resolve_input_value(v)
                    elif name in state:
                        original_vals_snapshot[name] = state.get(name)
                        kwargs[name] = _resolve_input_value(state.get(name))

                # Inject output_path for direct tools
                kwargs = _maybe_inject_output_path(kwargs)

                # Emit debug for input resolution (direct)
                try:
                    mapping_debug = list(_load_input_mapping().keys())
                    for pname, orig in original_vals_snapshot.items():
                        if isinstance(orig, str) and not (isinstance(orig, str) and orig.startswith("${") and orig.endswith("}")):
                            newv = kwargs.get(pname)
                            if newv != orig:
                                emit_status(
                                    type=StatusType.EXECUTION_EVENT,
                                    node=node_name,
                                    event={
                                        "status": "input_resolution",
                                        "tool_name": node_name,
                                        "param": pname,
                                        "original": str(orig),
                                        "resolved": str(newv),
                                        "mapping_keys": mapping_debug
                                    }
                                )
                except Exception:
                    pass
                
                print(f"Running {node_name} directly with kwargs: {list(kwargs.keys())}")
                
                try:
                    result = tool_func(**kwargs)
                    
                    
                except Exception as err:
                    tb_str = _tb.format_exc()
                    
                    # Emit error event
                    emit_status(
                        type=StatusType.ERROR,
                        node=node_name,
                        content=f"Tool execution failed: {str(err)}"
                    )
                    
                    raise ExecutionNodeError(
                        node_name=node_name,
                        tool_name=getattr(tool_func, '__name__', 'unknown_tool'),
                        kwargs=kwargs,
                        original_error=err,
                        traceback_str=tb_str
                    )
            
            # Map outputs to state updates
            updates: Dict[str, Any] = {}
            if not output_params:
                pass
            elif len(output_params) == 1:
                updates[output_params[0]] = result
            else:
                if isinstance(result, dict):
                    for p in output_params:
                        updates[p] = result.get(p)
                else:
                    for p, v in zip(output_params, result if isinstance(result, (list, tuple)) else [result]):
                        updates[p] = v
            
            # Update outputs cache
            outputs_cache = dict(state.get('outputs') or {})
            step_outputs = dict(outputs_cache.get(node_name) or {})
            
            if not output_params:
                pass
            elif len(output_params) == 1:
                step_outputs[output_params[0]] = result
            else:
                if isinstance(result, dict):
                    for p in output_params:
                        step_outputs[p] = result.get(p)
                else:
                    for p, v in zip(output_params, result if isinstance(result, (list, tuple)) else [result]):
                        step_outputs[p] = v
            
            outputs_cache[node_name] = step_outputs
            updates['outputs'] = outputs_cache
            
            # Update execution path
            execution_path = list(state.get('execution_path', []))
            execution_path.append(node_name)
            updates['execution_path'] = execution_path

            # Emit a summary that includes step index for UI mapping
            try:
                emit_status(
                    type=StatusType.EXECUTION_EVENT,
                    node=node_name,
                    event={
                        "status": "execution_step_complete",
                        "tool_name": node_name,
                        "step_index": len(execution_path),
                    }
                )
            except Exception:
                pass
            updates['error_info'] = None
            
            return updates
        
        return node


# Convenience functions
def convert_path_to_isolated_graph(path_object: List[Dict[str, Any]], state_schema: Dict[str, Any]) -> StateGraph:
    """Convert path to fully isolated execution graph."""
    converter = StateGraphConverter(use_full_isolation=True)
    return converter.convert_to_stategraph(path_object, state_schema)


def convert_path_to_hybrid_graph(path_object: List[Dict[str, Any]], state_schema: Dict[str, Any]) -> StateGraph:
    """Convert path to graph with selective isolation."""
    converter = StateGraphConverter(use_full_isolation=False)
    return converter.convert_to_stategraph(path_object, state_schema)