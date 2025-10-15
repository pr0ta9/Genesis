"""
Message API endpoints.

POST /messages/{chat_id}
- Accepts message content and optional file uploads
- Saves uploaded files to inputs/{chat_id}/
- Creates a user message with file attachments
- Streams orchestrator events back to the client (NDJSON)
- After streaming completes, persists final state and assistant message
"""
from typing import Optional, Iterator, Dict, Any, Tuple, Union, List
import json
import os
import mimetypes
import uuid
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db import crud, semantics

from src.orchestrator.stream.stream import stream as orchestrator_stream
from langchain_core.messages import HumanMessage, AIMessage


router = APIRouter(prefix="/messages", tags=["messages"])


# Orchestrator and Weaviate are accessed via Request.app.state (gated in main.py)


Jsonable = Union[dict, list, str, int, float, bool, None]


def _deep_merge(destination: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries; source values overwrite destination when not None."""
    for key, value in source.items():
        # Always update if value is not None, or if key doesn't exist in destination
        if value is not None or key not in destination:
            if isinstance(value, dict) and isinstance(destination.get(key), dict):
                _deep_merge(destination[key], value)
            else:
                destination[key] = value
    return destination


def _flatten_state_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten LangGraph nested state updates to match database schema.
    
    LangGraph sends updates like: {'classify': {'node': 'classify', 'objective': '...'}}
    Database expects flat structure: {'node': 'classify', 'objective': '...'}
    
    Also serializes Pydantic models (like PathItem) to JSON-safe dicts.
    """
    flattened = {}
    
    # Handle special non-node keys directly
    for key, value in update.items():
        if key in ('__interrupt__',):
            # Normalize Interrupt objects to string values immediately for consistency
            if isinstance(value, (list, tuple)) and value:
                interrupt_obj = value[0]
                if hasattr(interrupt_obj, 'value'):
                    # Extract string value from Interrupt object
                    flattened[key] = [interrupt_obj.value]
                else:
                    # Fallback: stringify the object
                    flattened[key] = [str(interrupt_obj)]
            else:
                flattened[key] = value
        elif isinstance(value, dict):
            # This is a node update - flatten its contents and serialize values
            for field_key, field_value in value.items():
                flattened[field_key] = _to_jsonable(field_value)
        else:
            # Direct field update - serialize value
            flattened[key] = _to_jsonable(value)
    
    return flattened


def _to_jsonable(value: Any) -> Jsonable:
    """Convert common non-JSON types to JSON-safe structures."""
    from langchain_core.messages import HumanMessage as _HM, AIMessage as _AM, AIMessageChunk  # local to avoid import cycles during startup
    from pydantic import BaseModel  # For handling Pydantic models like PathItem

    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        # Handle tuples like (AIMessageChunk, metadata)
        return [_to_jsonable(v) for v in value]
    if isinstance(value, BaseModel):
        # Handle Pydantic models (like PathItem) by converting to dict and removing functions
        model_dict = value.model_dump()
        # Remove function fields that aren't JSON-serializable
        if 'function' in model_dict:
            model_dict.pop('function')
        return _to_jsonable(model_dict)
    if isinstance(value, _HM):
        return {"role": "user", "content": value.content}
    if isinstance(value, _AM):
        return {
            "role": "assistant", 
            "content": value.content,
            "additional_kwargs": _to_jsonable(value.additional_kwargs) if value.additional_kwargs else {},
            "response_metadata": _to_jsonable(value.response_metadata) if value.response_metadata else {},
        }
    if isinstance(value, AIMessageChunk):
        return {
            "role": "assistant",
            "content": value.content,
            "additional_kwargs": _to_jsonable(value.additional_kwargs) if value.additional_kwargs else {},
            "response_metadata": _to_jsonable(value.response_metadata) if value.response_metadata else {},
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _normalize_event(raw: Any) -> Tuple[str, Any]:
    """Normalize event shapes to (type, payload).

    Accepts either:
      - (etype: str, payload)
      - {"type": etype, ...}
      - any other raw payload → ("data", raw)
    """
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], str):
        return raw[0], raw[1]
    if isinstance(raw, dict) and "type" in raw:
        return str(raw["type"]), raw
    return "data", raw


