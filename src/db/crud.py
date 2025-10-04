from datetime import datetime, timezone
from typing import List, Optional, Iterable, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, delete, exists, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
import uuid
from .model import Chat, Message, State

VALID_ROLES = {"user", "assistant"}
VALID_TYPES = {"question", "response"}

def _state_column_keys() -> set[str]:
    # Only real columns, not relationships/properties
    return {c.key for c in inspect(State).mapper.column_attrs}

# =========================================
# Chat CRUD
# =========================================

def create_chat(db: Session) -> Chat:
    """Create a new chat with a generated id.

    Args:
        title: Optional chat title; defaults to "New Chat" when not provided.
    """
    chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    chat = Chat(
        id=chat_id,
        title="New Chat",
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat

def get_chat(db: Session, chat_id: str) -> Optional[Chat]:
    """Get a chat by id."""
    return db.query(Chat).filter(Chat.id == chat_id).first()

def list_chats(db: Session, limit: int = 50, offset: int = 0) -> List[Chat]:
    """List chats ordered by most recent update time."""
    return (
        db.query(Chat)
        .order_by(desc(Chat.updated_at))
        .limit(limit)
        .offset(offset)
        .all()
    )

def update_chat(db: Session, chat_id: str, title: Optional[str] = None) -> Optional[Chat]:
    """Update a chat's title and/or updated_at.

    Behavior:
      - If title is None: only bump updated_at to now
      - Else: set title and bump updated_at to now
    """
    chat = get_chat(db, chat_id)
    if not chat:
        return None

    if title is not None:
        chat.title = title

    # Explicitly update timestamp so it always bumps even if only title changes
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(chat)
    return chat

def delete_chat(db: Session, chat_id: str) -> bool:
    chat = db.query(Chat).get(chat_id)
    if not chat:
        return False
    db.delete(chat)
    db.flush()
    cleanup_orphan_states(db)
    db.commit()
    return True

def cleanup_orphan_states(db: Session, state_ids: Optional[Iterable[str]] = None) -> int:
    """
    Delete State rows that no longer have any Message referencing them.

    If state_ids is provided, only consider those; otherwise do a global cleanup.
    Returns number of State rows deleted.
    """
    if state_ids:
        stmt = delete(State).where(
            State.uid.in_(list(state_ids)),
            ~exists(select(1).where(Message.state_id == State.uid)),
        )
    else:
        stmt = delete(State).where(
            ~exists(select(1).where(Message.state_id == State.uid))
        )
    res = db.execute(stmt)
    return res.rowcount or 0

# =========================================
# Message CRUD
# =========================================

def create_message(
    db: Session,
    chat_id: str,
    role: str,
    content: str,
    *,
    state_id: Optional[str] = None,
    reasoning: Optional[dict] = None,
    attachments: Optional[list] = None,
    msg_type: str = "response",
) -> Message:
    """Create a new message in a chat.

    Args:
        chat_id: Target chat identifier
        role: "user" or "assistant"
        content: message content
        state_id: optional linked state uid
        reasoning: optional JSONB payload
        attachments: optional file attachment metadata (list of dicts)
        msg_type: "question" or "response" (default: "response")
    """
    if role not in VALID_ROLES:
        raise ValueError("role must be 'user' or 'assistant'")
    if msg_type not in VALID_TYPES:
        raise ValueError("msg_type must be 'question' or 'response'")

    chat = db.get(Chat, chat_id)
    if not chat:
        raise ValueError(f"chat '{chat_id}' not found")

    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        reasoning=reasoning,
        attachments=attachments,
        state_id=state_id,
        type=msg_type,
    )
    db.add(message)
    chat.updated_at = func.now()
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise ValueError(f"failed to create message: {e.orig}") from e
    db.refresh(message)
    return message

def get_messages(db: Session, chat_id: str, limit: Optional[int] = None) -> List[Message]:
    """Get messages for a chat ordered by timestamp."""
    query = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.timestamp.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()

def get_message(db: Session, message_id: int) -> Optional[Message]:
    """Get a specific message by ID."""
    return db.get(Message, message_id)

def update_message(
    db: Session,
    message_id: int,
    *,
    content: Optional[str] = None,
    msg_type: Optional[str] = None,
    state_id: Optional[str] = None,
    reasoning: Optional[dict] = None,
    attachments: Optional[List[dict]] = None,
) -> Optional[Message]:
    """Update a message's content, type, state, reasoning, or attachments.
    
    Args:
        message_id: The message ID to update
        content: New content (if provided)
        msg_type: New type "question" or "response" (if provided)
        state_id: New state_id (if provided)
        reasoning: New reasoning dict (if provided)
        attachments: New attachments list (if provided)
        
    Returns:
        Updated message or None if not found
    """
    message = db.get(Message, message_id)
    if not message:
        return None
    
    if content is not None:
        message.content = content
    if msg_type is not None:
        if msg_type not in VALID_TYPES:
            raise ValueError("msg_type must be 'question' or 'response'")
        message.type = msg_type
    if state_id is not None:
        message.state_id = state_id
    if reasoning is not None:
        message.reasoning = reasoning
    if attachments is not None:
        message.attachments = attachments
    
    # Bump chat updated_at
    db.query(Chat).filter(Chat.id == message.chat_id).update({"updated_at": func.now()})
    
    try:
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        return None

def set_message_precedent_id(db: Session, message_id: int, precedent_id: Optional[str]) -> bool:
    """Set the precedent_id for a specific message.

    Uses string type to align with the new schema. Pass None to clear the precedent_id.
    """
    message = db.get(Message, message_id)
    if not message:
        return False

    message.precedent_id = precedent_id
    db.query(Chat).filter(Chat.id == message.chat_id).update({"updated_at": func.now()})

    try:
        db.commit()
    except Exception:
        db.rollback()
        return False
    db.refresh(message)
    return True

# =========================================
# State CRUD
# =========================================

def create_state(
    db: Session,
    state_data: Dict[str, Any],
    *,
    uid: Optional[str] = None,
    commit: bool = True,
) -> State:
    cols = {c.key for c in inspect(State).mapper.column_attrs}
    payload = {k: v for k, v in state_data.items() if k in cols and k != "uid"}
    state = State(uid=uid or f"state_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}", **payload)
    db.add(state)
    if commit:
        db.commit(); db.refresh(state)
    else:
        db.flush()  # make uid visible for FK linkage
    return state

def get_state(db: Session, state_uid: str) -> Optional[State]:
    """Get a state by UID."""
    return db.get(State, state_uid)

def get_state_by_message(db: Session, message_id: int) -> Optional[State]:
    """Get the state linked to a specific message (if any)."""
    msg = db.get(Message, message_id)
    if not msg or not msg.state_id:
        return None
    return db.get(State, msg.state_id)

def update_state(db: Session, state_uid: str, updates: Dict[str, Any]) -> Optional[State]:
    """Update fields on a state and return the refreshed entity."""
    state = db.get(State, state_uid)
    if not state:
        return None

    cols = _state_column_keys()
    for key, value in updates.items():
        if key in cols and key != "uid":
            setattr(state, key, value)

    db.commit()
    db.refresh(state)
    return state
