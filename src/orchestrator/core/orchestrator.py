import logging
import os
from typing import Any, Dict, List, Iterator
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt, Command
from dotenv import load_dotenv

from .state import State
from ..agents import Precedent, Classifier, Router, Finalizer, setup_llm
from ..path import ToolRegistry, PathGenerator, PathToolMetadata, PathItem
from ..tools.agent_tools import search
from .logging_utils import get_logger, pretty, format_messages, log_section


class Orchestrator:
    def __init__(self, llm_type: str = "ollama", model_name: str = "gpt-oss:20b", temperature: float = 0.6, weaviate_client=None):
        """
        Initialize the orchestrator with configurable LLM settings.
        
        Args:
            llm_type: Type of LLM to use (e.g., "ollama", "openai")
            model_name: Name of the model to use (e.g., "gpt-oss:20b", "gpt-4")
            weaviate_client: Shared Weaviate client instance (optional)
        """
        load_dotenv(override=True)
        # Store shared Weaviate client
        self.weaviate_client = weaviate_client
        
        # Initialize LLM for agents with configurable type and model
        self.llm = setup_llm(llm_type, model_name, temperature)
        self.llm.bind_tools([search])
        # Initialize agents
        self.precedent = Precedent(self.llm)
        self.classifier = Classifier(self.llm)
        self.router = Router(self.llm)
        self.finalizer = Finalizer(self.llm)

        # Initialize path finder (registry + generator)
        self.registry = ToolRegistry()
        # Auto-register all decorated tools from src/orchestrator/tools/path_tools directory (absolute path)
        tools_dir = str((Path(__file__).resolve().parents[1] / "tools" / "path_tools"))
        self.registry.auto_register_from_directory(tools_dir)
        self.path_finder = PathGenerator(self.registry)

        # Set up logging
        self.logger = get_logger(__name__)
        self.logger.info("Path registry loaded %d tool(s): %s", len(self.registry.tools), list(self.registry.tools.keys()))

        # Load configuration
        self.config: Dict[str, Any] = {
            "max_retries": 3,
            "timeout": 300,
        }

        # Build LangGraph
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(State)

        # -----------------
        # Node definitions
        # -----------------
        def precedent_node(state: State) -> Dict[str, Any]:
            self.logger.info("🔍 [ORCHESTRATOR] Entering precedent_node state")
            
            # Extract user query from messages
            print("📝 [ORCHESTRATOR] Extracting user query from messages...")
            user_query = ""
            messages = state.get("messages", [])
            for msg in messages:
                if hasattr(msg, 'content') and hasattr(msg, '__class__'):
                    if msg.__class__.__name__ == 'HumanMessage':
                        if user_query:
                            user_query += " " + msg.content
                        else:
                            user_query = msg.content
            print(f"📝 [ORCHESTRATOR] Extracted query: '{user_query[:150]}...'") if user_query else print("⚠️  [ORCHESTRATOR] No user query found in messages")
            
            # Search for precedents (single search for both precedent and router use)
            precedents = []
            if user_query:
                if not self.weaviate_client:
                    print("⚠️  [ORCHESTRATOR] Weaviate client not available - skipping precedent search")
                else:
                    print("🔍 [ORCHESTRATOR] Starting precedent search...")
                    try:
                        # Use semantics module for Weaviate search with shared client
                        from src.db import semantics
                        
                        results = semantics.search(self.weaviate_client, user_query, limit=3, collection_name="precedent")
                        print(f"🔍 [ORCHESTRATOR] Results: {results}")
                        # Convert Weaviate results to expected format
                        precedents = []
                        for i, result in enumerate(results):
                            props = result.properties
                            
                            # Extract score from metadata (Weaviate hybrid search)
                            score = 0.0
                            if hasattr(result, 'metadata') and result.metadata:
                                # Try different score attributes
                                score = getattr(result.metadata, 'score', None)
                                if score is None:
                                    score = getattr(result.metadata, 'certainty', None)
                                if score is None:
                                    score = getattr(result.metadata, 'distance', None)
                            
                            # Ensure score is a valid float
                            if score is None:
                                score = 0.0
                            else:
                                score = float(score)
                            precedent_dict = {
                                "id": str(result.uuid),
                                "description": props.get('description', ''),
                                "path": props.get('path', []),
                                "router_format": props.get('router_format', []),
                                "messages": props.get('messages', ''),
                                "objective": props.get('objective', ''),
                                "is_complex": props.get('is_complex', False),
                                "input_type": props.get('input_type', ''),
                                "type_savepoint": props.get('type_savepoint', []),
                                "created_at": props.get('created_at'),
                                "score": score
                            }
                            
                            # Deserialize JSON strings back to dicts (param_types, required_inputs, default_params, param_values)
                            precedent_dict['path'] = semantics._deserialize_nested_dicts(precedent_dict['path'])
                            precedent_dict['router_format'] = semantics._deserialize_nested_dicts(precedent_dict['router_format'])
                            
                            print(f"🔍 [ORCHESTRATOR] Precedent dict: {precedent_dict}")
                            precedents.append(precedent_dict)
                            print(f"✅ [ORCHESTRATOR] Precedent {i+1}: ID={str(result.uuid)[:8]}..., score={score:.4f}")
                        
                        print(f"✅ [ORCHESTRATOR] Found {len(precedents)} precedents for query")
                        self.logger.info("Found %d precedents for query: %s", len(precedents), user_query[:100])
                    except Exception as e:
                        print(f"❌ [ORCHESTRATOR] Failed to search precedents: {e}")
                        self.logger.warning("Failed to search precedents: %s", e)
                        precedents = []
            else:
                print("⚠️  [ORCHESTRATOR] No user query found - skipping precedent search")
            
            # Only analyze precedents if we found any
            if precedents:
                print("🤖 [ORCHESTRATOR] Calling precedent agent to analyze results...")
                result = self.precedent.analyze_precedents(state, precedents)
                print(f"🎯 [ORCHESTRATOR] Precedent agent decision: next_node='{result.get('next_node', 'unknown')}'")
            else:
                print("⚠️ [ORCHESTRATOR] No precedents found - skipping analysis and routing to classify")
                result = {
                    "node": "precedent",
                    "next_node": "classify",
                    "precedent_reasoning": "No precedents found to analyze",
                    "precedent_clarification": None,
                    "messages": state.get("messages", [])
                }

            # Add precedent search data to state
            result["precedents_found"] = precedents
            print(f"💾 [ORCHESTRATOR] Added {len(precedents)} precedents to state")
            
            return result
        
        def classify_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: classify")
            self.logger.debug("State messages before classify:\n%s", format_messages(state.get("messages", [])))
            result = self.classifier.classify(state)
            return result

        def find_path_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: find_path")
            input_enum = state.get("input_type")
            # Prefer the latest savepoint for the target type if present
            type_savepoint = state.get("type_savepoint") or []
            output_enum = type_savepoint[-1]
            self.logger.debug("Input type=%s, Output type=%s", input_enum, output_enum)
            all_paths: List[List[PathToolMetadata]] = self.path_finder.find_all_paths(input_enum.cls, output_enum.cls)
            # Convert to serializable dicts (tool metadata)
            path_dicts: List[List[Dict[str, Any]]] = [
                [tool.to_dict() for tool in path] for path in all_paths
            ]

            # Build de-duplicated list of PathToolMetadata across all paths (preserve order)
            unique_tools_by_name: Dict[str, PathToolMetadata] = {}
            for path in all_paths:
                for tool in path:
                    if tool.name not in unique_tools_by_name:
                        unique_tools_by_name[tool.name] = tool
            self.logger.info("find_path discovered %d path(s) using %d unique tool(s)", len(path_dicts), len(unique_tools_by_name))
            log_section(self.logger, "find_path all candidate paths", path_dicts, level=logging.DEBUG)
            log_section(self.logger, "find_path unique tools", [tool.to_dict() for tool in unique_tools_by_name.values()], level=logging.DEBUG)

            # Sanitize tool metadata for router prompt: hide output_path param from LLM
            def _sanitize_tool_dict(d: Dict[str, Any]) -> Dict[str, Any]:
                sd = dict(d)
                if isinstance(sd.get("input_params"), list):
                    sd["input_params"] = [p for p in sd["input_params"] if p != "output_path"]
                if isinstance(sd.get("required_inputs"), dict) and "output_path" in sd["required_inputs"]:
                    sd["required_inputs"].pop("output_path", None)
                return sd

            # Sanitize all_paths tool items as well
            sanitized_paths: List[List[Dict[str, Any]]] = []
            for path in path_dicts:
                sanitized_paths.append([_sanitize_tool_dict(t) for t in path])

            result = {
                "all_paths": sanitized_paths,
                # Store serializable tool metadata dicts (sanitized)
                "tool_metadata": [_sanitize_tool_dict(tool.to_dict()) for tool in unique_tools_by_name.values()],
                "next_node": "route",
                "node": "find_path",
            }
            
            return result

        def route_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: route")
            self.logger.debug("Messages before route:\n%s", format_messages(state.get("messages", [])))
            result = self.router.route(state)
            print(f"[ORCHESTRATOR DEBUG] route_node result next_node: {result.get('next_node')}")
            print(f"[ORCHESTRATOR DEBUG] route_node result chosen_path length: {len(result.get('chosen_path', []))}")            
            return result

        def execute_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: execute")
            chosen_path: List[PathItem] = state.get("chosen_path", [])
            log_section(self.logger, "execute chosen path", chosen_path, level=logging.INFO)

            # Import dependencies
            from langgraph.config import get_stream_writer, get_config
            from pathlib import Path
            from ..executor.executor import execute_path
            
            # Get stream writer and config
            writer = get_stream_writer()
            config = get_config()
            chat_id = config.get("configurable", {}).get("thread_id", "unknown") if config else "unknown"
            message_id = config.get("configurable", {}).get("message_id", "unknown") if config else "unknown"

            # Bind executable functions to each path step if missing
            for step in chosen_path:
                if step.function is None:
                    step.function = self.registry.get_executable_function(step.name)
                # Replace LLM sentinel for model parameters
                if step.param_values and step.param_values.get("model") == "llm":
                    step.param_values["model"] = self.llm
                    if step.param_types is None:
                        step.param_types = {}
                    step.param_types["model"] = "BaseChatModel"

            # Execute the path using the executor
            execution_results = execute_path(
                chosen_path=chosen_path,
                chat_id=chat_id,
                message_id=message_id,
                writer=writer
            )
            
            # Build result dictionary
            execution_dict = {
                "execution_results": execution_results,
                "node": "execute",
                "next_node": "finalize"
            }
            
            # Extract execution_output_path from final_output
            final_output = execution_results.get("final_output")
            if final_output:
                output_dir = str(Path(final_output).parent)
                execution_dict["execution_output_path"] = output_dir
            
            return execution_dict

        def finalize_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: finalize")
            result = self.finalizer.finalize(state)
            return result
        
        def feedback_node(state: State) -> Dict[str, Any]:
            self.logger.info("Entering state: waiting_for_feedback")
            # Get the clarification question based on which node sent us here
            if state.get("node") == "classify":
                question = state.get("classify_clarification")
                return_node = "classify"
            elif state.get("node") == "precedent":
                question = state.get("precedent_clarification")
                return_node = "precedent"
            else:
                question = state.get("route_clarification") 
                return_node = "route"
            
            # Use interrupt to wait for user input
            feedback = interrupt(question or "Please provide additional information:")
            print(f"feedback: {feedback}")
            # Feedback validation is now handled at API level before streaming begins
            
            # Use add_messages reducer pattern - just return the new message
            return {
                "messages": [HumanMessage(content=feedback)],
                "next_node": return_node
            }

        # Add nodes
        builder.add_node("precedent", precedent_node)
        builder.add_node("classify", classify_node)
        builder.add_node("find_path", find_path_node)
        builder.add_node("route", route_node)
        builder.add_node("execute", execute_node)
        builder.add_node("finalize", finalize_node)
        builder.add_node("waiting_for_feedback", feedback_node)

        # Linear flow: START -> classify -> find_path -> route -> execute -> finalize -> END
        builder.add_edge(START, "precedent")
        builder.add_conditional_edges(
            "precedent",
            lambda state: state.get("next_node"),
        )
        builder.add_conditional_edges(
            "classify",
            lambda state: state.get("next_node"),
        )
        builder.add_edge("find_path", "route")
        
        def route_decision(state: State) -> str:
            next_node = state.get("next_node")
            print(f"[GRAPH DEBUG] route conditional edge: next_node = {next_node}")
            return next_node
        
        builder.add_conditional_edges(
            "route",
            route_decision,
        )
        builder.add_edge("execute", "finalize")
        builder.add_conditional_edges(
            "finalize",
            lambda state: END if state.get("next_node") == "END" else state.get("next_node"),
        )
        builder.add_conditional_edges(
            "waiting_for_feedback",
            lambda state: state.get("next_node"),
        )
        # Set up memory for interrupt/resume functionality
        from langgraph.checkpoint.memory import InMemorySaver
        memory = InMemorySaver()
        
        return builder.compile(checkpointer=memory)

    @classmethod
    def build_messages(cls, user_input: str = None, message_history: List[AnyMessage] = None) -> List[AnyMessage]:
        """
        Helper method to build messages list from user input and history.
        
        Args:
            user_input: Simple text input to add as HumanMessage
            message_history: Existing conversation history
            
        Returns:
            Combined list of messages
        """
        messages: List[AnyMessage] = list(message_history or [])
        if user_input:
            messages.append(HumanMessage(content=user_input))
        return messages

    def run(self, messages: List[AnyMessage], thread_id: str = "default") -> Dict[str, Any]:
        """
        Execute the linear orchestrator workflow.

        Args:
            messages: List of messages to process (conversation context)
            thread_id: Thread ID for maintaining conversation state

        Returns:
            Final graph state after execution or interrupt info
        """
        # Set up thread configuration
        config = {"configurable": {"thread_id": thread_id}}
        
        # Use provided messages directly
        final_messages: List[AnyMessage] = list(messages)

        # Initialize all non-optional keys with sensible defaults
        initial_state: Dict[str, Any] = {
            # Control flow
            "next_node": "",
            "messages": final_messages,
            # Classify node results
            "objective": "",
            "input_type": "",
            "output_type": "",
            "is_complex": False,
            "classify_reasoning": "",
            "classify_clarification": None,
            # Router node results
            "route_reasoning": "",
            "route_clarification": None,
            # Path/execution data
            "all_paths": [],
            "chosen_path": [],
            "tool_metadata": [],
            "is_partial": False,
            # Finalizer node results
            "is_complete": False,
            "response": "",
            "finalize_reasoning": "",
            "summary": None,
            # Optional execution tracking
            "execution_results": None,
            "error_details": None,
        }
        # Logging run invocation
        self.logger.info("Starting orchestrator run thread_id=%s", thread_id)
        self.logger.debug("Initial messages:\n%s", format_messages(final_messages))

        # Execute graph - it will either complete or hit an interrupt
        try:
            return self.graph.invoke(initial_state, config)
        except Exception as e:
            # If we hit an interrupt or other error, log and return current state with error details
            self.logger.exception("Graph invocation error")
            current_state = self.graph.get_state(config)
            
            # Include error details in the state
            state_values = current_state.values if current_state else {}
            if "error_details" not in state_values:
                state_values = dict(state_values) if state_values else {}
                state_values["error_details"] = f"{type(e).__name__}: {str(e)}"
            
            return {
                "interrupted": True,
                "state": state_values,
                "next_node": current_state.next if current_state else None,
                "thread_id": thread_id,
                "error": f"{type(e).__name__}: {str(e)}"  # Also include at top level
            }
    
    def resume_with_feedback(self, feedback: str, config: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """
        Resume execution after providing user feedback.
        
        Args:
            feedback: User's response to the clarification question
            config: RunnableConfig dict with configurable fields (thread_id, message_id, etc.)
            
        Returns:
            Iterator yielding graph state updates
        """        
        # Config is already built with thread_id and message_id
        return self.graph.stream(Command(resume=feedback), config, stream_mode=["updates", "messages", "custom"])

    def run_stream(self, messages: List[AnyMessage], config: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """
        Execute the linear orchestrator workflow with streaming.

        Args:
            messages: List of messages to process (conversation context)
            config: RunnableConfig dict with configurable fields (thread_id, message_id, etc.)

        Returns:
            Iterator yielding graph state updates during execution
        """
        # Extract thread_id for logging
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        
        # Use provided messages directly
        final_messages: List[AnyMessage] = list(messages)

        # Initialize all non-optional keys with sensible defaults
        initial_state: Dict[str, Any] = {
            # Control flow
            "next_node": "",
            "messages": final_messages,
            # Classify node results
            "objective": "",
            "input_type": "",
            "output_type": "",
            "is_complex": False,
            "classify_reasoning": "",
            "classify_clarification": None,
            # Router node results
            "route_reasoning": "",
            "route_clarification": None,
            # Path/execution data
            "all_paths": [],
            "chosen_path": [],
            "tool_metadata": [],
            "is_partial": False,
            # Finalizer node results
            "is_complete": False,
            "response": "",
            "finalize_reasoning": "",
            "summary": None,
            # Optional execution tracking
            "execution_results": None,
            "error_details": None,
        }
        # Logging run invocation
        self.logger.info("Starting orchestrator run thread_id=%s", thread_id)
        self.logger.debug("Initial messages:\n%s", format_messages(final_messages))

        # Execute graph - config is passed through to all nodes (thread-safe)
        return self.graph.stream(initial_state, config, stream_mode=["updates", "messages", "custom"])