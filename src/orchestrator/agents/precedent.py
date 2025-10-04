import os
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..core.state import State
from ..path import WorkflowTypeEnum

class PrecedentResponse(BaseModel):
    """Pydantic model for precedent analysis response."""
    index: int = Field(description="Index of chosen precedent (0-based), or -1 if no match")
    reasoning: str = Field(description="Explanation of precedent selection or rejection")
    clarification_question: Optional[str] = Field(
        default=None, 
        description="Question to ask user if precedent analysis is unclear"
    )

    
class Precedent(BaseAgent[PrecedentResponse]):
    """
    Precedent analysis agent that examines workflow precedents and selects the best match.
    Uses LangChain's structured output to return a PrecedentResponse with index selection,
    reasoning, and optional clarification questions.
    """
    
    def __init__(self, llm: BaseChatModel, prompt_path: str = os.path.join(os.path.dirname(__file__), 'prompts', 'Precedent.yaml')):
        """
        Initialize the Precedent agent.
        
        Args:
            llm: The language model instance to use
            prompt_path: Path to the YAML prompt configuration file
        """
        super().__init__(llm, PrecedentResponse, prompt_path)
    
    def analyze_precedents(self, state: State, precedents: List[Dict]) -> Dict[str, Any]:
        """
        Analyze precedents and select best match (or -1 for no match).
        
        Args:
            state: Current workflow state
            precedents: List of precedent dictionaries from search_similar_precedents()
            
        Returns:
            Dictionary with precedent analysis results
        """
        print(f"🤖 [PRECEDENT AGENT] Starting analysis of {len(precedents)} precedents...")
        node = "precedent"
        messages: List[BaseMessage] = state.get("messages", [])
        
        if precedents:
            for i, p in enumerate(precedents):
                print(f"📋 [PRECEDENT AGENT] Precedent {i}: ID={p.get('id', 'unknown')}, score={p.get('score', 0):.3f}")
                print(f"   📝 [PRECEDENT AGENT] Objective: '{p.get('objective', '')[:80]}...'")
        else:
            print("⚠️  [PRECEDENT AGENT] No precedents to analyze")
        
        # Preprocess precedents into compact string for prompt
        print("🧠 [PRECEDENT AGENT] Preparing precedents for prompt...")
        formatted_precedents = self._format_precedents_for_prompt(precedents)
        # Invoke LLM with formatted precedents list
        print("🧠 [PRECEDENT AGENT] Invoking LLM for precedent analysis...")
        result, updated_history = self._invoke(
            messages,
            node,
            precedents=formatted_precedents  # Compact string for the template
        )
        print(f"🧠 [PRECEDENT AGENT] LLM returned: {type(result).__name__}")
        
        # Coerce unstructured results into PrecedentResponse
        if isinstance(result, str):
            # Default to no match if we get raw string
            result = PrecedentResponse(
                index=-1,
                reasoning=result or "Unable to analyze precedents",
                clarification_question=None,
            )
        elif isinstance(result, dict):
            try:
                result = PrecedentResponse.model_validate(result)
            except Exception:
                # Fallback to no match
                result = PrecedentResponse(
                    index=int(result.get("index", -1)),
                    reasoning=str(result.get("reasoning", "Unable to parse precedent analysis")),
                    clarification_question=result.get("clarification_question"),
                )
        
        next_node = self._get_next_step(result, len(precedents))
        
        # High-level summary log
        self.logger.info(
            "Precedent agent decided next_node=%s index=%s precedents_count=%d",
            next_node,
            result.index,
            len(precedents),
        )
        
        response = {
            "node": node,
            "next_node": next_node,
            "precedent_reasoning": result.reasoning,
            "precedent_clarification": result.clarification_question,
            "messages": updated_history
        }
        
        # Only add precedent data if we have a valid match
        if result.index >= 0 and result.index < len(precedents):
            precedent_data = precedents[result.index]
            print(f"✅ [PRECEDENT AGENT] Selected precedent {result.index}: {precedent_data.get('id', 'unknown')}")
            
            # Extract ALL data router needs (bypassing both classify AND find_path)
            print("📊 [PRECEDENT AGENT] Extracting classification and path data from precedent...")
            
            # Classification data (normally from classify node)
            response["objective"] = precedent_data.get("objective", "")
            # Coerce input_type and type_savepoint into WorkflowTypeEnum
            response["input_type"] = self._coerce_workflow_type(precedent_data.get("input_type"))
            response["type_savepoint"] = self._coerce_type_savepoints(precedent_data.get("type_savepoint", []))
            response["is_complex"] = precedent_data.get("is_complex", False)
            
            # Path data (normally from find_path node)
            precedent_path = precedent_data.get("path", [])
            response["all_paths"] = [precedent_path] if precedent_path else []  # Wrap single path in list
            response["tool_metadata"] = precedent_path if precedent_path else []  # Path contains tool metadata
            
            print(f"🎯 [PRECEDENT AGENT] Precedent data extracted:")
            print(f"   📝 Objective: '{response['objective'][:100]}...'")
            print(f"   📊 Input type: {response['input_type']}, Complex: {response['is_complex']}")
            print(f"   🛠️  Workflow: {len(response['tool_metadata'])} steps")
            
            self.logger.info("Selected precedent %d: %s", result.index, precedent_data.get("description", "")[:100])
            self.logger.info("Provided complete data - objective: %s, input_type: %s, paths: %d", 
                           response["objective"], response["input_type"], len(response["all_paths"]))
        else:
            if len(precedents) == 0:
                print("ℹ️  [PRECEDENT AGENT] No precedents found in database")
                self.logger.info("No precedents found in database")
            else:
                print(f"❌ [PRECEDENT AGENT] No precedent match selected (index={result.index}, available={len(precedents)})")
                self.logger.info("No precedent match selected (index=%d, available=%d)", result.index, len(precedents))
            
        return response

    def _coerce_workflow_type(self, value: Any) -> WorkflowTypeEnum:
        """Convert various representations into WorkflowTypeEnum with safe fallbacks."""
        if isinstance(value, WorkflowTypeEnum):
            return value
        
        if isinstance(value, str):
            # Handle string representation like "<WorkflowTypeEnum.AUDIOFILE: 'audiofile'>"
            import re
            match = re.search(r'WorkflowTypeEnum\.(\w+)', value)
            if match:
                enum_name = match.group(1)  # e.g., "AUDIOFILE"
                try:
                    result = WorkflowTypeEnum[enum_name]  # Access by name
                    print(f"🔄 [PRECEDENT AGENT] Parsed '{value}' → {result}")
                    return result
                except (KeyError, AttributeError):
                    pass
            
            # Try to parse from string label (e.g., "audiofile" or "AUDIOFILE")
            try:
                # Try uppercase name first (e.g., "AUDIOFILE")
                result = WorkflowTypeEnum[value.upper()]
                print(f"🔄 [PRECEDENT AGENT] Parsed '{value}' (uppercase) → {result}")
                return result
            except (KeyError, AttributeError):
                pass
            
            try:
                # Try as value (e.g., "audiofile")
                result = WorkflowTypeEnum(value.lower())
                print(f"🔄 [PRECEDENT AGENT] Parsed '{value}' (lowercase) → {result}")
                return result
            except (ValueError, AttributeError):
                pass
        
        # Fallback to TEXT as a safe default
        print(f"⚠️  [PRECEDENT AGENT] Failed to parse '{value}', falling back to TEXT")
        return WorkflowTypeEnum.TEXT

    def _coerce_type_savepoints(self, values: Any) -> List[WorkflowTypeEnum]:
        """Convert a list of string/enum values into List[WorkflowTypeEnum]."""
        result: List[WorkflowTypeEnum] = []
        if not isinstance(values, list):
            values = [values] if values is not None else []
        for v in values:
            coerced_type = self._coerce_workflow_type(v)
            result.append(coerced_type)
        # Ensure at least one savepoint if input exists; otherwise leave empty
        return result

    def _format_precedents_for_prompt(self, precedents: List[Dict]) -> str:
        """Build a compact, readable string with only the needed fields for the prompt.

        Includes: objective, path (tool names), input_type, type_savepoint, messages.
        """
        if not precedents:
            return ""
        parts: List[str] = []
        for i, p in enumerate(precedents):
            objective = str(p.get("objective", "")).strip()
            # Path: show tool names in order
            raw_path = p.get("path") or []
            try:
                tool_names = [step.get("name", "?") for step in raw_path if isinstance(step, dict)]
            except Exception:
                tool_names = []
            path_str = " -> ".join(tool_names) if tool_names else "(no path)"
            input_type = str(p.get("input_type", "")).lower()
            type_savepoint = p.get("type_savepoint", []) or []
            try:
                tsp_str = " -> ".join([str(t).lower() for t in type_savepoint]) if type_savepoint else ""
            except Exception:
                tsp_str = ""
            messages = str(p.get("messages", ""))
            # Keep messages concise
            max_len = 400
            if len(messages) > max_len:
                messages = messages[:max_len] + "..."
            parts.append(
                f"Precedent {i}:\n"
                f"- objective: {objective}\n"
                f"- path: {path_str}\n"
                f"- input_type: {input_type}\n"
                f"- type_savepoint: {tsp_str}\n"
                f"- messages: {messages}"
            )
        return "\n\n".join(parts)
    
    def _get_next_step(self, result: PrecedentResponse, precedents_count: int) -> str:
        """Determine next step based on precedent analysis result."""
        if result.clarification_question:
            return "waiting_for_feedback"
        elif result.index == -1:
            return "classify"  # No precedent match, proceed to classification
        elif 0 <= result.index < precedents_count:
            return "route"    # Use precedent, skip to routing
        else:
            # Invalid index, fallback to classification
            return "classify"
