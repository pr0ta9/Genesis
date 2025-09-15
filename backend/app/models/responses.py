"""
Response models for API endpoints.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    """Conversation response model."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Message response model."""
    id: int
    conversation_id: str
    role: str
    content: str
    reasoning: Optional[Dict[str, Any]] = None  # Add reasoning field
    state_id: Optional[str] = None
    timestamp: datetime
    has_state: bool = False
    precedent_id: Optional[int] = None
    
    class Config:
        from_attributes = True



class StateResponse(BaseModel):
    """State response model."""
    uid: str
    message_id: int
    node: Optional[str] = None
    next_node: Optional[str] = None
    created_at: datetime
    has_execution: bool = False
    execution_instance: Optional[str] = None
    is_complete: Optional[bool] = None
    
    # Include full state data when requested
    objective: Optional[str] = None
    input_type: Optional[str] = None
    type_savepoint: Optional[List[str]] = None
    is_complex: Optional[bool] = None
    classify_reasoning: Optional[str] = None
    classify_clarification: Optional[str] = None

    # Precedent node fields
    precedents_found: Optional[List[Dict]] = None
    precedent_reasoning: Optional[str] = None
    precedent_clarification: Optional[str] = None
    
    # FIX: Correct types for path-related fields
    tool_metadata: Optional[List[Dict]] = None  
    all_paths: Optional[List[List[Dict]]] = None
    chosen_path: Optional[List[Dict]] = None 
    
    route_reasoning: Optional[str] = None
    route_clarification: Optional[str] = None
    is_partial: Optional[bool] = None
    execution_results: Optional[Dict] = None
    execution_output_path: Optional[str] = None
    response: Optional[str] = None
    finalize_reasoning: Optional[str] = None
    summary: Optional[str] = None
    error_details: Optional[str] = None
    
    class Config:
        from_attributes = True


class MessageWithStateResponse(MessageResponse):
    """Message with embedded state data."""
    state: Optional[StateResponse] = None


class ConversationDetailResponse(BaseModel):
    """Conversation with messages."""
    conversation: ConversationResponse
    messages: List[MessageWithStateResponse]


class SendMessageResponse(BaseModel):
    """Response after sending a message."""
    message: MessageResponse
    response: str
    state_uid: Optional[str] = None
    has_clarification: bool = False
    clarification_type: Optional[str] = None  # 'classify' or 'route'
    execution_instance: Optional[str] = None


class ModelResponse(BaseModel):
    """Available model information."""
    id: str
    name: str
    provider: str


class WorkspaceInfoResponse(BaseModel):
    """Workspace information."""
    project_root: str
    tmp_root: str
    output_root: str
    tmp_directories: List[Dict[str, Any]]
    total_tmp_dirs: int
    tmp_space_used: int  # bytes
    output_space_used: int  # bytes


class OutputFileResponse(BaseModel):
    """Output file information."""
    filename: str
    path: str
    size: int  # bytes
    created_at: datetime
    mime_type: Optional[str] = None
