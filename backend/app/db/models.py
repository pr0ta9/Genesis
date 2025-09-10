"""
SQLAlchemy models for Genesis backend.
Three main tables: conversations, messages, and states.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Conversation(Base):
    """Conversation (thread) model."""
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True)  # thread_id
    title = Column(Text, nullable=False, default="New Conversation")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    @property
    def message_count(self):
        """Get message count."""
        return len(self.messages) if self.messages else 0
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.message_count
        }


class Message(Base):
    """Message model."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    reasoning = Column(JSON, nullable=True)  # Store reasoning data with thinking_time, content, etc.
    state_id = Column(String, ForeignKey("states.uid"), nullable=True)  # Links to state if exists
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    # One-to-one: Message can have one State
    state = relationship("State", primaryjoin="Message.state_id==State.uid", uselist=False)
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "reasoning": self.reasoning,  # Include reasoning data
            "state_id": self.state_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "has_state": self.state is not None
        }


class State(Base):
    """State model - stores all fields from orchestrator State TypedDict."""
    __tablename__ = "states"
    
    uid = Column(String, primary_key=True)  # Unique state identifier
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    
    # Control flow
    node = Column(String, nullable=True)
    next_node = Column(String, nullable=True)
    
    # Classify node results
    objective = Column(Text, nullable=True)
    input_type = Column(String, nullable=True)
    type_savepoint = Column(JSON, nullable=True)  # List of WorkflowTypeEnum
    is_complex = Column(Boolean, nullable=True)
    classify_reasoning = Column(Text, nullable=True)
    classify_clarification = Column(Text, nullable=True)
    
    # Path node results
    tool_metadata = Column(JSON, nullable=True)  # List of tool metadata
    all_paths = Column(JSON, nullable=True)  # All possible paths discovered
    
    # Router node results  
    chosen_path = Column(JSON, nullable=True)  # The selected path for execution
    route_reasoning = Column(Text, nullable=True)
    route_clarification = Column(Text, nullable=True)
    is_partial = Column(Boolean, nullable=True)
    
    # Execute node results
    execution_results = Column(JSON, nullable=True)  # ExecutionResult dict
    execution_instance = Column(String, nullable=True)  # e.g., "genesis_erase_1kn9z1gc"
    execution_output_path = Column(Text, nullable=True)  # Path to output file
    
    # Finalizer node results
    is_complete = Column(Boolean, nullable=True)
    response = Column(Text, nullable=True)
    finalize_reasoning = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    
    # Error tracking
    error_details = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    # One-to-many: State belongs to one Message (for tracking which message created this state)
    message = relationship("Message", primaryjoin="State.message_id==Message.id")
    
    def to_dict(self, include_full: bool = False):
        """Convert to dictionary for API responses."""
        base_dict = {
            "uid": self.uid,
            "message_id": self.message_id,
            "node": self.node,
            "next_node": self.next_node,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "has_execution": bool(self.execution_instance),
            "execution_instance": self.execution_instance,
            "is_complete": self.is_complete
        }
        
        if include_full:
            # Ensure path data is JSON-serializable
            def serialize_path_data(data):
                """Convert path data to JSON-serializable format."""
                if data is None:
                    return None
                if isinstance(data, list):
                    result = []
                    for item in data:
                        if isinstance(item, dict):
                            # Remove function references
                            serialized = {k: v for k, v in item.items() if k != 'function'}
                            result.append(serialized)
                        else:
                            result.append(item)
                    return result
                return data
            
            # Include all fields when requested
            base_dict.update({
                # Classify
                "objective": self.objective,
                "input_type": self.input_type,
                "type_savepoint": self.type_savepoint,
                "is_complex": self.is_complex,
                "classify_reasoning": self.classify_reasoning,
                "classify_clarification": self.classify_clarification,
                
                # Path - serialize to ensure JSON compatibility
                "tool_metadata": serialize_path_data(self.tool_metadata),
                "all_paths": serialize_path_data(self.all_paths),
                
                # Router
                "chosen_path": serialize_path_data(self.chosen_path),
                "route_reasoning": self.route_reasoning,
                "route_clarification": self.route_clarification,
                "is_partial": self.is_partial,
                
                # Execute
                "execution_results": self.execution_results,
                "execution_output_path": self.execution_output_path,
                
                # Finalizer
                "response": self.response,
                "finalize_reasoning": self.finalize_reasoning,
                "summary": self.summary,
                
                # Errors
                "error_details": self.error_details
            })
        
        return base_dict
