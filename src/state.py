from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import Annotated
from .path import WorkflowTypeEnum, PathItem

class State(TypedDict):
    # Control flow
    node: str
    next_node: str
    messages: Annotated[list[AnyMessage], add_messages]
    
    # Classify node results
    objective: str
    input_type: WorkflowTypeEnum  # Type of input provided by the user
    type_savepoint: List[WorkflowTypeEnum]  # The type of savepoint to use
    is_complex: bool  # Whether the task requires complex processing beyond simple web search
    classify_reasoning: str  # Explanation of the classification decision
    classify_clarification: Optional[str]  # Question to ask user if more information is needed
    
    # Path node results
    tool_metadata: List[Dict[str, Any]]  # Serializable metadata about tools in the path
    all_paths: List[dict]  # All possible paths discovered

    # Router node results
    chosen_path: List[PathItem]  # The selected path for execution
    route_reasoning: str  # Explanation of routing decision
    route_clarification: Optional[str]  # Question to ask user if more information is needed
    is_partial: bool  # Whether execution was partial/incomplete
    
    # Execute node results
    execution_results: Any  # Results from the execution

    # Finalizer node results
    is_complete: bool  # Whether the task is complete
    response: str  # The final response to the user
    finalize_reasoning: str  # Explanation of how the final answer was constructed
    summary: Optional[str]  # Summary of previous outputs
    
    # Optional: Additional execution tracking
    execution_results: Optional[List[dict]]  # Results from each step in the path
    error_details: Optional[str]  # Any errors encountered during execution
