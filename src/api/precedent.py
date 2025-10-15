"""
Precedent management API.

Endpoints:
- GET /precedent        → list all precedents
- DELETE /precedent     → delete specific precedents by UUID
- DELETE /precedent/all → delete all precedents
"""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.client import get_weaviate_client
from src.db import semantics, crud
from src.db.database import get_db


router = APIRouter(prefix="/precedent", tags=["precedent"])


class DeletePrecedentRequest(BaseModel):
    """Request body for deleting precedents"""
    uuids: List[str]


@router.get("/")
def get_precedents(req: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get all precedents from the vector database.
    Also includes the chat_id if a message references this precedent.
    
    Returns:
        Dictionary containing list of precedents and count.
    """
    try:
        client = get_weaviate_client()
        precedents = semantics.show_all(client, collection_name="precedent")
        
        # Convert Weaviate objects to dictionaries
        precedent_list = []
        for prec in precedents:
            precedent_uuid = str(prec.uuid)
            
            # Find message that references this precedent to get chat_id
            message = crud.get_message_by_precedent_id(db, precedent_uuid)
            chat_id = message.chat_id if message else None
            
            # Extract properties and metadata
            precedent_dict = {
                "uuid": precedent_uuid,
                "properties": prec.properties,
                "chat_id": chat_id,
            }
            # Add any other metadata if needed
            if hasattr(prec, 'metadata'):
                precedent_dict["metadata"] = prec.metadata
            
            precedent_list.append(precedent_dict)
        
        return {
            "precedents": precedent_list,
            "count": len(precedent_list)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch precedents: {str(e)}"
        )


@router.delete("/")
def delete_precedents(
    req: Request,
    body: DeletePrecedentRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Delete specific precedents by their UUIDs.
    Also clears precedent_id from any messages referencing these precedents.
    
    Args:
        body: Request body containing list of UUIDs to delete.
        db: Database session for clearing message references.
        
    Returns:
        Dictionary with deletion status and count.
    """
    if not body.uuids:
        raise HTTPException(
            status_code=400,
            detail="No UUIDs provided for deletion"
        )
    
    try:
        # Clear precedent_id from messages first
        messages_updated = crud.clear_precedent_ids(db, body.uuids)
        
        # Delete from Weaviate
        client = get_weaviate_client()
        deleted_count = semantics.delete(
            client,
            uuid_list=body.uuids,
            collection_name="precedent"
        )
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "requested_count": len(body.uuids),
            "messages_updated": messages_updated
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete precedents: {str(e)}"
        )


@router.delete("/all")
def delete_all_precedents(req: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Delete all precedents from the vector database.
    Also clears precedent_id from all messages.
    
    Warning: This operation cannot be undone.
    
    Returns:
        Dictionary with deletion status.
    """
    try:
        # Get all precedent UUIDs first
        client = get_weaviate_client()
        all_precedents = semantics.show_all(client, collection_name="precedent")
        precedent_uuids = [str(prec.uuid) for prec in all_precedents]
        
        # Clear precedent_id from all messages
        messages_updated = crud.clear_precedent_ids(db, precedent_uuids)
        
        # Delete all precedents
        result = semantics.delete_all(client, collection_name="precedent")
        
        return {
            "success": result,
            "message": "All precedents deleted successfully",
            "deleted_count": len(precedent_uuids),
            "messages_updated": messages_updated
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete all precedents: {str(e)}"
        )

