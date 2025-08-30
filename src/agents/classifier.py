from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent


class ClassificationResponse(BaseModel):
    """Pydantic model for structured classification response."""
    objective: str = Field(description="The main objective or task to be accomplished")
    input_type: Literal[
        "text", "pdf_document", "image", "audio", "video", "web_url", 
        "file_upload", "database_query", "api_request", "code"
    ] = Field(description="Type of input provided by the user")
    output_type: Literal[
        "text_response", "completed_document", "image", "audio", "video", 
        "file_download", "data_visualization", "code", "analysis_report"
    ] = Field(description="Expected type of output to be delivered")
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
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = "prompts/Classifier.yaml"):
        """
        Initialize the Classifier agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, ClassificationResponse, prompt_path)
    
    def get_default_prompt_path(self) -> str:
        """Return the default prompt path for the Classifier."""
        return "prompts/Classifier.yaml"
    
    def classify(self, user_input: str, message_history: List[BaseMessage] = None) -> tuple[ClassificationResponse, List[BaseMessage]]:
        """
        Classify the user's request and determine the task type.
        
        Args:
            user_input: The raw user input (what gets stored in message history)
            message_history: Existing conversation history
            
        Returns:
            Tuple of (classification_result, updated_message_history)
        """
        return self._invoke_with_history(user_input, message_history, "Classification")
    
    def get_next_step(self, result: ClassificationResponse) -> str:
        """Determine next step based on classification result."""
        if result.clarification_question:
            return "classify_reiteration"
        elif result.is_complex:
            return "path_generation"
        else:
            return "finalization"