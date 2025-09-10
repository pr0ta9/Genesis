"""
Request models for API endpoints.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    title: Optional[str] = Field(None, description="Conversation title")


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: str = Field(..., description="New conversation title")


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    content: str = Field(..., description="Message content")
    file_paths: Optional[List[str]] = Field(None, description="Paths to uploaded files")


class SendClarificationRequest(BaseModel):
    """Request to send clarification response."""
    feedback: str = Field(..., description="Clarification response")
