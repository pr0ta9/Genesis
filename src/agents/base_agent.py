from requests import options
import yaml
import logging
import os
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypeVar, Generic, Type, Optional, Generator
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from ..logging_utils import get_logger, pretty, format_messages, log_section
from jinja2 import Template

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
        # For now, keep support for unstructured models, but consider removing this
        model_name = getattr(llm, "model", "")
        self._use_structured_output = not (isinstance(model_name, str) and "gpt-oss" in model_name)

        if self._use_structured_output:
            self.llm = llm.with_structured_output(response_schema)
        else:
            self.llm = llm

        self.response_schema = response_schema
        self.prompt_config = self._load_prompt(prompt_path)
        self.logger = get_logger(f"agents.{self.__class__.__name__}")
        
    def _load_prompt(self, prompt_path: str) -> Dict[str, Any]:
        """Load prompt configuration from YAML file."""
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def create_response_message(self, structured_response: ResponseType, **additional_metadata: Any) -> AIMessage:
        """
        Create an AIMessage from the structured response.
        
        Args:
            structured_response: The structured response from the LLM
            **additional_metadata: Any additional metadata to store
            
        Returns:
            AIMessage with appropriate content and metadata
        """
        # Handle StructuredResult wrapper from unstructured models
        if hasattr(structured_response, 'structured_content'):
            # Use the structured content for internal data
            if hasattr(structured_response.structured_content, 'model_dump'):
                internal_data = structured_response.structured_content.model_dump()
            elif isinstance(structured_response.structured_content, dict):
                internal_data = structured_response.structured_content
            elif isinstance(structured_response.structured_content, str):
                internal_data = {"raw_output": structured_response.structured_content}
            else:
                internal_data = {"raw_output": str(structured_response.structured_content)}
                
            # Get additional_kwargs from original result
            additional_kwargs = structured_response.get("additional_kwargs", {})
        else:
            # Handle regular structured responses
            if hasattr(structured_response, 'model_dump'):
                internal_data = structured_response.model_dump()
            elif isinstance(structured_response, dict):
                internal_data = structured_response
            elif isinstance(structured_response, str):
                internal_data = {"raw_output": structured_response}
            else:
                internal_data = {"raw_output": str(structured_response)}
                
            # For regular responses, try to get additional_kwargs if it exists
            additional_kwargs = getattr(structured_response, 'additional_kwargs', {})
        
        # Add any additional metadata
        internal_data.update(additional_metadata)
        
        # Extract main response text (no fallbacks)
        main_response = internal_data.get("response") or internal_data.get("clarification_question") or ""
        
        # Return AIMessage with content and metadata
        return AIMessage(
            content=main_response,
            response_metadata=internal_data,
            additional_kwargs=additional_kwargs,
        )
    
    def _invoke(
        self, 
        messages: List[BaseMessage],
        node: str,
        **kwargs: Any,
    ) -> tuple[ResponseType, List[BaseMessage]]:
        """
        Invoke LLM and manage message history.
        
        Args:
            messages: Existing conversation history
            node: Name of the node for logging/tracking
            **kwargs: Additional parameters for template rendering
            
        Returns:
            Tuple of (structured_response, updated_message_history)
        """
        system_prompt_text = self._render_system_prompt(kwargs)

        # Format all messages as conversation text
        conversation_text = "\n\n## Conversation:\n"
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                conversation_text += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage) and msg.content:
                conversation_text += f"Assistant: {msg.content}\n"
            elif isinstance(msg, SystemMessage) and msg.content:
                conversation_text += f"System: {msg.content}\n"

        # Create enhanced system prompt with embedded conversation
        enhanced_system_content = system_prompt_text + conversation_text

        # Create processing messages with just the enhanced system message
        processing_messages = [SystemMessage(content=enhanced_system_content)]

        # Add JSON schema instruction if needed
        if not self._use_structured_output:
            processing_messages.append(self._create_json_instruction_message())

            # # Prepare system message
            # system_prompt_text = self._render_system_prompt(kwargs)
            # processing_messages = [SystemMessage(content=system_prompt_text)]

            # # Add JSON schema instruction for unstructured output
            # if not self._use_structured_output:
            #     processing_messages.append(self._create_json_instruction_message())

            # # Add conversation history
            # processing_messages += messages

            # # Log invocation
            # self.logger.info("Entering state: %s", node)
            # self.logger.debug("Messages before invoke:\n%s", format_messages(messages))
            
            # Prepare invocation parameters
        metadata = self.prompt_config.get("metadata", {})
        invoke_options = {
            "temperature": metadata.get("temperature", 0.1),
            "max_tokens": metadata.get("max_tokens", 500),
        }
        
        # Enable reasoning if configured in metadata
        invoke_kwargs = self.prompt_config.get("invoke_kwargs", {})

        # Check if we should emit reasoning content
        from ..streaming import emit_status, StatusType
        # Invoke LLM
        self.logger.info("Starting invoke for: %s", node)
        print(f"invoke_kwargs: {invoke_kwargs}")
        print(f"prompt:\n{processing_messages}")
        result = self.llm.invoke(
            processing_messages,
            options=invoke_options,
            **invoke_kwargs,
        )
        print(f"result: {result}")
        self.logger.info("Completed invoke for: %s", node)
        # Emit reasoning if available - wrapped in try/catch
        try:
            reasoning_content = result.additional_kwargs.get('reasoning_content')
            if reasoning_content:
                # Try to capture model think time (prompt_eval_duration is typically in nanoseconds)
                try:
                    prompt_eval_duration = 0
                    if hasattr(result, 'response_metadata') and isinstance(result.response_metadata, dict):
                        prompt_eval_duration = int(result.response_metadata.get('prompt_eval_duration') or 0)
                    # Format as requested: <think>{reasoning}</think>{prompt_eval_duration}</time>
                    reasoning_payload = f"<think>{reasoning_content}</think>{prompt_eval_duration}</time>"
                except Exception:
                    reasoning_payload = reasoning_content

                # Emit reasoning with embedded think time payload
                emit_status(StatusType.REASONING, node, reasoning_payload)
        except Exception as e:
            import traceback
            traceback.print_exc()

        # print("result:")
        # print(result)
        # Process result for unstructured models
        if not self._use_structured_output:
            processed_result = self._process_unstructured_result(result)
            # Extract the structured content for business logic
            structured_content = processed_result.structured_content
        else:
            processed_result = result
            structured_content = result
        print("processed_result:")
        print(processed_result)
        # Create response message and update history
        response_metadata = {"node": node}
            
        updated_messages = messages + [
            self.create_response_message(processed_result, **response_metadata)
        ]
        
        # Log results using the structured content
        log_section(self.logger, f"{node} result", structured_content, level=logging.INFO)
        self.logger.debug("Updated messages after invoke:\n%s", format_messages(updated_messages))
        
        return structured_content, updated_messages
    
    def _stream_invoke(
        self, 
        messages: List[BaseMessage],
        node: str,
        **kwargs: Any,
    ) -> Generator[tuple[str, Any], None, None]:
        """
        Streaming version of _invoke that yields reasoning chunks and final result.
        
        Args:
            messages: Existing conversation history
            node: Name of the node for logging/tracking
            **kwargs: Additional parameters for template rendering
            
        Yields:
            Tuple of (update_type, content) where:
            - ("reasoning", reasoning_text) for real-time reasoning updates
            - ("result", (structured_response, updated_messages)) for final result
        """
        # Prepare system message
        system_prompt_text = self._render_system_prompt(kwargs)
        processing_messages = [SystemMessage(content=system_prompt_text)]

        # Add JSON schema instruction for unstructured output
        if not self._use_structured_output:
            processing_messages.append(self._create_json_instruction_message())

        # Add conversation history
        processing_messages += messages

        # Log invocation
        self.logger.info("Entering streaming state: %s", node)
        self.logger.debug("Messages before stream invoke:\n%s", format_messages(messages))
        
        # Prepare invocation parameters
        metadata = self.prompt_config.get("metadata", {})
        invoke_options = {
            "temperature": metadata.get("temperature", 0.1),
            "max_tokens": metadata.get("max_tokens", 500),
        }
        
        # Enable reasoning for streaming
        invoke_kwargs = metadata.get("invoke_kwargs", {})
        invoke_kwargs["reasoning"] = True

        # Stream and yield reasoning chunks
        main_content_buffer = ""
        final_result = None
        
        # Check if we should emit reasoning content
        from ..streaming import emit_status, StatusType
        
        for chunk in self.llm.stream(
            processing_messages,
            options=invoke_options,
            **invoke_kwargs,
        ):
            # Yield reasoning content immediately for real-time updates
            if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                reasoning_content = chunk.additional_kwargs.get('reasoning_content')
                if reasoning_content:
                    print(f"🧠 Stream found reasoning content for {node}: {reasoning_content[:100]}...")
                    
                    # Check if streaming context is active
                    try:
                        from ..streaming import stream_writer_var
                        writer = stream_writer_var.get(None)
                        print(f"📡 Stream context active: {writer is not None}")
                        
                        # Emit to streaming context for WebSocket
                        emit_status(StatusType.REASONING, node, reasoning_content)
                        print(f"✅ Emitted stream reasoning event for {node}")
                    except Exception as e:
                        print(f"❌ Error emitting stream reasoning: {e}")
                    
                    yield ("reasoning", reasoning_content)
            
            # Buffer main content for final processing
            if hasattr(chunk, 'content') and chunk.content:
                main_content_buffer += chunk.content
            
            final_result = chunk

        print("final_result after streaming:")
        print(final_result)
        # Process final result (same as _invoke)
        if not self._use_structured_output:
            final_result.content = main_content_buffer
            processed_result = self._process_unstructured_result(final_result)
            structured_content = processed_result.structured_content
        else:
            structured_content = final_result
        
        # Create response message and update history
        response_metadata = {"node": node}
        updated_messages = messages + [
            self.create_response_message(
                processed_result if not self._use_structured_output else final_result, 
                **response_metadata
            )
        ]
        
        # Log final result
        log_section(self.logger, f"{node} streaming result", structured_content, level=logging.INFO)
        
        # Yield final result
        yield ("result", (structured_content, updated_messages))
    
    def _render_system_prompt(self, kwargs: Dict[str, Any]) -> str:
        """Render system prompt with template variables."""
        system_prompt_text = self.prompt_config["system_prompt"]
        if kwargs:
            try:
                return Template(system_prompt_text).render(**kwargs)
            except Exception as e:
                self.logger.warning("Failed to render system_prompt with kwargs: %s", e)
        return system_prompt_text
    
    def _create_json_instruction_message(self) -> SystemMessage:
        """Create JSON schema instruction for unstructured models."""
        try:
            schema_dict = self.response_schema.model_json_schema()
        except Exception:
            schema_dict = {"type": "object"}

        schema_text = json.dumps(schema_dict, ensure_ascii=False)
        json_instruction = (
            "You MUST respond ONLY with a single minified JSON object that strictly matches this JSON Schema. "
            "No extra text, no markdown, no code fences. JSON Schema: " + schema_text
        )
        return SystemMessage(content=json_instruction)
    
    def _process_unstructured_result(self, result: Any) -> Any:
        """Process and validate unstructured model output while preserving original metadata."""
        # Try to extract and parse JSON from the result
        raw_text = self._extract_text_from_result(result)
        parsed_obj = None
        
        # Try parsing from content
        if raw_text:
            try:
                parsed_obj = self._parse_json_from_text(raw_text)
            except Exception:
                pass
        
        # Try parsing from tool calls if content failed
        if parsed_obj is None:
            parsed_obj = self._extract_from_tool_calls(result)
        
        # Validate or fallback to structured data
        structured_content = None
        if parsed_obj is not None:
            try:
                structured_content = self.response_schema.model_validate(parsed_obj)
            except Exception:
                # If the parsed object is a JSON string (double-encoded), try parsing once more
                if isinstance(parsed_obj, str):
                    try:
                        reparsed = self._parse_json_from_text(parsed_obj)
                        try:
                            structured_content = self.response_schema.model_validate(reparsed)
                        except Exception:
                            structured_content = reparsed
                    except Exception:
                        structured_content = parsed_obj
                else:
                    structured_content = parsed_obj
        else:
            # Fallback to raw text
            structured_content = raw_text if raw_text else str(getattr(result, "content", ""))
        
        # Create a result object that preserves original metadata but has structured content
        class StructuredResult:
            def __init__(self, original_result, structured_content):
                self.structured_content = structured_content
                self.original_result = original_result
                
            def __getattr__(self, name):
                # Delegate to original result for attributes like additional_kwargs, response_metadata
                return getattr(self.original_result, name)
                
            def get(self, key, default=None):
                # Support dict-like access for backwards compatibility
                if hasattr(self.original_result, key):
                    return getattr(self.original_result, key)
                elif hasattr(self.original_result, 'get') and callable(getattr(self.original_result, 'get')):
                    return self.original_result.get(key, default)
                else:
                    return default
        
        return StructuredResult(result, structured_content)
    
    def _extract_text_from_result(self, result: Any) -> str:
        """Extract text content from result object."""
        raw_content = getattr(result, "content", "")
        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return "\n".join(text_parts)
        return raw_content or ""
    
    def _extract_from_tool_calls(self, result: Any) -> Optional[Dict[str, Any]]:
        """Try to extract JSON from tool calls."""
        tool_calls = getattr(result, "tool_calls", None)
        if not tool_calls:
            tool_calls = getattr(result, "additional_kwargs", {}).get("tool_calls") if hasattr(result, "additional_kwargs") else None

        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            first_call = tool_calls[0]
            call_args = None
            
            if isinstance(first_call, dict):
                call_args = first_call.get("args") or first_call.get("arguments")
            else:
                call_args = getattr(first_call, "args", None) or getattr(first_call, "arguments", None)

            if isinstance(call_args, dict):
                return call_args
            elif isinstance(call_args, str):
                try:
                    return json.loads(call_args)
                except Exception:
                    # Try repaired tool call args
                    try:
                        repaired = self._repair_unescaped_backslashes(call_args)
                        return json.loads(repaired)
                    except Exception:
                        pass
        return None

    def _parse_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract and parse a JSON object from text."""
        # Direct parse
        try:
            return json.loads(text)
        except Exception:
            # Try repairing common issues like unescaped backslashes in Windows paths
            try:
                repaired = self._repair_unescaped_backslashes(text)
                return json.loads(repaired)
            except Exception:
                pass

        # Handle markdown fences
        fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        m = re.search(fence_pattern, text, re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                # Try repaired content inside fence
                try:
                    repaired = self._repair_unescaped_backslashes(m.group(1))
                    return json.loads(repaired)
                except Exception:
                    pass

        # Extract JSON substring
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                # Try repaired substring
                try:
                    repaired = self._repair_unescaped_backslashes(text[start:end + 1])
                    return json.loads(repaired)
                except Exception:
                    pass

        raise ValueError("Failed to parse JSON from model output")

    def _repair_unescaped_backslashes(self, text: str) -> str:
        """Repair unescaped backslashes inside JSON string literals."""
        # Match JSON double-quoted strings, including escaped quotes inside
        string_pattern = re.compile(r'"(?:[^"\\]|\\.)*"')

        def fix_string(m: re.Match) -> str:
            s = m.group(0)
            inner = s[1:-1]
            # Replace a single backslash that is not already escaped and not starting a valid JSON escape
            # Valid escapes after backslash: " \\ \/ \b \f \n \r \t \u
            fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', inner)
            return '"' + fixed + '"'

        return string_pattern.sub(fix_string, text)
    
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