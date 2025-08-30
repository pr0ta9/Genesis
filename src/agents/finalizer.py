from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent


class FinalizationResponse(BaseModel):
    """Pydantic model for structured finalization response."""
    is_complete: bool = Field(description="Whether the task is complete")
    response: str = Field(
        default="", description="The final response to the user"
    )
    reasoning: str = Field(description="Explanation of how the final answer was constructed")
    summary: Optional[str] = Field(
        default=None, description="Summary of previous outputs"
    )


class Finalizer(BaseAgent[FinalizationResponse]):
    """
    Finalization agent that produces the final structured response to the user.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = "prompts/Finalizer.yaml"):
        """
        Initialize the Finalizer agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, FinalizationResponse, prompt_path)
    
    def finalize(self, user_input: str, message_history: List[BaseMessage] = None) -> tuple[FinalizationResponse, List[BaseMessage]]:
        """
        Create the final response based on all previous agent outputs.
        
        Args:
            user_input: The raw user input (what gets stored in message history)
            message_history: Existing conversation history
            
        Returns:
            Tuple of (finalization_result, updated_message_history)
        """
        return self._invoke_with_history(user_input, message_history, "Finalization")
    
    def get_next_step(self, result: FinalizationResponse, is_partial: bool = False) -> str:
        """Determine next step based on finalization result."""
        if result.is_complete and not is_partial:
            return "END"
        else:
            return "path_generation"