def _ndjson(event_type: str, payload: Any) -> str:
    obj = {"type": event_type, "data": _to_jsonable(payload)}
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _should_yield_message_chunk(
    chunk_content: str, 
    chunk_accumulator: str, 
    streaming_state: str, 
    quote_count: int
) -> tuple[bool, str, int, Optional[str]]:
    """
    Determine if a message chunk should be yielded based on user-facing content filtering.
    
    Returns:
        (should_yield, new_streaming_state, new_quote_count, truncated_content)
        truncated_content is None for normal yielding, or modified content for partial yields
    """
    should_yield_chunk = False
    new_streaming_state = streaming_state
    new_quote_count = quote_count
    truncated_content = None
    
    if streaming_state == "NORMAL":
        # Look for user-facing keys with opening quote pattern
        for key in ['"response":', '"clarification_question":']:
            if key in chunk_accumulator:
                key_pos = chunk_accumulator.rfind(key)
                if key_pos != -1:
                    # Look for what comes after the key
                    after_key_start = key_pos + len(key)
                    remaining = chunk_accumulator[after_key_start:].strip()
                    
                    # Check if this key's value has already been closed
                    if remaining.startswith('"'):
                        # Find the closing quote for this value
                        quote_count = 0
                        i = 1  # Start after the opening quote
                        value_closed = False
                        
                        while i < len(remaining):
                            if remaining[i] == '"' and remaining[i-1] != '\\':
                                # Found unescaped closing quote
                                value_closed = True
                                break
                            i += 1
                        
                        # Only start streaming if the value is NOT already closed
                        if not value_closed:
                            # Check for empty value patterns
                            if remaining.startswith('""') or remaining.startswith('"null"'):
                                # Empty value or null, don't stream
                                new_streaming_state = "NORMAL"
                            else:
                                # We have an opening quote and value is not closed, start streaming
                                new_streaming_state = "IN_VALUE"
                                new_quote_count = 0
                                
                                # Check if current chunk contains content that should be yielded
                                content_after_quote = remaining[1:]  # Skip the opening quote
                                if content_after_quote:
                                    should_yield_chunk = True
                    break
    elif streaming_state == "IN_VALUE":
        # We're inside a value, look for any unescaped quote to end streaming
        should_yield_chunk = True  # Default to yielding while in value
        
        # Find first unescaped quote in this chunk
        i = 0
        while i < len(chunk_content):
            if chunk_content[i] == '"':
                # Check if it's escaped by looking at the previous character
                if i > 0 and chunk_content[i - 1] == '\\':
                    # This quote is escaped, continue
                    pass
                else:
                    # Found unescaped closing quote - stop streaming
                    new_streaming_state = "NORMAL"
                    new_quote_count = 0
                    if i == 0:
                        # Closing quote at start of chunk, don't yield
                        should_yield_chunk = False
                    else:
                        # Yield only content up to the closing quote
                        truncated_content = chunk_content[:i]
                    break
            i += 1
    
    return should_yield_chunk, new_streaming_state, new_quote_count, truncated_content


def _project_root() -> Path:
    root = os.environ.get("GENESIS_PROJECT_ROOT") or os.getcwd()
    return Path(root).resolve()


def _inputs_root() -> Path:
    return Path(os.environ.get("GENESIS_INPUTS_ROOT", _project_root() / "inputs")).resolve()


async def _upload_files(chat_id: str, files: List[UploadFile]) -> Tuple[List[Dict], str]:
    """Upload files and create attachment metadata + file tags.
    
    Returns:
        Tuple of (attachment_list, file_tags_string)
    """
    if not files:
        return [], ""
    
    try:
        base_dir = (_inputs_root() / chat_id).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        attachments: List[Dict] = []
        file_tags: List[str] = []
        
        for f in files:
            name = Path(f.filename or "file").name
            dest = base_dir / name
            
            # Avoid overwrite by adding numeric suffix
            stem, suffix = Path(name).stem, Path(name).suffix
            counter = 1
            while dest.exists():
                dest = base_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            content = await f.read()
            
            # Write file with explicit flush and sync to prevent race conditions
            # This ensures the file is fully written to disk before orchestrator accesses it
            with open(dest, 'wb') as file_handle:
                file_handle.write(content)
                file_handle.flush()  # Flush Python buffers
                os.fsync(file_handle.fileno())  # Force OS to write to disk
            
            size = dest.stat().st_size
            mime, _ = mimetypes.guess_type(str(dest))
            
            # Create attachment metadata
            attachments.append({
                "filename": dest.name,
                "path": str(dest),
                "size": size,
                "mime_type": mime or "application/octet-stream",
            })
            
            # Create file tag for orchestrator
            file_tags.append(f"<file>inputs/{chat_id}/{dest.name}</file>")

        return attachments, "\n".join(file_tags)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")


