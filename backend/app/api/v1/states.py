"""
States API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import crud, get_db
from app.models.responses import StateResponse

router = APIRouter()


@router.get("/{state_uid}", response_model=StateResponse)
async def get_state(
    state_uid: str,
    include_full: bool = Query(False, description="Include all state fields"),
    db: Session = Depends(get_db)
):
    """
    Get state details by UID.
    
    Args:
        state_uid: Unique state identifier
        include_full: If True, returns all state fields (paths, reasoning, etc.)
                     If False, returns only basic info
    """
    state = crud.get_state(db, state_uid)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    
    return state.to_dict(include_full=include_full)


@router.get("/message/{message_id}", response_model=StateResponse)
async def get_state_by_message(
    message_id: int,
    include_full: bool = Query(False, description="Include all state fields"),
    db: Session = Depends(get_db)
):
    """Get state for a specific message."""
    state = crud.get_state_by_message(db, message_id)
    if not state:
        raise HTTPException(status_code=404, detail="No state found for this message")
    
    return state.to_dict(include_full=include_full)
