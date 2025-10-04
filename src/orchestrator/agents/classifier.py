import os
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..core.state import State
from ..path import WorkflowTypeEnum

class ClassificationResponse(BaseModel):
    """Pydantic model for structured classification response."""
    objective: str = Field(description="The main objective or task to be accomplished")
    input_type: WorkflowTypeEnum = Field(description="Type of input provided by the user as a string label")
    output_type: WorkflowTypeEnum = Field(description="Expected type of output to be delivered as a string label")
    is_complex: bool = Field(description="Whether the task requires complex processing beyond simple web search")
    reasoning: str = Field(description="Explanation of the classification decision")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if more information is needed"
    )

    
class Classifier(BaseAgent[ClassificationResponse]):
    """
    Task classification agent that analyzes user requests and provides structured classification.
    Uses LangChain's structured output to return a ClassificationResponse with objective, 
    input/output types, complexity assessment, reasoning, and optional clarification questions.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = os.path.join(os.path.dirname(__file__), 'prompts', 'Classifier.yaml')):
        """
        Initialize the Classifier agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, ClassificationResponse, prompt_path)
    
    def classify(self, state: State) -> Dict[str, Any]:
        """
        Classify the user's request and determine the task type.
        
        Args:
            state: The current state of the workflow
            message_history: Existing conversation history
            
        Returns:
            Tuple of (classification_result, updated_message_history)
        """
        node = "classify"
        messages: List[BaseMessage] = state.get("messages", [])
        # Extract latest human input from message history

        classification, updated_history = self._invoke(messages, node)

        # Coerce unstructured results into ClassificationResponse
        if isinstance(classification, str):
            # Put the raw string into cot, everything else defaults; ensure is_complex=Falsensure is_complex=False
            from ..path import WorkflowTypeEnum
            classification = ClassificationResponse(
                objective="free_text",
                input_type=WorkflowTypeEnum.TEXT,
                output_type=WorkflowTypeEnum.TEXT,
                is_complex=False,
                reasoning="",
                clarification_question=None,
            )
        elif isinstance(classification, dict):
            try:
                classification = ClassificationResponse.model_validate(classification)
            except Exception:
                from ..path import WorkflowTypeEnum
                classification = ClassificationResponse(
                    objective=str(classification.get("objective", "free_text")),
                    input_type=classification.get("input_type", WorkflowTypeEnum.TEXT),
                    output_type=classification.get("output_type", WorkflowTypeEnum.TEXT),
                    is_complex=bool(classification.get("is_complex", False)),
                    reasoning=str(classification.get("reasoning", "")),
                    clarification_question=classification.get("clarification_question"),
                )

        next_node = self._get_next_step(classification)

        # High-level summary log
        self.logger.info(
            "Classifier decided next_node=%s input=%s output=%s complex=%s",
            next_node,
            classification.input_type,
            classification.output_type,
            classification.is_complex,
        )

        return {
            "node": node,
            "next_node": next_node,
            "objective": classification.objective,
            "input_type": classification.input_type,  # Now a string
            "type_savepoint": [classification.output_type],  # Now a list of strings
            "is_complex": classification.is_complex,
            "classify_reasoning": classification.reasoning,
            "classify_clarification": classification.clarification_question,
            "messages": updated_history,
        }
    
    def _get_next_step(self, result: ClassificationResponse) -> str:
        """Determine next step based on classification result."""
        if result.clarification_question:
            return "waiting_for_feedback"
        elif result.is_complex:
            return "find_path"
        else:
            return "finalize"
