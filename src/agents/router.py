import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..logging_utils import pretty
from ..path import WorkflowTypeEnum, SimplePath, PathItem
from ..state import State

class RoutingResponse(BaseModel):
    """Routing response from LLM."""
    path: List[SimplePath] = Field(description="Simple path with names and param values")
    reasoning: str = Field(description="Explanation of routing decision")
    cot: str = Field(description="Step-by-step thinking process, one thought per line")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if more information is needed"
    )


class Router(BaseAgent[RoutingResponse]):
    """
    Routing agent that determines which specialized agent should handle a classified task.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = os.path.join(os.path.dirname(__file__), 'prompts', 'Router.yaml')):
        """
        Initialize the Router agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, RoutingResponse, prompt_path)
        self.is_partial = False
        self.full_path: List[PathItem] = []
    
    def _convert_to_full_path(self, simple_path: List[SimplePath], tool_metadata: List[Dict[str, Any]], up_to_index: int = None) -> List[PathItem]:
        """Convert simple LLM response to full PathItems using tool_metadata."""
        full_path = []
        
        # Create lookup dict for tool metadata by name
        tools_by_name = {tool["name"]: tool for tool in tool_metadata}
        
        # Convert only up to specified index (or all if None)
        end_index = up_to_index + 1 if up_to_index is not None else len(simple_path)
        
        for i in range(end_index):
            simple_step = simple_path[i]
            tool_meta = tools_by_name[simple_step.name]  # No need for error handling
            # Merge defaults: if a param is explicitly set to None and a default exists, use the default
            # Also fill in any missing defaulted params
            merged_values = dict(simple_step.param_values or {})
            default_params = (tool_meta.get("default_params") or {})
            for key, meta in default_params.items():
                default_value = (meta or {}).get("value")
                if key not in merged_values or merged_values.get(key) is None:
                    # Only set when missing or explicitly None
                    merged_values[key] = default_value
            
            # Build complete PathItem from metadata
            path_item = PathItem(
                name=simple_step.name,
                description=tool_meta["description"],
                function=None,  # Will be resolved during execution
                input_params=tool_meta["input_params"],
                output_params=tool_meta["output_params"], 
                param_values=merged_values,
                param_types=tool_meta["param_types"]
            )
            full_path.append(path_item)
        
        return full_path
    
    def route(self, state: State) -> Dict[str, Any]:
        """
        Route the classified task to appropriate agent.
        
        Args:
            state: Current state containing messages and type_savepoint
            
        Returns:
            Dictionary containing routing results and updated state
        """
        node = "route"
        messages: List[BaseMessage] = state.get("messages", [])
        type_savepoint = state.get("type_savepoint", [])
        tool_metadata = state.get("tool_metadata", [])
        
        # Get LLM response
        routing, updated_history = self._invoke(messages, node)
        
        # Determine next step (handles conversion and logic internally)
        next_node = self._get_next_step(routing, tool_metadata, type_savepoint)

        # High-level summary log
        self.logger.info(
            "Router decided next_node=%s steps=%d partial=%s",
            next_node,
            len(routing.path) if routing.path else 0,
            self.is_partial,
        )
        
        return {
            "node": node,
            "next_node": next_node,
            "chosen_path": self.full_path,
            "is_partial": self.is_partial,
            "route_reasoning": routing.reasoning,
            "route_clarification": routing.clarification_question,
            "messages": updated_history,
            "type_savepoint": type_savepoint,
        }
    
    def _get_next_step(self, routing: RoutingResponse, tool_metadata: List[Dict[str, Any]], type_savepoint: List[str]) -> str:
        """Determine next step and convert path to full PathItems only if needed."""
        # Check if LLM needs clarification first
        if routing.clarification_question:
            # Convert full path (including nulls) since LLM has a plan but needs clarification
            self.full_path = self._convert_to_full_path(routing.path, tool_metadata)
            return "waiting_for_feedback"
        
        # Build lookup for tool metadata by name
        tools_by_name = {tool["name"]: tool for tool in tool_metadata}

        # Check for null values in simple path param_values first, ignoring keys with defaults
        for i, simple_step in enumerate(routing.path):
            tool_meta = tools_by_name.get(simple_step.name)
            default_keys = set((tool_meta.get("default_params") or {}).keys()) if tool_meta else set()
            has_non_default_none = any(
                (value is None) and (key not in default_keys)
                for key, value in simple_step.param_values.items()
            )
            if has_non_default_none:
                self.is_partial = True
                
                # Convert path up to this point to get param_types for previous step
                self.full_path = self._convert_to_full_path(routing.path, tool_metadata, up_to_index=i)
                
                # Find the previous tool and get its output type
                if i > 0:
                    previous_step = self.full_path[i - 1]
                    # Get the output type from the previous step's param_types
                    if previous_step.output_params:
                        # Typically output_params contains ['return'] for most tools
                        for output_param in previous_step.output_params:
                            if output_param in previous_step.param_types:
                                output_type = previous_step.param_types[output_param]
                                # Map the class to the enum using the new enum structure
                                try:
                                    enum_value = WorkflowTypeEnum.from_class(output_type)
                                except Exception:
                                    enum_value = None
                                if enum_value is not None:
                                    type_savepoint.append(enum_value)
                                break
                else:
                    # If this is the first step and has None values, 
                    # we need more information from user
                    return "waiting_for_feedback"
                
                return "find_path"
        
        self.full_path = self._convert_to_full_path(routing.path, tool_metadata)
        return "execute"
