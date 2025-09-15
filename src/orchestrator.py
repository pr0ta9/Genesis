import logging
import os
from typing import Any, Dict, List, Optional, Generator
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt, Command
from dotenv import load_dotenv

from .state import State
from .agents import Precedent, Classifier, Router, Finalizer, setup_llm
from .path import ToolRegistry, PathGenerator, PathToolMetadata, PathItem
from .executor.flow_state import StateGenerator
from .executor.conversion import convert_path_to_hybrid_graph
from .executor.execution import ExecutionOrchestrator, ExecutionResult
from .tools.agent_tools import search
from .logging_utils import get_logger, pretty, format_messages, log_section
from .streaming import emit_status, StreamingContext, StatusType


class Orchestrator:
    def __init__(self):
        load_dotenv(override=True)
        # Initialize LLM for agents (simple default; can be customized externally)
        self.llm = setup_llm("ollama", "gpt-oss:20b")
        self.llm.bind_tools([search])
        # Initialize agents
        self.precedent = Precedent(self.llm)
        self.classifier = Classifier(self.llm)
        self.router = Router(self.llm)
        self.finalizer = Finalizer(self.llm)

        # Initialize path finder (registry + generator)
        self.registry = ToolRegistry()
        # Auto-register all decorated tools from tools/path_tools directory (absolute path)
        tools_dir = str((Path(__file__).resolve().parent / "tools" / "path_tools"))
        self.registry.auto_register_from_directory(tools_dir)
        try:
            self.logger.info("Path registry loaded %d tool(s): %s", len(self.registry.tools), list(self.registry.tools.keys()))
        except Exception:
            pass
        self.path_finder = PathGenerator(self.registry)

        # Initialize executor orchestrator
        self._graph_executor = ExecutionOrchestrator()

        # Set up logging
        self.logger = get_logger(__name__)

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
        def precedent_node(state: State) -> list[dict]:
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
                print("🔍 [ORCHESTRATOR] Starting precedent search...")
                try:
                    # Import here to avoid circular imports and ensure a single module instance
                    from app.db.precedent import search_similar_precedents
                    precedents = search_similar_precedents(user_query, threshold=0.5, limit=3)
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
            
            # Emit state update
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="precedent",
                state_update=result
            )
            
            return result
        
        def classify_node(state: State) -> list[dict]:
            self.logger.info("Entering state: classify")
            self.logger.debug("State messages before classify:\n%s", format_messages(state.get("messages", [])))
            
            # Check if we have a streaming context
            # from .streaming import get_stream_writer
            # stream_writer = get_stream_writer()
            
            # if stream_writer and hasattr(self.classifier, 'classify_stream'):
            #     # Use streaming version
            #     for update_type, content in self.classifier.classify_stream(state):
            #         print(f"result in classify_node: {update_type}")
            #         if update_type == "reasoning":
            #             # Emit reasoning through the streaming context
            #             emit_status(
            #                 type=StatusType.REASONING,
            #                 node="classify",
            #                 content=content
            #             )
            #         elif update_type == "result":
            #             # Emit state update before returning
            #             emit_status(
            #                 type=StatusType.STATE_UPDATE,
            #                 node="classify",
            #                 state_update=content
            #             )
            #             return content
            # else:
                # Use regular version
            result = self.classifier.classify(state)
            # Emit state update
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="classify",
                state_update=result
            )
            return result

        def find_path_node(state: State) -> list[dict]:
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
                try:
                    if isinstance(sd.get("input_params"), list):
                        sd["input_params"] = [p for p in sd["input_params"] if p != "output_path"]
                    if isinstance(sd.get("required_inputs"), dict) and "output_path" in sd["required_inputs"]:
                        sd["required_inputs"].pop("output_path", None)
                except Exception:
                    pass
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
            }
            
            # Emit state update via streaming
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="find_path",
                state_update=result
            )
            
            return result

        def route_node(state: State) -> list[dict]:
            self.logger.info("Entering state: route")
            self.logger.debug("Messages before route:\n%s", format_messages(state.get("messages", [])))
            result = self.router.route(state)
            # Emit state update
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="route",
                state_update=result
            )
            return result

        def execute_node(state: State) -> list[dict]:
            self.logger.info("Entering state: execute")
            chosen_path: List[PathItem] = state.get("chosen_path", [])
            log_section(self.logger, "execute chosen path", chosen_path, level=logging.INFO)

            # Bind executable functions to each path step if missing
            try:
                for i, step in enumerate(chosen_path):
                    # PathItem model only
                    if step.function is None:
                        try:
                            step.function = self.registry.get_executable_function(step.name)
                        except Exception as e:
                            self.logger.debug("Could not bind function for step %s: %s", step.name, e)
                    # Replace LLM sentinel for model parameters
                    try:
                        if step.param_values and step.param_values.get("model") == "llm":
                            step.param_values["model"] = self.llm
                            # Mark as non-serializable so isolation treats it correctly
                            if step.param_types is None:
                                step.param_types = {}
                            step.param_types["model"] = "BaseChatModel"
                    except Exception:
                        pass
            except Exception as bind_err:
                self.logger.debug("Function binding encountered an issue: %s", bind_err)

            # Generate execution state schema and initial state
            state_gen = StateGenerator(chosen_path)
            exec_state_schema = state_gen.state_schema
            exec_initial_state = state_gen.ready_state

            # Build workflow and execute
            workflow = convert_path_to_hybrid_graph(chosen_path, exec_state_schema)
            
            result: ExecutionResult = self._graph_executor.execute_workflow(
                workflow=workflow,
                path_object=chosen_path,
                initial_state=exec_initial_state,
            )
            log_section(self.logger, "execute result", result, level=logging.INFO)
            
            # Convert ExecutionResult to serializable dict for LangGraph state
            execution_dict = {"execution_results": result.to_dict(), "next_node": "finalize"}
            
            # Emit state update
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="execute",
                state_update=execution_dict
            )
            
            return execution_dict

        def finalize_node(state: State) -> list[dict]:
            self.logger.info("Entering state: finalize")
            result = self.finalizer.finalize(state)
            # Emit state update
            emit_status(
                type=StatusType.STATE_UPDATE,
                node="finalize",
                state_update=result
            )
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
            
            # If no feedback provided, ask again
            if not feedback or feedback.strip() == "":
                return {"next_node": "waiting_for_feedback"}
            
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
        builder.add_edge("classify", "find_path")
        builder.add_conditional_edges(
            "classify",
            lambda state: state.get("next_node"),
        )
        builder.add_edge("find_path", "route")
        builder.add_conditional_edges(
            "route",
            lambda state: state.get("next_node"),
        )
        builder.add_edge("execute", "finalize")
        builder.add_conditional_edges(
            "finalize",
            lambda state: END if state.get("next_node") == "END" else state.get("next_node"),
        )
        builder.add_conditional_edges(
            "waiting_for_feedback",
            lambda state: END if state.get("next_node") == "END" else state.get("next_node"),
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
    
    def resume_with_feedback(self, feedback: str, thread_id: str = "default") -> Dict[str, Any]:
        """
        Resume execution after providing user feedback.
        
        Args:
            feedback: User's response to the clarification question
            thread_id: Thread ID to resume
            
        Returns:
            Final graph state after resuming execution
        """
        from langgraph.types import Command
        
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            return self.graph.invoke(Command(resume=feedback), config)
        except Exception as e:
            # If we hit another interrupt, return current state with error details
            self.logger.exception("Graph resume error")
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
    
    def run_with_streaming(
        self, 
        messages: List[AnyMessage], 
        thread_id: str = "default",
        reasoning_callback=None
    ) -> Generator[tuple[str, Any], None, None]:
        """
        Execute orchestrator workflow with streaming reasoning support.
        
        This is a wrapper around the regular run() that adds reasoning streaming.
        The graph execution remains unchanged - we just intercept reasoning emissions.
        
        Args:
            messages: List of messages to process
            thread_id: Thread ID for conversation state
            reasoning_callback: Optional callback for reasoning updates
            
        Yields:
            Tuple of (update_type, content) where:
            - ("reasoning", reasoning_text) for real-time reasoning from agents
            - ("result", final_state) for final orchestrator result
        """
        # Import streaming utilities
        from .streaming import StreamingContext
        
        # Collect reasoning events
        reasoning_events = []
        
        def stream_collector(event):
            """Collect streaming events"""
            if event.type.value == "reasoning":
                reasoning_events.append(event.content)
                if reasoning_callback:
                    reasoning_callback(event.content)
        
        # Run the graph with streaming context
        with StreamingContext(stream_collector):
            # Let the graph run normally - nodes that support streaming will emit events
            result = self.run(messages, thread_id)
        
        # Yield all collected reasoning events
        for reasoning in reasoning_events:
            yield ("reasoning", reasoning)
        
        # Yield final result
        yield ("result", result)