def format_message_with_attachments(message_content: str, attachments: Optional[list]) -> str:
    """
    Format a message by appending <file> tags for each attachment.
    
    Args:
        message_content: The original message content
        attachments: List of attachment metadata dictionaries
        
    Returns:
        Formatted message content with <file> tags appended
    """
    if not attachments:
        return message_content
        
    file_tags = []
    for attachment in attachments:
        path = attachment.get('path')
        if path:
            # Extract relative path from the full path for <file> tag
            if '/inputs/' in path:
                # Convert /app/inputs/chat_123/file.png -> inputs/chat_123/file.png
                relative_path = 'inputs/' + path.split('/inputs/')[-1]
                file_tags.append(f"<file>{relative_path}</file>")
    
    if file_tags:
        file_tags_str = "\n".join(file_tags)
        return f"{message_content}\n\n{file_tags_str}" if message_content.strip() else file_tags_str
    
    return message_content


@router.post("/{chat_id}")
async def post_message(  # Changed to async
    chat_id: str,
    req: Request,
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),  # Added files parameter
    interrupted: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Stream orchestrator events while ensuring persistence after completion."""
    # Validate chat exists
    chat = crud.get_chat(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Validate feedback is provided when resuming interrupted workflow
    if not message or message.strip() == "":
        raise HTTPException(
            status_code=400, 
            detail="Feedback is required to resume an interrupted workflow. Please provide your response."
        )

    # Handle file uploads (if any)
    attachments, file_tags = await _upload_files(chat_id, files)  # Call _upload_files
    # Combine message content with file tags for orchestrator processing
    orchestrator_content = message
    if file_tags:
        orchestrator_content = f"{message}\n\n{file_tags}" if message.strip() else file_tags

    # Create user message with attachments
    print(f"[DB LOG] Creating user message with db session: {db}")
    user_msg = crud.create_message(
        db,
        chat_id=chat_id,
        role="user",
        content=message,               # Clean content for user display
        attachments=attachments,       # Metadata for frontend display
        msg_type="question",
    )
    print(f"[DB LOG] Created user message with id: {user_msg.id}")
    
    # Create assistant message placeholder FIRST to get real ID
    print(f"[DB LOG] Creating assistant message with db session: {db}")
    assistant_msg = crud.create_message(
        db,
        chat_id=chat_id,
        role="assistant",
        content="",  # Empty for now, will be updated after streaming
        msg_type="response",  # Default to response, will update if interrupted
    )
    print(f"[DB LOG] Created assistant message with id: {assistant_msg.id}")
    
    # Extract IDs before session closes (avoid DetachedInstanceError)
    assistant_msg_id = assistant_msg.id
    user_msg_id = user_msg.id
    print(f"[DB LOG] Extracted IDs - user_msg_id: {user_msg_id}, assistant_msg_id: {assistant_msg_id}")
    
    # Fetch all messages BEFORE closing the db session
    print(f"[DB LOG] About to call crud.get_messages with db session: {db}")
    db_messages = crud.get_messages(db, chat_id)
    print(f"[DB LOG] Successfully got {len(db_messages)} messages")
    
    # Close the database session NOW to free up connection pool
    # The session will be reopened later only for final persistence
    db.close()
    print(f"[DB LOG] Closed db session to free connection pool")
    
    # Build thread-safe config (each request has isolated config)
    config = {
        "configurable": {
            "thread_id": chat_id,              # Used by LangGraph for checkpointing
            "message_id": assistant_msg_id,    # Used by executor for output folders
        }
    }

    def event_generator() -> Iterator[str]:
        state_uid: Optional[str] = None
        accum_state: List[Dict[str, Any]] = []
        last_updated_node: Optional[str] = None  # "classify" | "precedent" | "route"
        reasoning_events: List[Dict[str, Any]] = []
        chunk_accumulator: str = ""  # Accumulate message chunks
        
        # State for tracking user-facing content streaming
        streaming_state = "NORMAL"  # NORMAL, FOUND_KEY, IN_VALUE
        quote_count = 0  # Track quotes to find value boundaries
        
        try:
            # Build full conversation context in chronological order
            # (db_messages already fetched above before closing db session)
            messages: List[Union[HumanMessage, AIMessage]] = []
            for m in reversed(db_messages):  # crud returns DESC; reverse to ASC
                # Skip the assistant message placeholder we just created (it's empty)
                if m.role == "assistant" and m.id == assistant_msg_id:
                    continue
                    
                if m.role == "user":
                    # Format user messages with their attachments for orchestrator
                    if m.id == user_msg_id:
                        # Use the already prepared orchestrator content for current message
                        formatted_content = orchestrator_content
                    else:
                        # Format historical messages with their attachments
                        formatted_content = format_message_with_attachments(m.content, m.attachments)
                    messages.append(HumanMessage(content=formatted_content))
                else:
                    messages.append(AIMessage(content=m.content))
            orchestrator = req.app.state.orchestrator
            for raw in orchestrator_stream(orchestrator, messages, config, interrupted):
                etype, payload = _normalize_event(raw)

                # Handle message chunks with smart filtering for user-facing content
                if etype == "messages":
                    # Extract content from AIMessageChunk (payload is always a tuple)
                    chunk_obj = payload[0]  # AIMessageChunk
                    chunk_content = chunk_obj.content or ""
                    if chunk_content:
                        chunk_accumulator += chunk_content
                        
                        # Use helper function to determine if this chunk should be yielded
                        should_yield_chunk, streaming_state, quote_count, truncated_content = _should_yield_message_chunk(
                            chunk_content, chunk_accumulator, streaming_state, quote_count
                        )
                        
                        # Try to parse for state persistence (regardless of yielding)
                        try:
                            parsed_json = json.loads(chunk_accumulator)
                            if isinstance(parsed_json, dict):
                                json_patch = _to_jsonable(parsed_json)
                                if isinstance(json_patch, dict):
                                    accum_state.append(json_patch)
                                chunk_accumulator = ""  # Reset after successful parse
                                streaming_state = "NORMAL"  # Reset streaming state
                                quote_count = 0
                        except (json.JSONDecodeError, ValueError):
                            # Not valid JSON yet, continue accumulating
                            pass
                        
                        # Only yield this message event if it contains user-facing content
                        if should_yield_chunk:
                            if truncated_content is not None:
                                # Modify payload directly with truncated content
                                original_content = chunk_obj.content
                                chunk_obj.content = truncated_content
                                yield _ndjson(etype, payload)
                                chunk_obj.content = original_content  # Restore original
                            else:
                                # Normal yielding
                                yield _ndjson(etype, payload)
                    
                        # Continue to next iteration to avoid yielding again below
                        continue

                # Incremental state persistence for other event types
                elif etype in ("updates", "state_update"):
                    patch: Dict[str, Any] = payload if isinstance(payload, dict) else {"data": payload}
                    # Store raw patch (with Interrupt objects intact) for proper extraction later
                    if isinstance(patch, dict):
                        accum_state.append(patch)
                        
                        # Normalize workflow enums for frontend before yielding
                        normalized_patch = {}
                        for key, value in patch.items():
                            if isinstance(value, dict):
                                normalized_node = {}
                                for node_key, node_value in value.items():
                                    if node_key in ("input_type", "type_savepoint"):
                                        print(f"[DB LOG] Normalizing node key: {node_key} with value: {node_value}")
                                        normalized_node[node_key] = _normalize_workflow_enum(node_value)
                                    else:
                                        normalized_node[node_key] = node_value
                                normalized_patch[key] = normalized_node
                            else:
                                normalized_patch[key] = value
                        payload = normalized_patch
                        print(f"[DB LOG] Normalized patch: {payload}")

                        # Track which node most recently updated for clarification mapping
                        for node_key in ("classify", "precedent", "route"):
                            if node_key in patch:
                                last_updated_node = node_key

                        # NOTE: Incremental state persistence is now DISABLED during streaming
                        # to avoid holding database connections open. Final state will be
                        # persisted after streaming completes using a new session.
                        # This prevents connection pool exhaustion.

                # Collect structured reasoning from specific custom events only
                if etype == "custom":
                    candidate = _to_jsonable(payload)
                    print(f"[DB LOG] Custom event received - type: {type(candidate)}, data: {candidate}")
                    if isinstance(candidate, dict):
                        # Log executor events separately
                        if "tool_name" in candidate:
                            print(f"[DB LOG] Executor custom event: tool_name={candidate.get('tool_name')}, status={candidate.get('status')}, has_stdout={('stdout' in candidate)}, workspace_dir={candidate.get('workspace_dir')}")
                        
                        # Collect reasoning events for persistence
                        if (
                            "node" in candidate and
                            "content" in candidate and
                            "timestamp" in candidate and
                            "think_duration" in candidate
                        ):
                            reasoning_events.append({
                                "node": candidate.get("node"),
                                "content": candidate.get("content"),
                                "timestamp": candidate.get("timestamp"),
                                "think_duration": candidate.get("think_duration"),
                            })
                            print(f"[DB LOG] Reasoning custom event: node={candidate.get('node')}")

                # Forward all other events to frontend (custom, error, etc.)
                # Note: "messages" events are handled above with filtering
                yield _ndjson(etype, payload)

            merged_state = {}
            for state in accum_state:
                flat_state = _flatten_state_update(state)
                _deep_merge(merged_state, flat_state)
            
            # Create a NEW database session for final persistence
            # (the original session was closed before streaming started)
            from src.db.database import SessionLocal
            final_db = SessionLocal()
            try:
                if state_uid is None:
                    if accum_state:
                        print(f"[DB LOG] About to call crud.create_state (final) with NEW db session: {final_db}")
                        st = crud.create_state(final_db, merged_state)
                        state_uid = getattr(st, "uid", None)
                        print(f"[DB LOG] Successfully created final state: {state_uid}")
                else:
                    if accum_state:
                        print(f"[DB LOG] About to call crud.update_state (final) with NEW db session: {final_db}")
                        crud.update_state(final_db, state_uid, merged_state)
                        print(f"[DB LOG] Successfully updated final state: {state_uid}")
            except Exception as e:
                print(f"[DB LOG] Error in final state persistence: {e}")
                # Best-effort persistence; do not interrupt response generation
                pass

            # Determine interruption and message type/content
            # Check ONLY the latest state for interrupt (not all accumulated states)
            # Flatten the last state to properly extract interrupt value
            last_state_flattened = _flatten_state_update(accum_state[-1]) if accum_state else {}
            is_interrupted = "__interrupt__" in last_state_flattened
            if is_interrupted:
                # Extract the interrupt message from the flattened last state
                msg_type = "question"
                interrupt_list = last_state_flattened.get("__interrupt__")
                print(f"Interrupt list: {interrupt_list}")
                # Interrupt is always normalized to [string_value] in _flatten_state_update
                msg_content = interrupt_list[0] if interrupt_list else ""
                print(f"Extracted interrupt message: {msg_content}")
            else:
                msg_type = "response"
                # Extract response content from the state
                # Priority: 1) "response" field (from finalize node), 2) messages[-1].content (fallback)
                msg_content = ""
                
                # First, check for "response" field in the merged state (produced by finalize node)
                if merged_state and "response" in merged_state:
                    msg_content = merged_state["response"]
                    print(f"[DB LOG] Extracted message content from 'response' field: {msg_content[:100]}...")
                
                # Fallback: look for messages in the last state update
                elif accum_state:
                    # Get the last state (most recent node)
                    last_state = accum_state[-1]
                    # Find any node that has messages
                    for node_name, node_data in last_state.items():
                        if isinstance(node_data, dict) and "messages" in node_data:
                            messages = node_data["messages"]
                            if messages and isinstance(messages, list) and len(messages) > 0:
                                last_message = messages[-1]
                                if isinstance(last_message, dict) and "content" in last_message:
                                    msg_content = last_message["content"]
                                    print(f"[DB LOG] Extracted message content from messages: {msg_content[:100]}...")
                                    break

            # Extract output file attachments from execution results
            output_attachments = []
            try:
                exec_results = merged_state.get("execution_results")
                if exec_results and isinstance(exec_results, dict):
                    final_output = exec_results.get("final_output")
                    if final_output and isinstance(final_output, str):
                        # Convert Docker path to relative path and create attachment
                        import os
                        from pathlib import Path
                        import mimetypes
                        
                        # Normalize path
                        output_path = final_output.replace("/app/outputs/", "").replace("\\", "/")
                        full_path = Path(os.environ.get("GENESIS_PROJECT_ROOT", ".")) / "outputs" / output_path
                        
                        if full_path.exists():
                            stat = full_path.stat()
                            mime, _ = mimetypes.guess_type(str(full_path))
                            output_attachments.append({
                                "path": final_output,  # Store Docker path for consistency
                                "size": stat.st_size,
                                "filename": full_path.name,
                                "mime_type": mime or "application/octet-stream"
                            })
            except Exception as e:
                print(f"[DB LOG] Failed to extract output attachments: {e}")
            
            # Update assistant message with final content, state, and attachments
            # Use the same final_db session created above
            try:
                print(f"[DB LOG] About to call crud.update_message with NEW db session: {final_db}, assistant_msg_id: {assistant_msg_id}")
                crud.update_message(
                    final_db,
                    assistant_msg_id,
                    content=msg_content,
                    state_id=state_uid,
                    reasoning={"content": reasoning_events} if reasoning_events else None,
                    msg_type=msg_type,
                    attachments=output_attachments if output_attachments else None,
                )
                print(f"[DB LOG] Successfully updated assistant message {assistant_msg_id} with state uid: {state_uid} and {len(output_attachments)} attachments")
            finally:
                # ALWAYS close the final_db session to free the connection
                final_db.close()
                print(f"[DB LOG] Closed final_db session")

            # Emit a final persisted notification so the client has IDs
            yield json.dumps({
                "type": "persisted",
                "data": {
                    "user_message_id": user_msg_id,
                    "assistant_message_id": assistant_msg_id,
                    "state_uid": state_uid,
                    "message_type": msg_type,  # Include type for interrupt detection
                }
            }, ensure_ascii=False) + "\n"

        except Exception as e:
            print(f"[DB LOG] Exception in generator: {type(e).__name__}: {str(e)}")
            # Make sure to close final_db if it was created
            try:
                if 'final_db' in locals():
                    final_db.close()
                    print(f"[DB LOG] Closed final_db session after exception")
            except:
                pass
            yield _ndjson("error", {"message": f"{type(e).__name__}: {str(e)}"})

    print(f"[DB LOG] About to return StreamingResponse (original db session already closed)")
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

def _normalize_workflow_enum(value: Any) -> Any:
    """
    Normalize WorkflowTypeEnum to simplified format for frontend.
    
    Converts: WorkflowTypeEnum.AUDIOFILE or "<WorkflowTypeEnum.AUDIOFILE: 'audiofile'>" -> "AUDIO"
    """
    # Import enum class to check instance
    from src.orchestrator.path.metadata import WorkflowTypeEnum
    from enum import Enum
    
    # Handle actual enum instances (the root cause of the bug)
    if isinstance(value, WorkflowTypeEnum) or (isinstance(value, Enum) and 'WorkflowTypeEnum' in type(value).__name__):
        enum_name = value.name  # Gets "AUDIOFILE" from the enum
        mapping = {
            "AUDIOFILE": "AUDIO",
            "IMAGEFILE": "IMAGE",
            "VIDEOFILE": "VIDEO",
            "TEXTFILE": "TEXT_FILE",
            "DOCUMENTFILE": "DOCUMENT",
            "STRUCTUREDDATA": "DATA",
            "TEXT": "TEXT",
        }
        return mapping.get(enum_name, enum_name)
    
    # Handle string representations (fallback for serialized enums)
    if isinstance(value, str):
        # Extract enum name from string representation
        import re
        match = re.search(r"WorkflowTypeEnum\.(\w+)", value)
        if match:
            enum_name = match.group(1)
            mapping = {
                "AUDIOFILE": "AUDIO",
                "IMAGEFILE": "IMAGE",
                "VIDEOFILE": "VIDEO",
                "TEXTFILE": "TEXT_FILE",
                "DOCUMENTFILE": "DOCUMENT",
                "STRUCTUREDDATA": "DATA",
                "TEXT": "TEXT",
            }
            return mapping.get(enum_name, enum_name)
    
    # Handle lists and dicts recursively
    elif isinstance(value, list):
        return [_normalize_workflow_enum(item) for item in value]
    elif isinstance(value, dict):
        return {k: _normalize_workflow_enum(v) for k, v in value.items()}
    
    return value


@router.get("/{message_id}")
def get_message_state(
    message_id: int,
    db: Session = Depends(get_db),
):
    """Get a message by ID with full state data including paths."""
    state = crud.get_state_by_message(db, message_id)
    state_dict = state.to_dict(include_full=True)
    
    # Normalize workflow enum representations for frontend
    # Frontend will use these to construct the correct endpoints
    if "input_type" in state_dict:
        state_dict["input_type"] = _normalize_workflow_enum(state_dict["input_type"])
    if "type_savepoint" in state_dict:
        state_dict["type_savepoint"] = _normalize_workflow_enum(state_dict["type_savepoint"])
    
    return state_dict

@router.post("/{message_id}/precedent", response_model=Dict[str, Any])
def save_message_as_precedent(
    message_id: int,
    req: Request,
    db: Session = Depends(get_db),
):
    """
    Save a specific assistant message's workflow as a precedent in Weaviate.
    Extracts workflow data from the associated state and stores it for future retrieval.
    """
    # Get the message
    message = db.get(crud.Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify it's an assistant message
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be saved as precedents")
    
    # Verify it has a state
    if not message.state_id:
        raise HTTPException(status_code=400, detail="Message has no workflow state")
    
    # Check if already saved as precedent
    if message.precedent_id:
        return {
            "success": True,
            "message": "This workflow is already saved as a precedent",
            "precedent_id": message.precedent_id,
            "already_exists": True
        }
    
    # Get the state
    state = crud.get_state(db, message.state_id)
    if not state:
        raise HTTPException(status_code=400, detail="Workflow state not found")
    
    # Get full state data (include_full=True to get objective, chosen_path, etc.)
    state_dict = state.to_dict(include_full=True)
    
    # Extract required fields for precedent
    objective = state_dict.get("objective", "")
    if not objective:
        raise HTTPException(status_code=400, detail="No objective found in workflow state")
    
    # Build description for semantic search (combining objective and conversation context)
    # Get all messages in this chat for context
    chat_messages = crud.get_messages(db, message.chat_id)
    conversation_text = ""
    for msg in chat_messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        conversation_text += f"{role_label}: {msg.content}\n\n"
    
    description = f"Objective: {objective}\n\nConversation:\n{conversation_text}"
    
    # Extract workflow data
    # tool_metadata contains the full PathToolMetadata objects (not just tool names)
    tool_metadata = state_dict.get("tool_metadata", [])
    is_complex = state_dict.get("is_complex", False)
    chosen_path = state_dict.get("chosen_path", [])
    input_type = state_dict.get("input_type")
    type_savepoint = state_dict.get("type_savepoint", [])
    created_at = state_dict.get("created_at")
    
    # Construct router_format from state fields (route_reasoning, route_clarification, chosen_path)
    route_reasoning = state_dict.get("route_reasoning", "")
    route_clarification = state_dict.get("route_clarification")
    
    # Convert chosen_path (PathItem objects) to SimplePath format (name + param_values only)
    simple_path = []
    if chosen_path:
        for item in chosen_path:
            if isinstance(item, dict):
                simple_path.append({
                    "name": item.get("name", ""),
                    "param_values": item.get("param_values", {})
                })
    
    # Build router_format structure
    router_format = [
        {
            "path": simple_path,
            "reasoning": route_reasoning,
            "clarification_question": route_clarification
        }
    ] if simple_path else []
    
    # DEBUG: Check what we have
    print(f"[PRECEDENT DEBUG] tool_metadata type: {type(tool_metadata)}, length: {len(tool_metadata) if isinstance(tool_metadata, list) else 'N/A'}")
    print(f"[PRECEDENT DEBUG] tool_metadata: {tool_metadata}")
    print(f"[PRECEDENT DEBUG] router_format type: {type(router_format)}, length: {len(router_format) if isinstance(router_format, list) else 'N/A'}")
    print(f"[PRECEDENT DEBUG] router_format: {router_format}")
    print(f"[PRECEDENT DEBUG] chosen_path: {chosen_path}")
    print(f"[PRECEDENT DEBUG] input_type: {input_type}")
    print(f"[PRECEDENT DEBUG] type_savepoint: {type_savepoint}")
    
    # Generate UUID for this precedent
    precedent_uuid = str(uuid.uuid4())
    
    # Get current timestamp for updated_at
    current_time = datetime.utcnow()
    
    # Prepare data for Weaviate (matching the schema in create_precedent_collection)
    # Store raw enum values (string representations) for internal use
    # Include 'uid' so Weaviate uses it as both object ID and property value
    precedent_data = {
        "uid": precedent_uuid,
        "description": description.strip(),
        "path": tool_metadata,  # List of PathToolMetadata objects (not just names)
        "router_format": router_format,  # List of PathItem objects
        "messages": conversation_text.strip(),
        "objective": objective,
        "is_complex": is_complex,
        "input_type": input_type,  # Raw enum string representation
        "type_savepoint": type_savepoint if isinstance(type_savepoint, list) else [type_savepoint] if type_savepoint else [],
        "created_at": created_at,
        "updated_at": current_time,
    }
    
    print(f"[PRECEDENT DEBUG] Sending to Weaviate: {precedent_data}")
    
    # Get Weaviate client from app state
    weaviate_client = getattr(req.app.state, "weaviate_client", None)
    if not weaviate_client:
        raise HTTPException(status_code=500, detail="Weaviate client not available")
    
    # Save to Weaviate
    try:
        print(f"[PRECEDENT DEBUG] About to call semantics.save with UUID: {precedent_uuid}...")
        saved_uuid = semantics.save(weaviate_client, precedent_data, collection_name="precedent")
        print(f"[PRECEDENT DEBUG] ✅ Saved successfully! UUID: {saved_uuid}")
        
        # Verify the returned UUID matches what we provided
        if str(saved_uuid) != precedent_uuid:
            print(f"[PRECEDENT DEBUG] ⚠️ Warning: Returned UUID ({saved_uuid}) != provided UUID ({precedent_uuid})")
        
        # Update the message with precedent_id
        crud.set_message_precedent_id(db, message.id, precedent_uuid)
        
        return {
            "success": True,
            "message": "Workflow saved as precedent successfully",
            "precedent_id": precedent_uuid,
            "already_exists": False
        }
    except Exception as e:
        print(f"[PRECEDENT DEBUG] ❌ Weaviate error: {type(e).__name__}")
        print(f"[PRECEDENT DEBUG] ❌ Error details: {str(e)}")
        print(f"[PRECEDENT DEBUG] ❌ Error repr: {repr(e)}")
        print(f"[PRECEDENT DEBUG] ❌ Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to save precedent: {str(e)}")


@router.delete("/{message_id}/precedent", response_model=Dict[str, Any])
def delete_message_precedent(
    message_id: int,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Delete the precedent associated with a specific message.
    Removes the precedent from Weaviate and clears the precedent_id from the message.
    """
    # Get the message
    message = crud.get_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if not message.precedent_id:
        raise HTTPException(status_code=404, detail="Message has no associated precedent")
    
    # Delete from Weaviate
    weaviate_client = getattr(req.app.state, "weaviate_client", None)
    if not weaviate_client:
        raise HTTPException(status_code=500, detail="Weaviate client not available")
    
    try:
        print(f"[PRECEDENT DEBUG] Deleting precedent: {message.precedent_id}")
        
        # Clear precedent_id from all messages with this precedent
        crud.clear_precedent_ids(db, [message.precedent_id])
        
        # Delete from Weaviate
        deleted_count = semantics.delete(weaviate_client, [message.precedent_id], collection_name="precedent")
        
        if deleted_count == 0:
            raise HTTPException(status_code=500, detail="Failed to delete precedent from Weaviate")
        
        print(f"[PRECEDENT DEBUG] ✅ Deleted from Weaviate")
        
        return {
            "success": True,
            "message": "Precedent deleted successfully",
            "precedent_id": message.precedent_id
        }
        
    except Exception as e:
        print(f"[PRECEDENT DEBUG] ❌ Error deleting precedent: {str(e)}")
        print(f"[PRECEDENT DEBUG] ❌ Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to delete precedent: {str(e)}")