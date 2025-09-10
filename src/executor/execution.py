"""
execution.py
Graph Execution Engine
=====================

Handles execution of StateGraphs with progress tracking,
error handling, and structured result extraction.
"""

from typing import Any, Dict, List, Optional, Callable
from ..path.models import PathItem  # type: ignore
from .flow_state import StateGenerator
from langgraph.graph import StateGraph
class ExecutionNodeError(Exception):
    """
    Exception raised when a node (tool) execution fails.
    Carries node/tool identifiers, input kwargs, and full traceback.
    """
    def __init__(self, node_name: str, tool_name: str, kwargs: Dict[str, Any], original_error: Exception, traceback_str: str):
        self.node_name = node_name
        self.tool_name = tool_name
        self.kwargs = kwargs
        self.original_error = original_error
        self.traceback_str = traceback_str
        super().__init__(f"Execution failed in node '{node_name}' (tool '{tool_name}'): {type(original_error).__name__}: {str(original_error)}")



class ExecutionResult:
    """
    Container for execution results with metadata and analysis.
    """
    
    def __init__(self, 
                 final_state: Dict[str, Any],
                 path_object: List[Dict[str, Any]],
                 execution_metadata: Dict[str, Any] = None):
        self.final_state = final_state
        self.path_object = path_object
        self.metadata = execution_metadata or {}
        self._state_generator = StateGenerator(path_object)
    
    @property
    def success(self) -> bool:
        """Whether execution completed successfully"""
        return self.final_state.get("error_info") is None
    
    @property
    def execution_path(self) -> List[str]:
        """List of tools that were executed"""
        return self.final_state.get("execution_path", [])
    
    @property
    def final_output(self) -> Any:
        """The final output from the last tool"""
        return self._state_generator.get_final_output(self.final_state)
    
    @property
    def error_info(self) -> Optional[Dict[str, Any]]:
        """Error information if execution failed"""
        return self.final_state.get("error_info")
    
    @property
    def steps_completed(self) -> int:
        """Number of tools successfully executed"""
        return len(self.execution_path)
    
    def get_output(self, field_name: str) -> Any:
        """Get any output field by name (e.g., 'translated_text')"""
        return self.final_state.get(field_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary format"""
        return {
            "success": self.success,
            "execution_path": self.execution_path,
            "steps_completed": self.steps_completed,
            "final_output": self.final_output,
            "error_info": self.error_info,
            "metadata": self.metadata
        }


class ProgressTracker:
    """
    Tracks execution progress and provides callbacks.
    """
    
    def __init__(self):
        self.callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
    
    def add_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add a progress callback function"""
        self.callbacks.append(callback)
    
    def report_progress(self, event: str, data: Dict[str, Any]) -> None:
        """Report progress to all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(event, data)
            except Exception as e:
                # Don't let callback errors break execution
                print(f"Progress callback error: {e}")


class GraphExecutor:
    """
    Handles execution of compiled StateGraphs with progress tracking.
    """
    
    def __init__(self):
        self.progress_tracker = ProgressTracker()
    
    def execute_graph(self, 
                     workflow: StateGraph, 
                     initial_state: Dict[str, Any],
                     path_object: List[PathItem]) -> ExecutionResult:
        """
        Execute a compiled StateGraph.
        
        Args:
            workflow: Compiled StateGraph to execute
            initial_state: Initial state for execution
            path_object: Path object for context
            
        Returns:
            ExecutionResult with complete execution information
        """
        
        try:
            # Report execution start
            self.progress_tracker.report_progress("execution_started", {
                "path_length": len(path_object),
                "tool_names": [tool.name for tool in path_object],
                "initial_state_keys": list(initial_state.keys())
            })
            
            # Execute the workflow using LangGraph
            result = workflow.invoke(initial_state)
            
            # Report completion
            execution_path = result.get("execution_path", [])
            self.progress_tracker.report_progress("execution_completed", {
                "execution_path": execution_path,
                "success": True,
                "final_state_keys": list(result.keys()) if isinstance(result, dict) else []
            })
            
            # Create execution result
            execution_result = ExecutionResult(
                final_state=result,
                path_object=path_object,
                execution_metadata={
                    "execution_method": "langgraph"
                }
            )
            
            return execution_result
            
        except Exception as e:
            # Handle execution errors with detailed node context when available
            if isinstance(e, ExecutionNodeError):
                error_info = {
                    "error": str(e.original_error),
                    "error_type": type(e.original_error).__name__,
                    "execution_failed": True,
                    "node_name": e.node_name,
                    "tool_name": e.tool_name,
                    "kwargs": e.kwargs,
                    "traceback": e.traceback_str,
                }
            else:
                error_info = {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "execution_failed": True
                }

            error_state = {"error_info": error_info}

            # Report error
            self.progress_tracker.report_progress("execution_error", {
                "error": error_info.get("error"),
                "error_type": error_info.get("error_type"),
                "node_name": error_info.get("node_name"),
            })

            return ExecutionResult(
                final_state=error_state,
                path_object=path_object,
                execution_metadata={
                    "execution_method": "error",
                    "error": error_info.get("error"),
                    "error_type": error_info.get("error_type")
                }
            )
    
    def add_progress_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add a progress callback"""
        self.progress_tracker.add_callback(callback)


class ExecutionOrchestrator:
    """
    High-level orchestrator for graph execution workflows.
    """
    
    def __init__(self):
        self.executor = GraphExecutor()
    
    def execute_workflow(self, 
                        workflow: StateGraph, 
                        path_object: List[Dict[str, Any]],
                        initial_state: Dict[str, Any]) -> ExecutionResult:
        """
        Execute a complete workflow.
        
        Args:
            workflow: Compiled StateGraph to execute
            path_object: Path object for context
            initial_state: Initial state for execution
            
        Returns:
            ExecutionResult with complete execution information
        """
        
        # Execute the workflow
        result = self.executor.execute_graph(workflow, initial_state, path_object)
        
        return result
    
    def add_progress_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add a progress callback for execution tracking"""
        self.executor.add_progress_callback(callback)


# Convenience function for quick execution
def execute_stategraph(workflow: StateGraph, 
                      path_object: List[Dict[str, Any]], 
                      initial_state: Dict[str, Any]) -> ExecutionResult:
    """
    Quick execution function for simple use cases.
    
    Args:
        workflow: Compiled StateGraph to execute
        path_object: Path object for context
        initial_state: Initial state for execution
        
    Returns:
        Execution result
    """
    orchestrator = ExecutionOrchestrator()
    return orchestrator.execute_workflow(workflow, path_object, initial_state)
