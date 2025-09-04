from typing import List, Optional, Type, Any, ClassVar, Dict
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..state import State
from ..path import (
    WorkflowType,
    Text,
    AudioFile,
    ImageFile,
    VideoFile,
    TextFile,
    DocumentFile,
    StructuredData,
)


class ClassificationResponse(BaseModel):
    """Pydantic model for structured classification response."""
    objective: str = Field(description="The main objective or task to be accomplished")
    input_type: Type[WorkflowType] = Field(description="Type of input provided by the user as a WorkflowType class")
    output_type: Type[WorkflowType] = Field(description="Expected type of output to be delivered as a WorkflowType class")
    is_complex: bool = Field(description="Whether the task requires complex processing beyond simple web search")
    reasoning: str = Field(description="Explanation of the classification decision")
    cot: str = Field(description="Step-by-step thinking process, one thought per line")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if more information is needed"
    )

    # Strict label-to-type mappings (only the listed classes)
    _ALLOWED_LABELS: ClassVar[dict] = {
        "text": Text,
        "audiofile": AudioFile,
        "imagefile": ImageFile,
        "videofile": VideoFile,
        "textfile": TextFile,
        "documentfile": DocumentFile,
        "structureddata": StructuredData,
    }

    @field_validator("input_type", mode="before")  # type: ignore[misc]
    def _coerce_input_type(cls, v: Any):  # type: ignore[override]
        if isinstance(v, type) and issubclass(v, WorkflowType):
            return v
        if isinstance(v, str):
            key = v.strip().lower()
            if key in cls._ALLOWED_LABELS:
                return cls._ALLOWED_LABELS[key]
        raise ValueError("input_type must be one of: Text, AudioFile, ImageFile, VideoFile, TextFile, DocumentFile, StructuredData (or their string names)")

    @field_validator("output_type", mode="before")  # type: ignore[misc]
    def _coerce_output_type(cls, v: Any):  # type: ignore[override]
        if isinstance(v, type) and issubclass(v, WorkflowType):
            return v
        if isinstance(v, str):
            key = v.strip().lower()
            if key in cls._ALLOWED_LABELS:
                return cls._ALLOWED_LABELS[key]
        raise ValueError("output_type must be one of: Text, AudioFile, ImageFile, VideoFile, TextFile, DocumentFile, StructuredData (or their string names)")
    
class Classifier(BaseAgent[ClassificationResponse]):
    """
    Task classification agent that analyzes user requests and provides structured classification.
    Uses LangChain's structured output to return a ClassificationResponse with objective, 
    input/output types, complexity assessment, reasoning, and optional clarification questions.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = "prompts/Classifier.yaml"):
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

        next_node = self._get_next_step(classification)

        return {
            "node": node,
            "next_node": next_node,
            "objective": classification.objective,
            "input_type": classification.input_type.value,
            "type_savepoint": [classification.output_type.value],
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
            return "path_generation"
        else:
            return "finalization"