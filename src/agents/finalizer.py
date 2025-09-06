import os
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..logging_utils import pretty
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
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = os.path.join(os.path.dirname(__file__), 'prompts', 'Finalizer.yaml')):
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
            state: The current state containing messages and execution results
            
        Returns:
            Dictionary containing finalization results and updated state
        """
        node = "finalize"
        messages: List[BaseMessage] = state.get("messages", [])
        execution_results = state.get("execution_results")
        
        # Create a special message containing execution results for the LLM to see
        if execution_results:
            from langchain_core.messages import SystemMessage
            execution_summary = self._format_execution_results(execution_results)
            execution_message = SystemMessage(
                content=f"EXECUTION RESULTS:\n{execution_summary}"
            )
            messages_with_execution = messages + [execution_message]
        else:
            messages_with_execution = messages
            
        finalization, updated_history = self._invoke(messages_with_execution, node)

        next_node = self._get_next_step(finalization, state.get("is_partial", False))

        # High-level summary log
        self.logger.info(
            "Finalizer decided next_node=%s is_complete=%s",
            next_node,
            finalization.is_complete,
        )

        return {
            "node": node,
            "next_node": next_node,
            "is_complete": finalization.is_complete,
            "response": finalization.response,
            "finalize_reasoning": finalization.reasoning,
            "summary": finalization.summary,
            "messages": updated_history,
        }
        
    def _format_execution_results(self, execution_results) -> str:
        """
        Format execution results into a readable summary for the LLM.
        
        Args:
            execution_results: Dict containing execution info (from ExecutionResult.to_dict())
            
        Returns:
            Formatted string summary of execution results
        """
        if isinstance(execution_results, dict):
            # Already a dictionary (from ExecutionResult.to_dict())
            result_dict = execution_results
        else:
            return f"Execution completed with result: {execution_results}"
            
        summary = []
        summary.append(f"Success: {result_dict.get('success', False)}")
        summary.append(f"Execution Path: {' -> '.join(result_dict.get('execution_path', []))}")
        summary.append(f"Steps Completed: {result_dict.get('steps_completed', 0)}")
        
        if result_dict.get('final_output'):
            summary.append(f"Final Output: {result_dict['final_output']}")
            
        if result_dict.get('error_info'):
            summary.append(f"Error Info: {result_dict['error_info']}")
            
        return "\n".join(summary)
    def _get_next_step(self, result: FinalizationResponse, is_partial: bool = False) -> str:
        """Determine next step based on finalization result."""
        if result.is_complete and not is_partial:
            return "END"
        else:
            return "find_path"
