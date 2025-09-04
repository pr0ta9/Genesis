import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt, Command
from dotenv import load_dotenv

from .state import State
from .agents import Classifier, Router, Finalizer, setup_llm
from .path import ToolRegistry, PathGenerator, PathToolMetadata
from .executor.flow_state import StateGenerator
from .executor.conversion import convert_path_to_hybrid_graph
from .executor.execution import ExecutionOrchestrator, ExecutionResult
from .tools.agent_tools import search


class Orchestrator:
    def __init__(self):
        load_dotenv(override=True)
        # Initialize LLM for agents (simple default; can be customized externally)
        llm = setup_llm("ollama", "gpt-oss:20b")
        llm.bind_tools([search])
        # Initialize agents
        self.classifier = Classifier(llm)
        self.router = Router(llm)
        self.finalizer = Finalizer(llm)

        # Initialize path finder (registry + generator)
        self.registry = ToolRegistry()
        # Auto-register all decorated tools from tools/path_tools directory
        self.registry.auto_register_from_directory("src/tools/path_tools")
        self.path_finder = PathGenerator(self.registry)

        # Initialize executor orchestrator
        self._graph_executor = ExecutionOrchestrator()

        # Set up logging
        self.logger = logging.getLogger(__name__)

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

        def classify_node(state: State) -> list[dict]:
            return self.classifier.classify(state)

        def find_path_node(state: State) -> list[dict]:
            input_type = state.get("input_type")
            output_type = state.get("output_type")

            all_paths: List[List[PathToolMetadata]] = self.path_finder.find_all_paths(input_type, output_type)

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

            return {
                "all_paths": path_dicts,
                # Store the actual PathToolMetadata objects without duplicates
                "tool_metadata": list(unique_tools_by_name.values()),
            }

        def route_node(state: State) -> list[dict]:
            return self.router.route(state)

        def execute_node(state: State) -> list[dict]:
            chosen_path: List[Dict[str, Any]] = state.get("chosen_path", [])

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
            return {"execution_results": result}

        def finalize_node(state: State) -> list[dict]:
            return self.finalizer.finalize(state)
        
        def feedback_node(state: State) -> Dict[str, Any]:
            # Get the clarification question based on which node sent us here
            if state.get("node") == "classify":
                question = state.get("classify_clarification")
                return_node = "classify"
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
        builder.add_node("classify", classify_node)
        builder.add_node("find_path", find_path_node)
        builder.add_node("route", route_node)
        builder.add_node("execute", execute_node)
        builder.add_node("finalize", finalize_node)
        builder.add_node("waiting_for_feedback", feedback_node)

        # Linear flow: START -> classify -> find_path -> route -> execute -> finalize -> END
        builder.add_edge(START, "classify")
        builder.add_conditional_edges(
            "classify",
            lambda state: END if state.get("next_node") == "END" else state.get("next_node"),
        )
        builder.add_edge("find_path", "route")
        builder.add_conditional_edges(
            "route",
            lambda state: END if state.get("next_node") == "END" else state.get("next_node"),
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

    def run(self, user_input: str, message_history: List[AnyMessage] = None, thread_id: str = "default") -> Dict[str, Any]:
        """
        Execute the linear orchestrator workflow.

        Args:
            user_input: The latest user input to add to the conversation
            message_history: Existing conversation history (list of messages)
            thread_id: Thread ID for maintaining conversation state

        Returns:
            Final graph state after execution or interrupt info
        """
        # Set up thread configuration
        config = {"configurable": {"thread_id": thread_id}}
        
        # Build messages from provided history and latest user input
        messages: List[AnyMessage] = list(message_history or [])
        if user_input:
            messages.append(HumanMessage(content=user_input))

        # Initialize all non-optional keys with sensible defaults
        initial_state: Dict[str, Any] = {
            # Control flow
            "next_node": "",
            "messages": messages,
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
        
        # Execute graph - it will either complete or hit an interrupt
        try:
            return self.graph.invoke(initial_state, config)
        except Exception as e:
            # If we hit an interrupt, return current state
            current_state = self.graph.get_state(config)
            return {
                "interrupted": True,
                "state": current_state.values,
                "next_node": current_state.next,
                "thread_id": thread_id
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
            # If we hit another interrupt, return current state
            current_state = self.graph.get_state(config)
            return {
                "interrupted": True,
                "state": current_state.values,
                "next_node": current_state.next,
                "thread_id": thread_id
            }


