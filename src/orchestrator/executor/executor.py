"""
executor.py
Path Execution Engine
=====================

Executes path objects by running tools sequentially with process isolation,
file path resolution, and real-time streaming.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
import tempfile
import os
from ..path.models import PathItem
from .process_isolation import run_tool_isolated


class PathExecutor:
    """
    Executes a path by running tools sequentially with process isolation.
    """
    
    def __init__(self):
        pass
    
    def execute_path(
        self,
        chosen_path: List[PathItem],
        chat_id: str,
        message_id: str,
        writer=None
    ) -> Dict[str, Any]:
        """
        Execute a path by running tools sequentially.
        
        Args:
            chosen_path: List of PathItem objects to execute
            chat_id: Chat identifier for file path resolution
            message_id: Message identifier for output directory
            writer: Stream writer for emitting custom events (optional)
            
        Returns:
            Dictionary with execution results:
            {
                "success": bool,
                "execution_path": List[str],
                "steps_completed": int,
                "final_output": Any,
                "error_info": Optional[Dict],
                "metadata": Dict
            }
        """
        
        # Initialize execution state
        exec_state = {}
        execution_path = []
        final_output = None
        error_info = None
        
        # Execute tools sequentially
        for i, tool_spec in enumerate(chosen_path):
            tool_name = tool_spec.name
            step_index = i + 1
            execution_path.append(tool_name)
            
            try:
                # Resolve input/output file paths
                self._resolve_file_paths(tool_spec, chat_id, message_id)
                
                # Create workspace for this tool
                tmp_root = Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "tmp"
                tmp_root.mkdir(parents=True, exist_ok=True)
                workspace_dir = Path(tempfile.mkdtemp(prefix=f"genesis_{tool_name}_", dir=str(tmp_root)))
                
                # Emit start event
                if writer:
                    writer({
                        "tool_name": tool_name,
                        "workspace_dir": str(workspace_dir),
                        "status": "start"
                    })
                
                # Run tool in isolation
                result = run_tool_isolated(
                    tool_spec=tool_spec.model_dump(),
                    workspace_dir=workspace_dir,
                    project_root=os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd()),
                    writer=writer,
                    chat_id=chat_id,
                    message_id=message_id,
                    step_index=step_index,
                )
                
                # Store result for potential chaining
                if tool_spec.output_params and len(tool_spec.output_params) > 0:
                    output_key = tool_spec.output_params[0]
                    exec_state[output_key] = result
                    final_output = result
                
                # Emit end event
                if writer:
                    writer({
                        "tool_name": tool_name,
                        "workspace_dir": str(workspace_dir),
                        "status": "end"
                    })
                    
            except Exception as e:
                # Tool execution failed
                error_info = {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "tool_name": tool_name,
                    "execution_failed": True
                }
                if writer:
                    writer({
                        "tool_name": tool_name,
                        "stdout": f"ERROR: {str(e)}"
                    })
                break
        
        # Build execution result
        return {
            "success": error_info is None,
            "execution_path": execution_path,
            "steps_completed": len(execution_path),
            "final_output": final_output,
            "error_info": error_info,
            "metadata": {"execution_method": "direct_loop"}
        }
    
    def _resolve_file_paths(
        self,
        tool_spec: PathItem,
        chat_id: str,
        message_id: str
    ) -> None:
        """
        Resolve simple filenames to absolute paths.
        
        Input files: {filename} -> /app/inputs/{chat_id}/{filename}
        Output files: {filename} -> /app/outputs/{chat_id}/{message_id}/{filename}
        
        Args:
            tool_spec: PathItem with param_values to resolve
            chat_id: Chat identifier
            message_id: Message identifier
        """
        if not tool_spec.param_values:
            return
        
        for param_name, param_value in tool_spec.param_values.items():
            # Only process simple filenames (no path separators)
            if not isinstance(param_value, str):
                continue
            if '/' in param_value or '\\' in param_value:
                continue
            
            # Check if it's an output parameter
            is_output = (
                (tool_spec.output_params and param_name in tool_spec.output_params) or
                param_name == "output_path"
            )
            
            if is_output:
                # Output file - resolve to outputs/{chat_id}/{message_id}/{filename}
                outputs_root = os.environ.get("GENESIS_OUTPUTS_ROOT") or str(
                    Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "outputs"
                )
                output_path = Path(outputs_root) / chat_id / str(message_id) / param_value
                output_path.parent.mkdir(parents=True, exist_ok=True)
                tool_spec.param_values[param_name] = str(output_path)
            else:
                # Input file - resolve to inputs/{chat_id}/{filename}
                inputs_root = os.environ.get("GENESIS_INPUTS_ROOT") or str(
                    Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "inputs"
                )
                input_path = Path(inputs_root) / chat_id / param_value
                if input_path.exists():
                    tool_spec.param_values[param_name] = str(input_path)


def execute_path(
    chosen_path: List[PathItem],
    chat_id: str,
    message_id: str,
    writer=None
) -> Dict[str, Any]:
    """
    Convenience function to execute a path.
    
    Args:
        chosen_path: List of PathItem objects to execute
        chat_id: Chat identifier
        message_id: Message identifier
        writer: Stream writer for custom events
        
    Returns:
        Execution result dictionary
    """
    executor = PathExecutor()
    return executor.execute_path(chosen_path, chat_id, message_id, writer)

