import os
import json
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..core.logging_utils import pretty
from ..path import WorkflowTypeEnum, SimplePath, PathItem
from ..core.state import State
from pathlib import Path

class RoutingResponse(BaseModel):
    """Routing response from LLM."""
    path: List[SimplePath] = Field(description="Simple path with names and param values")
    reasoning: str = Field(description="Explanation of routing decision")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if more information is needed"
    )


class Router(BaseAgent[RoutingResponse]):
    """
    Routing agent that determines which specialized agent should handle a classified task.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = os.path.join(os.path.dirname(__file__), 'prompts', 'Router.yaml')):
        """
        Initialize the Router agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, RoutingResponse, prompt_path)
        self.is_partial = False
        self.full_path: List[PathItem] = []
    
    def _extract_files_from_messages(self, messages: List[BaseMessage]) -> List[str]:
        """
        Extract filenames from <file>...</file> tags in message history.
        
        Parses tags like <file>inputs/chat_123/test.png</file> and extracts just "test.png".
        Path resolution happens during execution.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            List of unique filenames (e.g., ["test.png", "document.pdf"])
        """
        files = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                # Extract filename from <file>...</file> tags
                # Pattern: <file>path/to/file.ext</file> -> file.ext
                matches = re.findall(r'<file>(?:.*[/\\])?([^/\\<]+)</file>', msg.content)
                files.extend(matches)
        
        # Deduplicate while preserving order (dict keys maintain insertion order in Python 3.7+)
        return list(dict.fromkeys(files))
    
    def _convert_to_full_path(self, simple_path: List[SimplePath], tool_metadata: List[Dict[str, Any]], up_to_index: int = None) -> List[PathItem]:
        """Convert simple LLM response to full PathItems using tool_metadata."""
        full_path = []
        
        # Create lookup dict for tool metadata by name
        tools_by_name = {tool["name"]: tool for tool in tool_metadata}
        
        # Convert only up to specified index (or all if None)
        end_index = up_to_index + 1 if up_to_index is not None else len(simple_path)
        
        for i in range(end_index):
            simple_step = simple_path[i]
            tool_meta = tools_by_name[simple_step.name]  # No need for error handling
            # Merge defaults: if a param is explicitly set to None and a default exists, use the default
            # Also fill in any missing defaulted params
            merged_values = dict(simple_step.param_values or {})
            default_params = (tool_meta.get("default_params") or {})
            for key, meta in default_params.items():
                default_value = (meta or {}).get("value")
                if key not in merged_values or merged_values.get(key) is None:
                    # Only set when missing or explicitly None
                    merged_values[key] = default_value
            
            # Build complete PathItem from metadata
            path_item = PathItem(
                name=simple_step.name,
                description=tool_meta["description"],
                function=None,  # Will be resolved during execution
                input_params=tool_meta["input_params"],
                output_params=tool_meta["output_params"], 
                param_values=merged_values,
                param_types=tool_meta["param_types"]
            )
            full_path.append(path_item)
        
        return full_path
    
    def route(self, state: State) -> Dict[str, Any]:
        """
        Route the classified task to appropriate agent.
        
        Args:
            state: Current state containing messages and type_savepoint
            
        Returns:
            Dictionary containing routing results and updated state
        """
        node = "route"
        messages: List[BaseMessage] = state.get("messages", [])
        type_savepoint = state.get("type_savepoint", [])
        tool_metadata = state.get("tool_metadata", [])
        all_paths = state.get("all_paths", [])
        
        # Extract available files from <file> tags in message history
        available_files: List[str] = self._extract_files_from_messages(messages)

        # Extract classification data from state (from classify or precedent node)
        classification = {
            "objective": state.get("objective", ""),
            "input_type": state.get("input_type", "").value, 
            "output_type": state.get("type_savepoint", [])[-1].value if state.get("type_savepoint") else "",
            "is_complex": state.get("is_complex", False),
            "reasoning": state.get("classify_reasoning") or state.get("precedent_reasoning", "")
        }
        
        # Get precedents from state (searched by orchestrator)
        precedents_found = state.get("precedents_found", [])
        print(f"📋 [ROUTER] Formatting {len(precedents_found)} precedents as examples...")
        precedent_examples = self._format_precedent_examples(precedents_found)
        if precedent_examples:
            print(f"✅ [ROUTER] Generated precedent examples: {len(precedent_examples)} chars")
        else:
            print("ℹ️  [ROUTER] No precedent examples available")
        
        routing, updated_history = self._invoke(
            messages,
            node,
            available_paths=all_paths,
            tool_descriptions=tool_metadata,
            available_files=available_files,
            classification=classification,
            precedent_examples=precedent_examples,
        )
        print(f"routing result: {routing}")
        # Coerce/normalize unstructured JSON string/dict into RoutingResponse
        if isinstance(routing, str):
            try:
                # Try direct JSON parsing first
                routing = RoutingResponse.model_validate(json.loads(routing))
            except Exception:
                try:
                    # Try to extract JSON from mixed text content
                    import re
                    json_pattern = r'\{.*\}'
                    json_match = re.search(json_pattern, routing, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        print(f"[ROUTER DEBUG] Extracted JSON from mixed content: {json_str[:100]}...")
                        data = json.loads(json_str)
                        routing = RoutingResponse.model_validate(data)
                    else:
                        print("[ROUTER DEBUG] No JSON found in LLM response")
                        routing = None
                except Exception as e:
                    print(f"[ROUTER DEBUG] JSON extraction failed: {e}")
                    routing = None
        elif isinstance(routing, dict):
            pass

        # Normalize keys per step (tool_name -> name) and strip output_path
        if isinstance(routing, dict) and isinstance(routing.get("path"), list):
            for step in routing.get("path", []):
                if isinstance(step, dict):
                    if "tool_name" in step and "name" not in step:
                        step["name"] = step.pop("tool_name")
                    pv = step.get("param_values")
                    if isinstance(pv, dict) and "output_path" in pv:
                        pv.pop("output_path", None)
            try:
                routing = RoutingResponse.model_validate(routing)
            except Exception:
                routing = None

        # Fallback: if routing is invalid or empty, ask for clarification instead of crashing
        if not isinstance(routing, RoutingResponse):
            routing = RoutingResponse(
                path=[],
                reasoning="Routing model returned an invalid/empty response; requesting clarification.",
                clarification_question="Please confirm the desired steps/tools so I can proceed."
            )
        
        # Determine next step (handles conversion and logic internally)
        print(f"[ROUTER DEBUG] About to call _get_next_step with {len(routing.path)} steps")
        try:
            next_node = self._get_next_step(routing, tool_metadata, type_savepoint)
            print(f"[ROUTER DEBUG] _get_next_step returned: {next_node}")
            print(f"[ROUTER DEBUG] self.full_path has {len(self.full_path) if self.full_path else 0} items")
        except Exception as e:
            print(f"[ROUTER DEBUG] ERROR in _get_next_step: {e}")
            import traceback
            traceback.print_exc()
            raise

        # High-level summary log
        self.logger.info(
            "Router decided next_node=%s steps=%d partial=%s",
            next_node,
            len(routing.path) if routing.path else 0,
            self.is_partial,
        )
        
        return {
            "node": node,
            "next_node": next_node,
            "chosen_path": self.full_path,
            "is_partial": self.is_partial,
            "route_reasoning": routing.reasoning,
            "route_clarification": routing.clarification_question,
            "messages": updated_history,
            "type_savepoint": type_savepoint,
        }
    
    def _format_precedent_examples(self, precedents: List[Dict]) -> str:
        """Format precedents into example strings for the prompt."""
        print(f"🔄 [ROUTER] Formatting {len(precedents)} precedents into examples...")
        
        if not precedents:
            print("ℹ️  [ROUTER] No precedents provided for examples")
            return ""
        
        example_parts = []
        try:
            import json
            for i, precedent in enumerate(precedents):
                router_response = precedent.get("router_format", {})
                if router_response and isinstance(router_response, dict):
                    # Format as JSON example
                    example_json = json.dumps(router_response, indent=2)
                    objective = precedent.get("objective", "Previous task")
                    example_parts.append(f"### Example {i+1}: {objective}\n```json\n{example_json}\n```")
                    print(f"📝 [ROUTER] Added example {i+1}: '{objective[:60]}...' ({len(example_json)} chars)")
                else:
                    print(f"⚠️  [ROUTER] Skipped precedent {i+1}: no router_format data")
            
            result = "\n\n".join(example_parts) if example_parts else ""
            print(f"✅ [ROUTER] Generated {len(example_parts)} examples ({len(result)} total chars)")
            return result
        except Exception as e:
            print(f"❌ [ROUTER] Error formatting precedent examples: {e}")
            return ""
    
    def _get_next_step(self, routing: RoutingResponse, tool_metadata: List[Dict[str, Any]], type_savepoint: List[str]) -> str:
        """Determine next step and convert path to full PathItems only if needed."""
        # Check if LLM needs clarification first
        if routing.clarification_question:
            # Convert full path (including nulls) since LLM has a plan but needs clarification
            self.full_path = self._convert_to_full_path(routing.path, tool_metadata)
            return "waiting_for_feedback"
        
        # Build lookup for tool metadata by name
        tools_by_name = {tool["name"]: tool for tool in tool_metadata}
        
        # Check for empty values that don't match expected defaults
        for i, simple_step in enumerate(routing.path):
            tool_meta = tools_by_name.get(simple_step.name)
            if not tool_meta:
                self.is_partial = True
                self.full_path = self._convert_to_full_path(routing.path, tool_metadata, up_to_index=i)
                return "find_path"
                
            has_invalid_empty = self._has_invalid_empty_values(simple_step.param_values, tool_meta)
            if has_invalid_empty:
                self.is_partial = True
                
                # Convert path up to this point to get param_types for previous step
                self.full_path = self._convert_to_full_path(routing.path, tool_metadata, up_to_index=i)
                
                # Find the previous tool and get its output type
                if i > 0:
                    previous_step = self.full_path[i - 1]
                    # Get the output type from the previous step's param_types
                    if previous_step.output_params:
                        # Typically output_params contains ['return'] for most tools
                        for output_param in previous_step.output_params:
                            if output_param in previous_step.param_types:
                                output_type = previous_step.param_types[output_param]
                                # Map the class to the enum using the new enum structure
                                enum_value = WorkflowTypeEnum.from_class(output_type) if hasattr(WorkflowTypeEnum, 'from_class') else None
                                if enum_value is not None:
                                    type_savepoint.append(enum_value)
                                break
                
                return "find_path"
        
        self.full_path = self._convert_to_full_path(routing.path, tool_metadata)
        return "execute"
    
    def _is_empty_value(self, value) -> bool:
        """Check if a value is considered empty (None, empty string, empty list, etc.)"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
            return True
        return False
    
    def _has_invalid_empty_values(self, param_values: Dict[str, Any], tool_meta: Optional[Dict[str, Any]]) -> bool:
        """
        Check if param_values contains empty values that don't match expected defaults.
        
        Args:
            param_values: The parameter values from the routing response
            tool_meta: Tool metadata containing default_params
            
        Returns:
            True if there are invalid empty values that need user input
        """
        if not param_values or not tool_meta:
            return False
            
        default_params = tool_meta.get("default_params", {})
        
        for key, value in param_values.items():
            if self._is_empty_value(value):
                # Check if this parameter has a default defined
                if key in default_params:
                    expected_default = default_params[key].get("value") if isinstance(default_params[key], dict) else default_params[key]
                    # If the empty value matches the expected default, it's valid
                    if value == expected_default:
                        continue
                    # Special case: if expected default is None and we have None, it's valid
                    if expected_default is None and value is None:
                        continue
                
                # Empty value without matching default - this needs user input
                return True
                
        return False
