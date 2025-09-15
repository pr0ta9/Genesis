import os
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent
from ..state import State

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
        
        # Invoke LLM with precedents list
        print("🧠 [PRECEDENT AGENT] Invoking LLM for precedent analysis...")
        result, updated_history = self._invoke(
            messages, 
            node,
            precedents=precedents  # Pass to prompt template
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
            response["input_type"] = precedent_data.get("input_type", "")
            response["type_savepoint"] = precedent_data.get("type_savepoint", [])
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
