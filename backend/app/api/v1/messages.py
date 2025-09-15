"""
Messages API endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud, get_db
from app.db.database import get_output_dir
from app.models.requests import SendMessageRequest, SendClarificationRequest
from app.models.responses import SendMessageResponse, MessageResponse
from app.services.orchestrator_service import get_orchestrator
from src.streaming import StreamingContext
import shutil
from pathlib import Path
from datetime import datetime

router = APIRouter()


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    db: Session = Depends(get_db)
):
    """Send a message to the orchestrator and get response."""
    # Verify conversation exists
    conversation = crud.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Create user message in DB
    # Prepare content for storage (original) and for orchestrator (annotated)
    original_content = request.content
    orchestrator_content = original_content
    if getattr(request, "file_paths", None):
        try:
            file_list = "\n".join(str(p) for p in request.file_paths or [])
            orchestrator_content = f"{original_content}\n\n<files>\n{file_list}\n</files>"
        except Exception:
            pass

    user_message = crud.create_message(
        db, 
        conversation_id=conversation_id,
        role="user",
        content=original_content,
        reasoning={
            "additional_kwargs": {
                "file_paths": request.file_paths
            }
        } if getattr(request, "file_paths", None) else None
    )
    
    try:
        # Get orchestrator service
        orchestrator_service = get_orchestrator()
        
        # Get message history
        messages = crud.get_messages(db, conversation_id)
        message_history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages[:-1]  # Exclude the message we just created
        ]
        
        # Process through orchestrator (without streaming for REST endpoint)
        result = await orchestrator_service.process_message(
            conversation_id=conversation_id,
            user_input=orchestrator_content,
            message_history=message_history
        )
        
        # Extract response
        response_text = orchestrator_service.get_response_from_result(result)
        
        # Extract state data
        state_data = orchestrator_service.extract_state_data(result)
        
        # Create state record
        state = crud.create_state(db, user_message.id, state_data)
        
        # Prepare reasoning data from state for storage
        reasoning_data = None
        reasoning_parts = []
        
        # Collect reasoning from different workflow stages
        if state.classify_reasoning:
            reasoning_parts.append(f"**Classification:**\n{state.classify_reasoning}")
        if state.route_reasoning:
            reasoning_parts.append(f"**Routing:**\n{state.route_reasoning}")
        if state.finalize_reasoning:
            reasoning_parts.append(f"**Finalization:**\n{state.finalize_reasoning}")
        
        if reasoning_parts:
            combined_reasoning = "\n\n".join(reasoning_parts)
            reasoning_data = {
                "content": combined_reasoning,
                "thinking_time": len(reasoning_parts) * 3,  # Rough estimate
                "is_expanded": False,
                "is_thinking": False,
                "additional_kwargs": {
                    "reasoning_content": combined_reasoning,
                    "workflow_reasoning": True
                }
            }
        
        # Create assistant message
        assistant_message = crud.create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            reasoning=reasoning_data,
            state_id=state.uid
        )
        
        # Handle output files if execution occurred
        if state.execution_instance:
            await _copy_outputs_to_conversation(
                conversation_id, 
                state.execution_instance,
                state.uid
            )
        
        # Determine if there's a clarification request
        has_clarification = bool(
            state.classify_clarification or state.route_clarification
        )
        clarification_type = None
        if state.classify_clarification:
            clarification_type = "classify"
        elif state.route_clarification:
            clarification_type = "route"
        
        return SendMessageResponse(
            message=assistant_message,
            response=response_text,
            state_uid=state.uid,
            has_clarification=has_clarification,
            clarification_type=clarification_type,
            execution_instance=state.execution_instance
        )
        
    except Exception as e:
        # Delete the user message if processing failed
        db.delete(user_message)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: str,
    limit: int = None,
    db: Session = Depends(get_db)
):
    """Get messages for a conversation."""
    conversation = crud.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = crud.get_messages(db, conversation_id, limit=limit)
    return messages


@router.post("/{conversation_id}/clarification", response_model=SendMessageResponse)
async def send_clarification(
    conversation_id: str,
    request: SendClarificationRequest,
    db: Session = Depends(get_db)
):
    """Send clarification response to resume orchestrator."""
    # Verify conversation exists
    conversation = crud.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Create clarification message in DB
    clarification_message = crud.create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=request.feedback
    )
    
    try:
        # Get orchestrator service
        orchestrator_service = get_orchestrator()
        
        # Resume with feedback
        result = await orchestrator_service.process_clarification(
            conversation_id=conversation_id,
            feedback=request.feedback
        )
        
        # Extract response
        response_text = orchestrator_service.get_response_from_result(result)
        
        # Extract state data
        state_data = orchestrator_service.extract_state_data(result)
        
        # Create state record
        state = crud.create_state(db, clarification_message.id, state_data)
        
        # Create assistant message
        assistant_message = crud.create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            state_id=state.uid
        )
        
        # Handle output files if execution occurred
        if state.execution_instance:
            await _copy_outputs_to_conversation(
                conversation_id,
                state.execution_instance,
                state.uid
            )
        
        return SendMessageResponse(
            message=assistant_message,
            response=response_text,
            state_uid=state.uid,
            has_clarification=False,  # Clarification should be resolved
            execution_instance=state.execution_instance
        )
        
    except Exception as e:
        # Delete the clarification message if processing failed
        db.delete(clarification_message)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


async def _copy_outputs_to_conversation(
    conversation_id: str, 
    execution_instance: str,
    state_uid: str
) -> None:
    """Copy outputs from tmp execution directory to conversation output directory."""
    # This is a placeholder - would need to be implemented based on 
    # how the executor saves outputs
    output_dir = get_output_dir(conversation_id)
    
    # TODO: Copy relevant files from tmp/execution_instance/ to output_dir/
    # For now, just create a marker file
    marker_file = output_dir / f"{state_uid}_{execution_instance}.json"
    marker_file.write_text(f'{{"execution": "{execution_instance}", "timestamp": "{datetime.now().isoformat()}"}}')
