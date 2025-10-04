"""
Chat API endpoints.

Provides CRUD operations for chats using the database CRUD layer in
`src/db/crud.py`.
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.db.database import get_db
from src.db import crud

router = APIRouter(prefix="/chats", tags=["chats"])

# ===== Models =====

class UpdateChatRequest(BaseModel):
    title: str

# ===== Routes =====

@router.post("/", response_model=dict)
def create_chat(
    db: Session = Depends(get_db),
):
    """Create a new chat."""
    chat = crud.create_chat(db)
    return chat.to_dict()

@router.get("/", response_model=List[dict])
def list_chats(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List chats ordered by most recent update time."""
    chats = crud.list_chats(db, limit=limit, offset=offset)
    return [c.to_dict() for c in chats]

@router.get("/{chat_id}", response_model=dict)
def get_chat_detail(
    chat_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific chat and all of its messages."""
    chat = crud.get_chat(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = crud.get_messages(db, chat_id)
    return {
        "chat": chat.to_dict(),
        "messages": [m.to_dict() for m in messages],
    }

@router.put("/{chat_id}", response_model=dict)
def update_chat(
    chat_id: str,
    request: UpdateChatRequest,
    db: Session = Depends(get_db),
):
    """Update a chat's title."""
    chat = crud.update_chat(db, chat_id, title=request.title)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat.to_dict()

@router.delete("/{chat_id}", response_model=Dict[str, Any])
def delete_chat(
    chat_id: str,
    db: Session = Depends(get_db),
):
    """Delete a chat and any orphaned states."""
    success = crud.delete_chat(db, chat_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "deleted", "chat_id": chat_id}