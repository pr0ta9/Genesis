import yaml
from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypeVar, Generic
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

# Generic type for response schemas
ResponseType = TypeVar('ResponseType', bound=BaseModel)


class BaseAgent(ABC, Generic[ResponseType]):
    """
    Base class for all agents that use structured output with YAML prompts.
    
    Provides common functionality for:
    - Loading YAML prompt configurations
    - Managing structured LLM output
    - Handling message history
    """
    
    def __init__(self, llm: BaseChatModel, response_schema: type[ResponseType], prompt_path: str):
        """
        Initialize the agent with structured output.
        
        Args:
            llm: The language model instance to use
            response_schema: Pydantic model class for structured responses
            prompt_path: Path to the YAML prompt configuration file
        """
        self.llm = llm.with_structured_output(response_schema)
        self.response_schema = response_schema
        self.prompt_config = self._load_prompt(prompt_path)
        
    def _load_prompt(self, prompt_path: str) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        with open(prompt_path, 'r') as f:
            return yaml.safe_load(f)
    
    def create_response_message(self, structured_response: ResponseType, **additional_metadata: Any) -> AIMessage:
        """
        Create an AIMessage with internal reasoning stored in metadata.
        
        Args:
            structured_response: The structured response from the LLM
            user_response: The user-facing response text
            **additional_metadata: Any additional metadata to store
            
        Returns:
            AIMessage with user response as content and reasoning in metadata
        """
        # Convert structured response to dict for storage
        internal_data = structured_response.model_dump() if hasattr(structured_response, 'model_dump') else dict(structured_response)
        
        # Add any additional metadata
        internal_data.update(additional_metadata)
        
        return AIMessage(
            content=internal_data.get("response") or internal_data.get("clarification_question") or internal_data.get("cot", ""),
            response_metadata=internal_data,
        )
    
    def _invoke(
        self, 
        messages: List[BaseMessage],
        node: str,
    ) -> tuple[ResponseType, List[BaseMessage]]:
        """
        Common method to invoke LLM and manage message history.
        
        Args:
            messages: Existing conversation history
            node: Name of the node for logging/tracking
            
        Returns:
            Tuple of (structured_response, updated_message_history)
        """
        # Create system message
        system_msg = SystemMessage(content=self.prompt_config["system_prompt"])
        
        # Build processing messages: [SystemMessage] + messages
        processing_messages = [system_msg] + messages
        
        # Get structured LLM response
        result = self.llm.invoke(
            processing_messages,
            temperature=self.prompt_config.get("metadata", {}).get("temperature", 0.1),
            max_tokens=self.prompt_config.get("metadata", {}).get("max_tokens", 500)
        )
        updated_messages = messages + [self.create_response_message(result, node)]
        return result, updated_messages
        
    @abstractmethod
    def get_next_step(self, result: ResponseType) -> str:
        """
        Determine the next step based on the agent's output.
        
        Args:
            result: The structured response from this agent
            
        Returns:
            String indicating the next step to take
        """
        pass