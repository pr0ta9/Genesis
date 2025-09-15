"""
CRUD operations for Genesis backend.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
import uuid

from .models import Conversation, Message, State


def _capitalize_first_word(text: str) -> str:
    """Capitalize only the first word of a string, leaving the rest unchanged."""
    if not isinstance(text, str) or not text:
        return text
    parts = text.strip().split(" ", 1)
    if not parts:
        return text
    first = parts[0].capitalize()
    if len(parts) == 1:
        return first
    return f"{first} {parts[1]}"


# Conversation CRUD
def create_conversation(db: Session, title: Optional[str] = None) -> Conversation:
    """Create a new conversation."""
    conv_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    conversation = Conversation(
        id=conv_id,
        title=title or "New Conversation"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: str) -> Optional[Conversation]:
    """Get a conversation by ID."""
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()


def list_conversations(db: Session, limit: int = 50, offset: int = 0) -> List[Conversation]:
    """List conversations ordered by most recent."""
    return db.query(Conversation).order_by(
        desc(Conversation.updated_at)
    ).limit(limit).offset(offset).all()


def update_conversation_title(db: Session, conversation_id: str, title: str) -> Optional[Conversation]:
    """Update conversation title."""
    conversation = get_conversation(db, conversation_id)
    if conversation:
        conversation.title = _capitalize_first_word(title)
        conversation.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation_id: str) -> bool:
    """Delete a conversation and all related data."""
    conversation = get_conversation(db, conversation_id)
    if not conversation:
        return False

    # Collect message ids for this conversation
    messages = db.query(Message).filter(Message.conversation_id == conversation_id).all()
    message_ids = [m.id for m in messages] if messages else []

    # 1) Break the circular FK by nulling message.state_id first
    if message_ids:
        db.query(Message).filter(Message.id.in_(message_ids)).update({Message.state_id: None}, synchronize_session=False)

    # 2) Delete dependent states for those messages
    if message_ids:
        db.query(State).filter(State.message_id.in_(message_ids)).delete(synchronize_session=False)

    # 3) Delete messages themselves
    if message_ids:
        db.query(Message).filter(Message.id.in_(message_ids)).delete(synchronize_session=False)

    # 4) Delete the conversation
    db.delete(conversation)
    db.commit()
    return True


# Message CRUD
def create_message(db: Session, conversation_id: str, role: str, content: str, 
                  state_id: Optional[str] = None, reasoning: Optional[dict] = None) -> Message:
    """Create a new message."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        reasoning=reasoning,
        state_id=state_id
    )
    db.add(message)
    
    # Update conversation's updated_at
    conversation = get_conversation(db, conversation_id)
    if conversation:
        conversation.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(message)

    # If this is the first assistant reply and we have a state with an objective,
    # set the conversation title to the objective (capitalize first word) if still default/empty
    if role == "assistant" and state_id:
        state = get_state(db, state_id)
        objective_value = getattr(state, "objective", None) if state else None
        if isinstance(objective_value, str) and objective_value.strip() and conversation:
            current_title = (conversation.title or "").strip()
            if not current_title or current_title == "New Conversation":
                conversation.title = _capitalize_first_word(objective_value.strip())
                conversation.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(message)
    return message


def get_messages(db: Session, conversation_id: str, limit: Optional[int] = None) -> List[Message]:
    """Get messages for a conversation."""
    query = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.timestamp)
    
    if limit:
        query = query.limit(limit)
    
    return query.all()


def get_message(db: Session, message_id: int) -> Optional[Message]:
    """Get a specific message by ID."""
    return db.query(Message).filter(Message.id == message_id).first()


