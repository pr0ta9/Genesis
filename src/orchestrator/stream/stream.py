"""
Streaming interface for the orchestrator.
Provides a unified streaming API that handles both new conversations and resuming interrupted ones.
"""

from typing import List, Iterator, Dict, Any
import traceback
from langchain_core.messages import AnyMessage

from ..core.orchestrator import Orchestrator


def stream(
    orchestrator: Orchestrator,
    messages: List[AnyMessage], 
    config: Dict[str, Any],
    interrupted: bool = False,
) -> Iterator[Dict[str, Any]]:
    """
    Stream orchestrator execution with support for interrupts and resuming.
    
    Args:
        orchestrator: Orchestrator instance
        messages: List of messages to process (conversation context)
        config: RunnableConfig dict with configurable fields (thread_id, message_id, etc.)
        interrupted: Whether this is resuming an interrupted conversation
        
    Yields:
        Dict containing graph state updates during execution
        
    Returns:
        Iterator yielding state updates from the orchestrator
    """
    try:
        print("interrupted:", interrupted)
        if interrupted:
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            print(f"Resuming interrupted conversation with messages: {messages[-1].content}")
            yield from orchestrator.resume_with_feedback(messages[-1].content, config)
        
        else:
            # Start new streaming conversation
            yield from orchestrator.run_stream(messages, config)
    except Exception as e:
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        yield {
            "error": f"{type(e).__name__}: {str(e)}",
            "thread_id": thread_id,
            "traceback": traceback.format_exc(),
        }


