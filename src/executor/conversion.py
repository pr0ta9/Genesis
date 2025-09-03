"""
conversion.py
Path to StateGraph Conversion with Enhanced Isolation
=====================================================

Converts path objects into executable LangGraph StateGraphs with
intelligent process isolation for tool execution.
"""

from typing import Any, Dict, List, Callable
from inspect import signature
from langgraph.graph import StateGraph, END, START
from datetime import datetime
import traceback as _tb
import os
from pathlib import Path
import tempfile
import shutil


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
                            path_object: List[Dict[str, Any]],
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
    
    def _create_fully_isolated_graph(self, path_object: List[Dict[str, Any]], state_schema: Dict[str, Any]) -> StateGraph:
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
    
    def _create_selective_isolation_graph(self, path_object: List[Dict[str, Any]], state_schema: Dict[str, Any]) -> StateGraph:
        """Create normal StateGraph with selective tool isolation."""
        
        builder = StateGraph(state_schema)
        
        # Add tool nodes with selective isolation
        node_names: List[str] = []
        for i, tool_spec in enumerate(path_object):
            node_name = tool_spec.get('name', f'tool_{i}')
            tool_func = tool_spec.get('function')
            if tool_func is None or not callable(tool_func):
                raise ValueError(f"Path step {i} missing a callable 'function'")
            
            input_params = tool_spec.get('input_params', [])
            output_params = tool_spec.get('output_params', [])
            
            node_func = self._make_hybrid_adapter(node_name, tool_func, input_params, output_params, tool_spec)
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
                            tool_spec: Dict[str, Any]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
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
            non_serializable = identify_non_serializable_params(tool_spec)
            
            # If tool has non-serializable inputs from previous steps, we need special handling
            param_values = tool_spec.get('param_values', {}) or {}
            has_model_param = any(p in non_serializable for p in input_params if p in param_values)
            
            if needs_isolation and not has_model_param:
                # Run in isolated process
                print(f"Running {node_name} in isolated process")
                
                # Create temporary workspace under repo tmp dir
                tmp_root = Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "tmp"
                tmp_root.mkdir(parents=True, exist_ok=True)
                workspace_dir = Path(tempfile.mkdtemp(prefix=f"genesis_{node_name}_", dir=str(tmp_root)))
                try:
                    # Prepare tool spec with resolved values
                    resolved_spec = tool_spec.copy()
                    resolved_values = {}
                    
                    for name in input_params:
                        if name in param_values:
                            v = param_values[name]
                            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                                # Resolve reference from state
                                ref = v[2:-1]
                                step, out_key = ref.split('.', 1)
                                outputs = state.get('outputs') or {}
                                resolved_values[name] = ((outputs.get(step) or {}).get(out_key))
                            else:
                                resolved_values[name] = v
                        elif name in state:
                            resolved_values[name] = state.get(name)
                    
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
                for name in input_params:
                    if name not in accepted_params:
                        continue
                    if name in param_values:
                        v = param_values[name]
                        v = _resolve_ref(v) if _is_ref(v) else v
                        kwargs[name] = v
                    elif name in state:
                        kwargs[name] = state.get(name)
                
                print(f"Running {node_name} directly with kwargs: {list(kwargs.keys())}")
                
                try:
                    result = tool_func(**kwargs)
                except Exception as err:
                    tb_str = _tb.format_exc()
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