def set_message_precedent_id(db: Session, message_id: int, precedent_id: int) -> bool:
    """Set the precedent_id for a specific message."""
    try:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.precedent_id = precedent_id
            db.commit()
            db.refresh(message)
            print(f"✅ [CRUD] Successfully updated message {message_id} with precedent_id {precedent_id}")
            return True
        else:
            print(f"❌ [CRUD] Message {message_id} not found")
            return False
    except Exception as e:
        print(f"❌ [CRUD] Error updating message precedent_id: {e}")
        db.rollback()
        return False


# State CRUD
def create_state(db: Session, message_id: int, state_data: Dict[str, Any]) -> State:
    """Create a new state record."""
    state_uid = f"state_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # Debug logging for route/find_path states
    node = state_data.get("node")
    if node in ["route", "find_path"]:
        print(f"\n[CRUD Debug] create_state for {node}:")
        print(f"  - state_data keys: {list(state_data.keys())}")
        for key in ["all_paths", "chosen_path", "tool_metadata"]:
            if key in state_data:
                val = state_data[key]
                print(f"  - {key}: type={type(val)}, is_None={val is None}, len={len(val) if isinstance(val, (list, dict, str)) else 'N/A'}")
    
    # Create state with all fields from state_data
    state = State(
        uid=state_uid,
        message_id=message_id,
        **{k: v for k, v in state_data.items() if hasattr(State, k)}
    )
    
    db.add(state)
    db.commit()
    db.refresh(state)
    
    # Debug what was actually saved for route/find_path
    if node in ["route", "find_path"]:
        print(f"[CRUD Debug] After save, state attributes:")
        print(f"  - all_paths: {state.all_paths is not None}")
        print(f"  - chosen_path: {state.chosen_path is not None}")
        print(f"  - tool_metadata: {state.tool_metadata is not None}")
    
    # Update the message's state_id
    message = get_message(db, message_id)
    if message:
        message.state_id = state_uid
        db.commit()
    
    return state


def get_state(db: Session, state_uid: str) -> Optional[State]:
    """Get a state by UID."""
    return db.query(State).filter(State.uid == state_uid).first()


def get_state_by_message(db: Session, message_id: int) -> Optional[State]:
    """Get state for a specific message."""
    return db.query(State).filter(State.message_id == message_id).first()


def update_state(db: Session, state_uid: str, updates: Dict[str, Any]) -> Optional[State]:
    """Update state fields."""
    state = get_state(db, state_uid)
    if state:
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
        db.commit()
        db.refresh(state)
    return state


# Utility functions
def clear_conversation_messages(db: Session, conversation_id: str) -> bool:
    """Clear all messages from a conversation but keep the conversation."""
    conversation = get_conversation(db, conversation_id)
    if not conversation:
        return False

    # Collect message ids for this conversation
    messages = db.query(Message).filter(Message.conversation_id == conversation_id).all()
    message_ids = [m.id for m in messages] if messages else []

    # Break the circular FK by nulling message.state_id first
    if message_ids:
        db.query(Message).filter(Message.id.in_(message_ids)).update({Message.state_id: None}, synchronize_session=False)

    # Delete dependent states first
    if message_ids:
        db.query(State).filter(State.message_id.in_(message_ids)).delete(synchronize_session=False)

    # Delete messages
    if message_ids:
        db.query(Message).filter(Message.id.in_(message_ids)).delete(synchronize_session=False)

    # Update conversation's updated_at and commit once
    conversation.updated_at = datetime.utcnow()
    db.commit()
    return True


def get_conversation_with_messages(db: Session, conversation_id: str, include_full: bool = False) -> Optional[Dict[str, Any]]:
    """Get conversation with all messages and states.

    Args:
        include_full: when True, include full state details (paths/metadata)
    """
    conversation = get_conversation(db, conversation_id)
    if not conversation:
        return None
    
    messages = get_messages(db, conversation_id)
    
    return {
        "conversation": conversation.to_dict(),
        "messages": [
            {
                **msg.to_dict(),
                "state": msg.state.to_dict(include_full=include_full) if msg.state else None
            }
            for msg in messages
        ]
    }
