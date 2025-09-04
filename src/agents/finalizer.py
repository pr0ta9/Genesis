from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..state import State


class FinalizationResponse(BaseModel):
    """Pydantic model for structured finalization response."""
    is_complete: bool = Field(description="Whether the task is complete")
    response: str = Field(
        default="", description="The final response to the user"
    )
    reasoning: str = Field(description="Explanation of how the final answer was constructed")
    cot: str = Field(description="Step-by-step thinking process, one thought per line")
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
    
    def finalize(self, state: State) -> Dict[str, Any]:
        """
        Create the final response based on all previous agent outputs.
        
        Args:
            user_input: The raw user input (what gets stored in message history)
            message_history: Existing conversation history
            
        Returns:
            Tuple of (finalization_result, updated_message_history)
        """
        node = "finalize"
        messages: List[BaseMessage] = state.get("messages", [])
        finalization, updated_history = self._invoke(messages, node)

        next_node = self._get_next_step(finalization, state.get("is_partial", False))

        return {
            "node": node,
            "next_node": next_node,
            "is_complete": finalization.is_complete,
            "response": finalization.response,
            "finalize_reasoning": finalization.reasoning,
            "summary": finalization.summary,
            "messages": updated_history,
        }
    def get_next_step(self, result: FinalizationResponse, is_partial: bool = False) -> str:
        """Determine next step based on finalization result."""
        if result.is_complete and not is_partial:
            return "END"
        else:
            return "find_path"
