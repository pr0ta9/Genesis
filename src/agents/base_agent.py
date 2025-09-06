import yaml
import logging
import os
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypeVar, Generic, Type, ClassVar
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from ..logging_utils import get_logger, pretty, format_messages, log_section

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
        # Detect models that have limited JSON Schema support (e.g., gpt-oss via Ollama)
        model_name = getattr(llm, "model", "")
        self._use_structured_output = not (isinstance(model_name, str) and "gpt-oss" in model_name)

        if self._use_structured_output:
            self.llm = llm.with_structured_output(response_schema)
        else:
            # Keep raw LLM; we'll enforce JSON via instruction + post-parse
            self.llm = llm

        self.response_schema = response_schema
        self.prompt_config = self._load_prompt(prompt_path)
        self.logger = get_logger(f"agents.{self.__class__.__name__}")
        
    def _load_prompt(self, prompt_path: str) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        with open(prompt_path, 'r') as f:
            return yaml.safe_load(f)
    
    def create_response_message(self, structured_response: ResponseType, **additional_metadata: Any) -> AIMessage:
        """
        Create an AIMessage with reasoning stored as content blocks and metadata.
        
        Args:
            structured_response: The structured response from the LLM
            **additional_metadata: Any additional metadata to store
            
        Returns:
            AIMessage with content blocks for reasoning and user response
        """
        # Convert structured response to dict for storage
        internal_data = structured_response.model_dump() if hasattr(structured_response, 'model_dump') else dict(structured_response)
        
        # Add any additional metadata
        internal_data.update(additional_metadata)
        
        # Create content blocks for the message
        content_blocks = []
        
        # Add reasoning block if present (this is our cot)
        if internal_data.get("cot"):
            content_blocks.append({
                "type": "reasoning",
                "reasoning": internal_data["cot"]
            })
        
        # Add main response text block
        main_response = (
            internal_data.get("response") or 
            internal_data.get("clarification_question") or 
            internal_data.get("reasoning", "")  # fallback to reasoning field
        )
        
        if main_response:
            content_blocks.append({
                "type": "text", 
                "text": main_response
            })
        
        # Create clean metadata (exclude cot since it's now in content blocks)
        metadata = {k: v for k, v in internal_data.items() if k != "cot"}
        
        # If no content blocks, fallback to simple text content
        if not content_blocks:
            return AIMessage(
                content="No response generated",
                response_metadata=metadata,
            )
        
        return AIMessage(
            content=content_blocks,
            response_metadata=metadata,
        )
    
    def _invoke(
        self, 
        messages: List[BaseMessage],
        node: str,
    ) -> tuple[ResponseType, List[BaseMessage]]:
        """
        Common method to invoke LLM and manage message history.
        
        Args:
            messages: Existing conversation history (may contain multimodal content)
            node: Name of the node for logging/tracking
            
        Returns:
            Tuple of (structured_response, updated_message_history)
        """
        # Create system message
        system_msg = SystemMessage(content=self.prompt_config["system_prompt"])
        
        # Build processing messages
        processing_messages = [system_msg]

        # Add JSON schema instruction for unstructured output
        if not self._use_structured_output:
            try:
                schema_dict = self.response_schema.model_json_schema()
            except Exception:
                schema_dict = {"type": "object"}

            schema_text = json.dumps(schema_dict, ensure_ascii=False)
            json_instruction = (
                "You MUST respond ONLY with a single minified JSON object that strictly matches this JSON Schema. "
                "No extra text, no markdown, no code fences. JSON Schema: " + schema_text
            )
            processing_messages.append(SystemMessage(content=json_instruction))

        # Add conversation history
        processing_messages += messages

        # Logging input context
        self.logger.info("Entering state: %s", node)
        self.logger.debug("Messages before invoke:\n%s", format_messages(messages))

        # Invoke LLM
        result = self.llm.invoke(
            processing_messages,
            options={
                "temperature": self.prompt_config.get("metadata", {}).get("temperature", 0.1),
                "max_tokens": self.prompt_config.get("metadata", {}).get("max_tokens", 500),
            },
        )

        # Convert unstructured output to structured format if needed
        if not self._use_structured_output:
            raw_content = getattr(result, "content", "")
            parsed_obj = self._parse_json_from_text(raw_content)
            result = self.response_schema.model_validate(parsed_obj)

        # Create response message and update history
        updated_messages = messages + [self.create_response_message(result, node=node)]
        
        # Log outputs
        log_section(self.logger, f"{node} result", result, level=logging.INFO)
        self.logger.debug("Updated messages after invoke:\n%s", format_messages(updated_messages))
        
        return result, updated_messages

    def _parse_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract and parse a JSON object from model text output robustly."""
        # Attempt direct parse first
        try:
            return json.loads(text)
        except Exception:
            pass

        # Handle markdown fences
        fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        m = re.search(fence_pattern, text, re.IGNORECASE)
        if m:
            inner = m.group(1)
            try:
                return json.loads(inner)
            except Exception:
                pass

        # Extract substring between first '{' and last '}'
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        raise ValueError("Failed to parse JSON from model output")
        
    @abstractmethod
    def _get_next_step(self, result: ResponseType) -> str:
        """
        Determine the next step based on the agent's output.
        
        Args:
            result: The structured response from this agent
            
        Returns:
            String indicating the next step to take
        """
        pass