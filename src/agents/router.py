from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent


class RoutingResponse(BaseModel):
    """Pydantic model for structured routing response."""
    path: dict = Field(
        description="Path for executor"
    )
    reasoning: str = Field(description="Explanation of routing decision")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if more information is needed"
    )


class Router(BaseAgent[RoutingResponse]):
    """
    Routing agent that determines which specialized agent should handle a classified task.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = "prompts/Router.yaml", output_type: str = None):
        """
        Initialize the Router agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
            is_partial: Whether the current path is partial
            output_type: Type of output to be generated
        """
        super().__init__(llm, RoutingResponse, prompt_path)
        self.is_partial = False
        self.output_type = output_type
    
    def route(self, user_input: str, message_history: List[BaseMessage] = None) -> tuple[RoutingResponse, List[BaseMessage]]:
        """
        Route the classified task to appropriate agent.
        
        Args:
            user_input: The raw user input (what gets stored in message history)
            message_history: Existing conversation history
            
        Returns:
            Tuple of (routing_result, updated_message_history)
        """
        return self._invoke_with_history(user_input, message_history, "Routing")
    
    def get_next_step(self, result: RoutingResponse) -> str:
        """Determine next step based on routing result."""
        if result.clarification_question:
            return "router_reiteration"
        
        # Check for null values in path param_values
        if isinstance(result.path, list):
            for path_obj in result.path:
                if "param_values" in path_obj and "output_params" in path_obj and "param_types" in path_obj:
                    param_values = path_obj["param_values"]
                    # Check if any param_values contain null
                    if any(value is None for value in param_values.values()):
                        # Get first output_param
                        if path_obj["output_params"]:
                            first_output_param = path_obj["output_params"][0]
                            # Change output_type to the type from param_types
                            if first_output_param in path_obj["param_types"]:
                                param_type = path_obj["param_types"][first_output_param]
                                self.output_type = param_type if isinstance(param_type, str) else str(param_type)
                                self.is_partial = True
                                return "path_generation"
        
        return "execution"
    
    def check_partial(self) -> bool:
        return self.is_partial
