"""
Precedent API endpoints for saving and managing workflow precedents.
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import crud, get_db
from app.models.responses import MessageResponse
from pathlib import Path

router = APIRouter()


@router.post("/{conversation_id}/save-precedent")
async def save_workflow_precedent(
    conversation_id: str, 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Save a completed workflow as precedent for future use.
    Extracts workflow data from conversation history and saves to TiDB vector store.
    
    Args:
        conversation_id: ID of conversation containing completed workflow
        db: Database session
        
    Returns:
        Dict with precedent_id and status information
        
    Raises:
        HTTPException: If conversation not found or workflow not complete
    """
    print(f"🎯 [PRECEDENT API] Save precedent request for conversation: {conversation_id}")
    
    # Verify conversation exists
    conversation = crud.get_conversation(db, conversation_id)
    if not conversation:
        print(f"❌ [PRECEDENT API] Conversation not found: {conversation_id}")
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get all messages for this conversation
    messages = crud.get_messages(db, conversation_id)
    if not messages:
        print(f"❌ [PRECEDENT API] No messages found for conversation: {conversation_id}")
        raise HTTPException(status_code=400, detail="No messages found in conversation")
    
    print(f"📝 [PRECEDENT API] Found {len(messages)} messages in conversation")
    
    # Find the most recent completed workflow state
    latest_state = None
    latest_state_message_id = None
    for message in reversed(messages):  # Start from most recent
        if message.state_id:
            state = crud.get_state(db, message.state_id)
            if state and state.is_complete:
                latest_state = state
                latest_state_message_id = message.id
                print(f"✅ [PRECEDENT API] Found completed workflow state: {state.uid} (message_id={message.id})")
                break
    
    if not latest_state:
        print(f"❌ [PRECEDENT API] No completed workflow found in conversation")
        raise HTTPException(status_code=400, detail="No completed workflow found in conversation")
    
    # Extract precedent data from state
    try:
        precedent_data = _extract_precedent_data_from_state(latest_state)
        print(f"📊 [PRECEDENT API] Extracted precedent data - objective: '{precedent_data['objective'][:100]}...'")
    except Exception as e:
        print(f"❌ [PRECEDENT API] Failed to extract precedent data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract workflow data: {str(e)}")
    
    # Create messages string for precedent context
    messages_str = "\n".join([f"{msg.role}: {msg.content}" for msg in messages])
    print(f"📝 [PRECEDENT API] Created messages context: {len(messages_str)} characters")
    
    # Save to TiDB using existing precedent functions
    try:
        from app.db.precedent import save_workflow_precedent
        
        precedent_id = save_workflow_precedent(
            objective=precedent_data["objective"],
            chosen_path=precedent_data["chosen_path"],
            router_format=precedent_data["router_format"],
            messages=messages_str,
            input_type=precedent_data["input_type"],
            is_complex=precedent_data["is_complex"],
            type_savepoint=precedent_data["type_savepoint"]
        )
        
        if precedent_id:
            print(f"✅ [PRECEDENT API] Successfully saved precedent: {precedent_id}")
            # Link the created precedent to the assistant message that produced the completed state
            try:
                if latest_state_message_id is not None:
                    crud.set_message_precedent_id(db, latest_state_message_id, int(precedent_id))
                    print(f"🔗 [PRECEDENT API] Linked precedent_id={precedent_id} to message_id={latest_state_message_id}")
            except Exception as e:
                print(f"⚠️ [PRECEDENT API] Failed to link precedent to message: {e}")
            return {
                "success": True,
                "precedent_id": precedent_id,
                "message": "Workflow precedent saved successfully",
                "conversation_id": conversation_id,
                "message_id": latest_state_message_id
            }
        else:
            print(f"❌ [PRECEDENT API] Failed to save precedent to TiDB")
            raise HTTPException(status_code=500, detail="Failed to save precedent to database")
            
    except Exception as e:
        print(f"❌ [PRECEDENT API] Error saving precedent: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving precedent: {str(e)}")


