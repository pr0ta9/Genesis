"""
Orchestrator service - wrapper around the core Genesis orchestrator.
Provides thread-safe access and state management.
"""
import os
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
from datetime import datetime

# Ensure Genesis src is in path
genesis_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(genesis_root))

from src.orchestrator import Orchestrator
from langchain_core.messages import HumanMessage, AIMessage
from src.streaming import get_stream_writer, set_stream_writer


class OrchestratorService:
    """Singleton service wrapping the Genesis orchestrator."""
    
    _instance: Optional['OrchestratorService'] = None
    _orchestrator: Optional[Orchestrator] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._orchestrator is None:
            # Initialize orchestrator only once
            print("Initializing Genesis Orchestrator...")
            self._orchestrator = Orchestrator()
            print("Orchestrator initialized successfully")
    
    @property
    def orchestrator(self) -> Orchestrator:
        """Get the orchestrator instance."""
        return self._orchestrator
    
    async def process_message(self, conversation_id: str, user_input: str, 
                            message_history: List[Dict] = None) -> Dict[str, Any]:
        """
        Process a user message through the orchestrator.
        
        Args:
            conversation_id: Thread ID for the conversation
            user_input: User's message
            message_history: Previous messages in the conversation
            
        Returns:
            Orchestrator result including state and response
        """
        # Convert message history to LangChain messages
        lc_history = []
        if message_history:
            for msg in message_history:
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_history.append(AIMessage(content=msg["content"]))
        
        # Build messages
        messages = self.orchestrator.build_messages(
            user_input=user_input,
            message_history=lc_history
        )
        
        # Run orchestrator in thread pool to avoid blocking and propagate streaming writer
        loop = asyncio.get_event_loop()
        current_writer = get_stream_writer()

        def _run_with_writer():
            if current_writer is not None:
                set_stream_writer(current_writer)
            return self.orchestrator.run(messages, conversation_id)

        result = await loop.run_in_executor(None, _run_with_writer)
        
        return result
    
    async def process_clarification(self, conversation_id: str, feedback: str) -> Dict[str, Any]:
        """
        Process a clarification response.
        
        Args:
            conversation_id: Thread ID for the conversation
            feedback: User's clarification response
            
        Returns:
            Orchestrator result after resuming with feedback
        """
        # Run in thread pool
        loop = asyncio.get_event_loop()
        current_writer = get_stream_writer()

        def _resume_with_writer():
            if current_writer is not None:
                set_stream_writer(current_writer)
            return self.orchestrator.resume_with_feedback(feedback, conversation_id)

        result = await loop.run_in_executor(None, _resume_with_writer)
        
        return result
    
    def extract_state_data(self, orchestrator_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract state data from orchestrator result for database storage.
        
        Args:
            orchestrator_result: Raw result from orchestrator.run()
            
        Returns:
            Dictionary of state fields to store
        """
        state_data = {}
        
        # Get the state dict (might be under 'state' key or at top level)
        state = orchestrator_result.get("state", orchestrator_result)
        
        # Debug logging
        print(f"\n[OrchestratorService Debug] extract_state_data called:")
        print(f"  - Input keys: {list(orchestrator_result.keys())}")
        print(f"  - State type: {type(state)}")
        print(f"  - State keys: {list(state.keys()) if isinstance(state, dict) else 'Not a dict'}")
        
        # Extract all state fields
        state_fields = [
            # Control flow
            "node", "next_node",
            # Classify
            "objective", "input_type", "output_type", "type_savepoint", "is_complex",
            "classify_reasoning", "classify_clarification",
            # Path
            "tool_metadata", "all_paths",
            # Router
            "chosen_path", "route_reasoning", "route_clarification", "is_partial",
            # Execute
            "execution_results",
            # Finalizer
            "is_complete", "response", "finalize_reasoning", "summary",
            # Errors
            "error_details"
        ]
        
        def serialize_tool_item(item):
            """Helper to serialize a single tool/path item - excludes function field entirely"""
            if item is None:
                return None
            
            # Handle PathToolMetadata with to_dict method
            if hasattr(item, 'to_dict'):
                result = item.to_dict()
                # Always exclude function field completely
                result.pop('function', None)
                return result
            
            # Handle PathItem or other Pydantic models
            if hasattr(item, 'model_dump'):
                serialized = item.model_dump(exclude={'function'})
                # Convert any enum types in param_types
                if 'param_types' in serialized:
                    serialized['param_types'] = {
                        k: v if isinstance(v, str) else str(v)
                        for k, v in serialized['param_types'].items()
                    }
                # Double-check function is excluded
                serialized.pop('function', None)
                return serialized
            
            # Handle Pydantic V1 models
            if hasattr(item, 'dict'):
                serialized = item.dict(exclude={'function'})
                if 'param_types' in serialized:
                    serialized['param_types'] = {
                        k: v if isinstance(v, str) else str(v)
                        for k, v in serialized['param_types'].items()
                    }
                # Double-check function is excluded
                serialized.pop('function', None)
                return serialized
            
            # Handle regular dicts
            if isinstance(item, dict):
                # Create a clean copy without function field
                serialized = {}
                for k, v in item.items():
                    if k != 'function':  # Always skip function field
                        serialized[k] = v
                
                # Convert param_types to strings
                if 'param_types' in serialized:
                    serialized['param_types'] = {
                        k: (v if isinstance(v, str) else str(v))
                        for k, v in serialized['param_types'].items()
                    }
                
                # Convert required_inputs to strings if present
                if 'required_inputs' in serialized and isinstance(serialized['required_inputs'], dict):
                    serialized['required_inputs'] = {
                        k: (v if isinstance(v, str) else str(v))
                        for k, v in serialized['required_inputs'].items()
                    }
                
                return serialized
            
            # Handle objects with __dict__
            if hasattr(item, '__dict__'):
                item_dict = {}
                for k, v in item.__dict__.items():
                    if k != 'function':  # Always skip function field
                        item_dict[k] = v
                return item_dict
            
            # Fallback to string representation
            return str(item)
        
        for field in state_fields:
            if field not in state:
                continue
                
            value = state[field]
            
            # Skip None values
            if value is None:
                state_data[field] = None
                continue
            
            # Convert enums to strings
            if field in ["input_type", "output_type"] and value is not None:
                if hasattr(value, 'value'):
                    value = value.value
                elif isinstance(value, list):
                    value = [v.value if hasattr(v, 'value') else v for v in value]
            
            # Special handling for type_savepoint (list of enums)
            elif field == "type_savepoint" and value is not None:
                if isinstance(value, list):
                    value = [v.value if hasattr(v, 'value') else v for v in value]
                elif hasattr(value, 'value'):
                    value = value.value
            
            # Handle tool_metadata - flat list of tool metadata
            elif field == "tool_metadata":
                if isinstance(value, list):
                    value = [serialize_tool_item(tool) for tool in value]
            
            # Handle all_paths - list of paths, where each path is a list of tools
            elif field == "all_paths":
                if isinstance(value, list):
                    serialized_paths = []
                    for path in value:
                        if isinstance(path, list):
                            # Each path is a list of tool items
                            serialized_path = [serialize_tool_item(tool) for tool in path]
                            serialized_paths.append(serialized_path)
                        elif isinstance(path, dict):
                            # Sometimes might be a dict representation
                            serialized_paths.append(serialize_tool_item(path))
                        else:
                            # Unexpected structure
                            serialized_paths.append(str(path))
                    value = serialized_paths
            
            # Handle chosen_path - single path (list of PathItem objects)
            elif field == "chosen_path":
                if isinstance(value, list):
                    value = [serialize_tool_item(item) for item in value]
            
            # Handle execution_results
            elif field == "execution_results":
                if isinstance(value, dict):
                    # Make a copy and ensure it's serializable
                    value = dict(value)
                    # Convert any non-serializable items to strings
                    for k, v in value.items():
                        if not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                            value[k] = str(v)
            
            # Store the processed value
            state_data[field] = value
        
        # Debug what we extracted for key fields
        if any(f in ["all_paths", "chosen_path", "tool_metadata"] for f in state_data):
            print(f"\n[OrchestratorService Debug] Extracted path data:")
            for key in ["all_paths", "chosen_path", "tool_metadata"]:
                if key in state_data:
                    val = state_data[key]
                    print(f"  - {key}: type={type(val)}, has_value={val is not None}")
                    if val is not None and isinstance(val, list) and len(val) > 0:
                        print(f"    First item type: {type(val[0])}")
                        if key == "all_paths" and isinstance(val[0], list) and len(val[0]) > 0:
                            print(f"    First path first tool type: {type(val[0][0])}")
        
        # Extract execution instance if present
        exec_results = state.get("execution_results")
        if exec_results and isinstance(exec_results, dict):
            # Look for workspace directory in execution results
            workspace_dir = exec_results.get("workspace_dir")
            if workspace_dir:
                # Extract instance name from path
                state_data["execution_instance"] = Path(workspace_dir).name
        
        return state_data

    def get_response_from_result(self, result: Dict[str, Any]) -> str:
        """Extract the appropriate response from orchestrator result."""
        state = result.get("state", result)
        
        # Check for clarification questions first
        if state.get("classify_clarification"):
            return f"❓ {state['classify_clarification']}"
        elif state.get("route_clarification"):
            return f"❓ {state['route_clarification']}"
        
        # Normal response
        elif result.get("response"):
            return result["response"]
        elif state.get("response"):
            return state["response"]
        
        # Error case
        elif result.get("interrupted"):
            error_msg = result.get("error") or state.get("error_details")
            return f"❌ An error occurred: {error_msg}" if error_msg else "⚠️ Processing was interrupted."
        
        # Fallback
        return "🤔 No response generated."
    
    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        # This could be made configurable
        return [
            "Gemini",
            "ollama:gpt-oss:20b"
        ]


# Global instance getter
def get_orchestrator() -> OrchestratorService:
    """Get the singleton orchestrator service instance."""
    return OrchestratorService()
