"""
Conversations API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import crud, get_db
from app.models.requests import CreateConversationRequest, UpdateConversationRequest
from app.models.responses import ConversationResponse, ConversationDetailResponse
from app.db.database import OUTPUT_DIR, get_output_dir
import shutil


router = APIRouter()


@router.post("/", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    db: Session = Depends(get_db)
):
    """Create a new conversation."""
    conversation = crud.create_conversation(db, title=request.title)
    return conversation


@router.get("/", response_model=List[ConversationResponse])
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List all conversations."""
    conversations = crud.list_conversations(db, limit=limit, offset=offset)
    return conversations


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    include_full: bool = Query(False, description="Include full state fields for each message"),
    db: Session = Depends(get_db)
):
    """Get conversation details with messages."""
    result = crud.get_conversation_with_messages(db, conversation_id, include_full=include_full)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Debug trace: compare include_full False vs True for the most recent assistant message (if any)
    try:
        messages = result.get("messages") or []
        recent_assistant = next((m for m in reversed(messages) if m.get("role") == "assistant" and m.get("state")), None)
        if recent_assistant:
            state_uid = recent_assistant.get("state", {}).get("uid")
            if state_uid:
                from app.db import crud as _crud
                state_obj = _crud.get_state(db, state_uid)
                if state_obj:
                    shallow = state_obj.to_dict(include_full=False)
                    full = state_obj.to_dict(include_full=True)
                    import json
                    print(json.dumps({
                        "debug": "conversation_state_compare",
                        "state_uid": state_uid,
                        "shallow_keys": list(shallow.keys()),
                        "full_has_paths": bool(full.get("all_paths")),
                        "full_has_chosen": bool(full.get("chosen_path")),
                        "full_has_meta": bool(full.get("tool_metadata")),
                        "include_full_param": include_full,
                    }))
                    print(f"length of all_paths: {len(full.get('all_paths'))}")
    except Exception:
        pass
    return result


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    db: Session = Depends(get_db)
):
    """Update conversation title."""
    conversation = crud.update_conversation_title(db, conversation_id, request.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Delete a conversation and its associated data."""
    # Delete from database
    if not crud.delete_conversation(db, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Delete output directory if exists
    output_dir = get_output_dir(conversation_id)
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    
    return {"status": "deleted", "conversation_id": conversation_id}


@router.put("/{conversation_id}/clear")
async def clear_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Clear all messages from a conversation."""
    if not crud.clear_conversation_messages(db, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"status": "cleared", "conversation_id": conversation_id}
