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
from jinja2 import Template

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
        # Convert structured response to dict for storage when applicable
        if hasattr(structured_response, 'model_dump'):
            internal_data = structured_response.model_dump()
        elif isinstance(structured_response, dict):
            internal_data = structured_response
        elif isinstance(structured_response, str):
            # Simple text response
            return AIMessage(
                content=structured_response,
                response_metadata=additional_metadata,
            )
        else:
            # Fallback: store stringified content
            return AIMessage(
                content=str(structured_response),
                response_metadata=additional_metadata,
            )
        
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
        
        
        # If no content blocks, fallback to simple text content
        if not content_blocks:
            return AIMessage(
                content="No response generated",
                response_metadata=internal_data,
            )
        
        return AIMessage(
            content=content_blocks,
            response_metadata=internal_data,
        )
    
    def _invoke(
        self, 
        messages: List[BaseMessage],
        node: str,
        **kwargs: Any,
    ) -> tuple[ResponseType, List[BaseMessage]]:
        """
        Common method to invoke LLM and manage message history.
        
        Args:
            messages: Existing conversation history (may contain multimodal content)
            node: Name of the node for logging/tracking
            
        Returns:
            Tuple of (structured_response, updated_message_history)
        """
        # Create system message (render with kwargs if provided)
        system_prompt_text = self.prompt_config["system_prompt"]
        if kwargs:
            try:
                system_prompt_text = Template(system_prompt_text).render(**kwargs)
            except Exception as e:
                self.logger.warning("Failed to render system_prompt with kwargs: %s", e)
        system_msg = SystemMessage(content=system_prompt_text)
        
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

        # Add conversation history (filter out unsupported content blocks for LLM)
        filtered_messages = self._filter_messages_for_llm(messages)
        processing_messages += filtered_messages

        # Logging input context
        self.logger.info("Entering state: %s", node)
        self.logger.debug("Messages before invoke:\n%s", format_messages(filtered_messages))
        # Invoke LLM
        result = self.llm.invoke(
            processing_messages,
            options={
                "temperature": self.prompt_config.get("metadata", {}).get("temperature", 0.1),
                "max_tokens": self.prompt_config.get("metadata", {}).get("max_tokens", 500),
            },
        )
        print("result:")
        print(result)
        # Convert unstructured output to structured format if needed
        if not self._use_structured_output:
            # Try to parse JSON from content first
            raw_content = getattr(result, "content", "")
            parsed_obj = None
            if isinstance(raw_content, list):
                # Join text blocks into a single string for parsing attempt
                try:
                    text_parts = []
                    for block in raw_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    raw_text = "\n".join(text_parts)
                except Exception:
                    raw_text = ""
            else:
                raw_text = raw_content or ""

            try:
                if raw_text:
                    parsed_obj = self._parse_json_from_text(raw_text)
            except Exception:
                parsed_obj = None

            # If no JSON found in content, check tool calls for arguments
            if parsed_obj is None:
                tool_calls = getattr(result, "tool_calls", None)
                if not tool_calls:
                    tool_calls = getattr(result, "additional_kwargs", {}).get("tool_calls") if hasattr(result, "additional_kwargs") else None

                if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                    first_call = tool_calls[0]
                    call_args = None
                    # Handle dict-shaped tool call
                    if isinstance(first_call, dict):
                        call_args = first_call.get("args") or first_call.get("arguments")
                    else:
                        # Handle object-shaped tool call
                        call_args = getattr(first_call, "args", None) or getattr(first_call, "arguments", None)

                    if isinstance(call_args, dict):
                        parsed_obj = call_args
                    elif isinstance(call_args, str):
                        try:
                            parsed_obj = json.loads(call_args)
                        except Exception:
                            parsed_obj = None

            # If we found a JSON object, validate to schema; otherwise, leave as plain text
            if parsed_obj is not None:
                try:
                    result = self.response_schema.model_validate(parsed_obj)
                except Exception:
                    # If validation fails, keep original parsed object as a dict for downstream handling
                    result = parsed_obj
            else:
                # Fallback to plain content string
                result = raw_text if raw_text else (str(getattr(result, "content", "")))

        # Create response message and update history
        updated_messages = messages + [self.create_response_message(result, node=node)]
        
        # Log outputs
        log_section(self.logger, f"{node} result", result, level=logging.INFO)
        self.logger.debug("Updated messages after invoke:\n%s", format_messages(updated_messages))
        
        return result, updated_messages
    
    def _filter_messages_for_llm(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Filter messages to ensure they only contain content types supported by the LLM.
        Converts complex content blocks to simple text format.
        """
        filtered_messages = []
        
        for message in messages:
            if hasattr(message, 'content') and isinstance(message.content, list):
                # Handle content blocks - extract text content only
                text_parts = []
                
                for block in message.content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "reasoning":
                            # Convert reasoning to text with clear labeling
                            reasoning_text = block.get("reasoning", "")
                            if reasoning_text:
                                text_parts.append(f"[Thinking: {reasoning_text}]")
                        # Skip other content types that LLM might not support
                
                # Create new message with combined text content
                combined_text = "\n".join(text_parts).strip()
                if combined_text:
                    # Create new message of same type with simple text content
                    message_class = type(message)
                    filtered_message = message_class(content=combined_text)
                    # Preserve important attributes
                    if hasattr(message, 'additional_kwargs'):
                        filtered_message.additional_kwargs = message.additional_kwargs
                    if hasattr(message, 'response_metadata'):
                        filtered_message.response_metadata = message.response_metadata
                    filtered_messages.append(filtered_message)
            else:
                # Message already has simple content, keep as is
                filtered_messages.append(message)
        
        return filtered_messages

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