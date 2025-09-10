"""
Streaming infrastructure for ephemeral content like reasoning.
This module provides a clean way to stream content that should NOT be stored in state.
"""
from contextvars import ContextVar
from typing import Optional, Callable, Dict, Any, TypeVar, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
from datetime import datetime


class StreamEventType(Enum):
    """Types of streaming events"""
    REASONING = "reasoning"
    STATUS = "status"
    PROGRESS = "progress"
    TOKEN = "token"
    DEBUG = "debug"


class StatusType(Enum):
    """Types for unified emit_status"""
    STATE_UPDATE = "state_update"
    REASONING = "reasoning"
    ERROR = "error"
    EXECUTION_EVENT = "execution_event"


@dataclass
class StreamEvent:
    """Represents a streaming event"""
    type: StreamEventType
    content: Any
    node: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    ephemeral: bool = True  # By default, all stream events are ephemeral
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        # If content is already a properly formatted event dict, return it
        if (isinstance(self.content, dict) and 
            "event" in self.content and 
            "timestamp" in self.content and 
            "data" in self.content):
            return self.content
        
        # Otherwise, return the old format for backward compatibility
        return {
            "type": self.type.value,
            "content": self.content,
            "node": self.node,
            "metadata": self.metadata or {},
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ephemeral": self.ephemeral
        }


# Type for stream writer callback
StreamWriter = Callable[[StreamEvent], None]
AsyncStreamWriter = Callable[[StreamEvent], asyncio.Future]

# Context variable to hold the current stream writer
stream_writer_var: ContextVar[Optional[StreamWriter]] = ContextVar('stream_writer', default=None)
async_stream_writer_var: ContextVar[Optional[AsyncStreamWriter]] = ContextVar('async_stream_writer', default=None)


def set_stream_writer(writer: Optional[StreamWriter]) -> None:
    """Set the stream writer for the current context"""
    stream_writer_var.set(writer)


def set_async_stream_writer(writer: Optional[AsyncStreamWriter]) -> None:
    """Set the async stream writer for the current context"""
    async_stream_writer_var.set(writer)


def get_stream_writer() -> Optional[StreamWriter]:
    """Get the current stream writer"""
    return stream_writer_var.get()


def get_async_stream_writer() -> Optional[AsyncStreamWriter]:
    """Get the current async stream writer"""
    return async_stream_writer_var.get()


# Removed emit_reasoning functions - use emit_status instead


def emit_status(type: Union[StatusType, str], node: str, content: Optional[str] = None, 
                state_update: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> None:
    """
    Unified status emission function with consistent event format.
    
    Args:
        type: Type of status (StatusType enum or string)
        node: Current node name
        content: Optional content for reasoning and errors
        state_update: Optional state update dict (result from node)
        event: Optional execution event data
    """
    writer = stream_writer_var.get()
    if writer:
        # Convert StatusType enum to string if needed
        type_str = type.value if isinstance(type, StatusType) else type
        
        # Build event data based on type
        event_data = {
            "node": node,
        }
        
        if type_str == StatusType.STATE_UPDATE.value:
            event_data["state_update"] = state_update
            event_data["status"] = content or f"State updated in {node}"
            event_data["fields"] = list(state_update.keys()) if state_update else []
        elif type_str == StatusType.REASONING.value:
            event_data["reasoning"] = content
            event_data["status"] = "Reasoning update"
        elif type_str == StatusType.ERROR.value:
            event_data["error"] = content
            event_data["status"] = "Error occurred"
        elif type_str == StatusType.EXECUTION_EVENT.value:
            event_data.update(event or {})
            event_data["status"] = content or event_data.get("status", "Execution event")
        
        # Build dict event first
        formatted_event = {
            "event": type_str,
            "timestamp": datetime.now().isoformat(),
            "data": event_data
        }
        
        # Also prepare StreamEvent for legacy consumers
        stream_event = StreamEvent(
            type=StreamEventType.STATUS,
            content=formatted_event,
            node=node,
            metadata=formatted_event
        )
        
        # Prefer sending dicts; fall back to object if the writer expects StreamEvent
        try:
            writer(formatted_event)
        except Exception:
            try:
                writer(stream_event)
            except Exception as emit_err:
                # Final fallback: log and drop
                print(f"emit_status failed to deliver event: {emit_err}")


def emit_progress(progress: float, node: str, message: str = "", **metadata) -> None:
    """
    Emit a progress update.
    
    Args:
        progress: Progress value between 0.0 and 1.0
        node: The node reporting progress
        message: Optional progress message
        **metadata: Additional metadata
    """
    writer = stream_writer_var.get()
    if writer:
        event = StreamEvent(
            type=StreamEventType.PROGRESS,
            content={"value": progress, "message": message},
            node=node,
            metadata=metadata
        )
        writer(event)


class StreamingContext:
    """
    Context manager for setting up streaming in a specific scope.
    """
    def __init__(self, writer: Union[StreamWriter, AsyncStreamWriter], is_async: bool = False):
        self.writer = writer
        self.is_async = is_async
        self._token = None
        
    def __enter__(self):
        if self.is_async:
            self._token = async_stream_writer_var.set(self.writer)
        else:
            self._token = stream_writer_var.set(self.writer)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.is_async:
            async_stream_writer_var.reset(self._token)
        else:
            stream_writer_var.reset(self._token)
            
    async def __aenter__(self):
        return self.__enter__()
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


# Convenience function for GUI integration
def create_gui_stream_writer(callback: Callable[[Dict[str, Any]], None]) -> StreamWriter:
    """
    Create a stream writer that converts events to dictionaries for GUI consumption.
    
    Args:
        callback: GUI callback that accepts dictionary events
        
    Returns:
        StreamWriter function
    """
    def writer(event):
        # Support both dict and StreamEvent inputs
        if isinstance(event, dict):
            callback(event)
        else:
            try:
                callback(event.to_dict())
            except Exception:
                # As a very last resort, wrap minimal info
                try:
                    callback({
                        "event": getattr(event, "type", None).value if getattr(event, "type", None) else "unknown",
                        "timestamp": getattr(event, "timestamp", None).isoformat() if getattr(event, "timestamp", None) else datetime.now().isoformat(),
                        "data": getattr(event, "content", {}) if hasattr(event, "content") else {}
                    })
                except Exception:
                    pass
    return writer
