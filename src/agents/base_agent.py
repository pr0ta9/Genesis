import yaml
from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypeVar, Generic
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

# Generic type for response schemas
ResponseType = TypeVar('ResponseType', bound=BaseModel)


class BaseAgent(ABC, Generic[ResponseType]):
    """
    Base class for all agents that use structured output with YAML prompts.
    
    Provides common functionality for:
    - Loading YAML prompt configurations
    - Creating chat templates
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
        self.chat_template = self._create_chat_template()
        
    def _load_prompt(self, prompt_path: str) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        with open(prompt_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _create_chat_template(self) -> ChatPromptTemplate:
        """Create ChatPromptTemplate from loaded prompt configuration."""
        return ChatPromptTemplate.from_messages([
            ("system", self.prompt_config["system_prompt"]),
            ("human", self.prompt_config["human_prompt_template"])
        ])
    
    def _invoke_with_history(
        self, 
        user_input: str, 
        message_history: List[BaseMessage] = None,
        action_name: str = "Processing"
    ) -> tuple[ResponseType, List[BaseMessage]]:
        """
        Common method to invoke LLM and manage message history.
        
        Args:
            user_input: The raw user input
            message_history: Existing conversation history
            action_name: Name of the action for history logging (e.g., "Classification", "Routing")
            
        Returns:
            Tuple of (structured_response, updated_message_history)
        """
        # Initialize message history if None
        if message_history is None:
            message_history = []
        
        # Create messages with template (for processing only, not stored)
        processing_messages = self.chat_template.format_messages(input=user_input)
        
        # Get structured LLM response
        result = self.llm.invoke(
            processing_messages,
            temperature=self.prompt_config.get("metadata", {}).get("temperature", 0.1),
            max_tokens=self.prompt_config.get("metadata", {}).get("max_tokens", 500)
        )
        
        # Add both user input and AI response to message history
        updated_history = message_history + [
            HumanMessage(content=user_input),
            AIMessage(content=f"{action_name}: {result.model_dump_json()}")
        ]
            
        return result, updated_history
        
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