def _extract_precedent_data_from_state(state) -> Dict[str, Any]:
    """
    Extract precedent data from a completed workflow state.
    Uses the same extraction logic as orchestrator_service.py for consistency.
    
    Args:
        state: State object from database
        
    Returns:
        Dict containing all data needed for precedent storage
        
    Raises:
        ValueError: If required precedent data is missing
    """
    print(f"🔄 [PRECEDENT API] Extracting precedent data from state: {state.uid}")
    
    # Parse state data using the same logic as orchestrator service
    try:
        # Get the raw state dict (similar to orchestrator_result.get("state"))
        raw_state = state.to_dict(include_full=True)
        print(f"📊 [PRECEDENT API] Raw state keys: {list(raw_state.keys()) if raw_state else 'none'}")
        
        # Use orchestrator service extraction logic for consistent serialization
        from app.services.orchestrator_service import get_orchestrator
        orchestrator_service = get_orchestrator()
        
        # Create a mock orchestrator_result to use existing extraction logic
        mock_result = {"state": raw_state}
        state_data = orchestrator_service.extract_state_data(mock_result)
        print(f"📊 [PRECEDENT API] Processed state data keys: {list(state_data.keys()) if state_data else 'none'}")
        
    except Exception as e:
        raise ValueError(f"Failed to extract state data: {e}")
    
    # Check required fields for precedent storage
    required_fields = ["objective", "chosen_path", "all_paths", "input_type", "is_complex", "type_savepoint"]
    missing_fields = [field for field in required_fields if not state_data.get(field)]
    
    if missing_fields:
        print(f"❌ [PRECEDENT API] Missing required fields: {missing_fields}")
        raise ValueError(f"Missing required precedent fields: {missing_fields}")
    
    # Find matching PathMetadata from all_paths based on chosen_path
    chosen_path_metadata = _find_matching_path_metadata(
        state_data.get("chosen_path", []), 
        state_data.get("all_paths", [])
    )
    
    if not chosen_path_metadata:
        print(f"❌ [PRECEDENT API] Could not find matching path metadata")
        raise ValueError("Could not find matching path metadata for chosen path")
    
    # Extract router format from raw state (use raw state for router_response)
    router_format = raw_state.get("router_response", {})
    if not router_format and state_data.get("chosen_path"):
        # Convert PathItem format back to SimplePath format for router
        simple_path = []
        for path_item in state_data.get("chosen_path", []):
            if isinstance(path_item, dict):
                simple_path.append({
                    "name": path_item.get("name", ""),
                    "param_values": path_item.get("param_values", {})
                })
        
        router_format = {
            "path": simple_path,  # SimplePath format for router
            "reasoning": state_data.get("route_reasoning", ""),
            "clarification_question": state_data.get("route_clarification")
        }
        print(f"🔄 [PRECEDENT API] Constructed router format from chosen_path with {len(simple_path)} steps")
    
    precedent_data = {
        "objective": state_data.get("objective", ""),
        "chosen_path": chosen_path_metadata,  # Use PathMetadata format for precedent
        "router_format": router_format,
        "input_type": state_data.get("input_type", ""),
        "is_complex": state_data.get("is_complex", False),
        "type_savepoint": state_data.get("type_savepoint", [])
    }
    
    print(f"✅ [PRECEDENT API] Successfully extracted precedent data:")
    print(f"   📝 Objective: '{precedent_data['objective'][:100]}...'")
    print(f"   📊 Input type: {precedent_data['input_type']}, Complex: {precedent_data['is_complex']}")
    print(f"   🛠️  Workflow: {len(precedent_data['chosen_path'])} steps")
    
    return precedent_data


def _find_matching_path_metadata(chosen_path: List[Dict], all_paths: List[List[Dict]]) -> Optional[List[Dict[str, Any]]]:
    """
    Find the matching PathMetadata array from all_paths that corresponds to the chosen_path.
    
    Args:
        chosen_path: List of executed PathItem dictionaries
        all_paths: List of available PathMetadata arrays
        
    Returns:
        The matching PathMetadata array or None if not found
    """
    print(f"🔍 [PRECEDENT API] Finding path metadata match for {len(chosen_path)} chosen steps from {len(all_paths)} available paths")
    
    if not chosen_path or not all_paths:
        return None
    
    # Extract tool names from chosen_path for comparison
    chosen_tool_names = [item.get("name") for item in chosen_path if item.get("name")]
    print(f"🎯 [PRECEDENT API] Chosen tools: {chosen_tool_names}")
    
    # Find matching path by comparing tool sequences
    for i, path_metadata in enumerate(all_paths):
        if isinstance(path_metadata, list):
            path_tool_names = [tool.get("name") for tool in path_metadata if tool.get("name")]
            print(f"🔍 [PRECEDENT API] Checking path {i}: {path_tool_names}")
            
            if path_tool_names == chosen_tool_names:
                print(f"✅ [PRECEDENT API] Found matching path metadata at index {i}")
                return path_metadata
    
    print(f"❌ [PRECEDENT API] No matching path metadata found")
    return None
