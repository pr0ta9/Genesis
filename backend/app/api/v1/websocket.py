"""
WebSocket endpoint for real-time streaming updates.
"""
import json
import asyncio
from typing import Dict, Any, List
from fastapi.encoders import jsonable_encoder
from copy import deepcopy
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.db import get_db, crud
from app.services.orchestrator_service import get_orchestrator
from src.streaming import StreamingContext, create_gui_stream_writer, StreamEvent
from pathlib import Path
import os

router = APIRouter()

def serialize_tool_item(item):
    """Helper to serialize a single tool/path item - excludes function field entirely"""
    if item is None:
        return None
    
    # Handle PathToolMetadata with to_dict method
    if hasattr(item, 'to_dict'):
        result = item.to_dict()
        # Always exclude function field completely
        result.pop('function', None)
        return result
    
    # Handle PathItem or other Pydantic models
    if hasattr(item, 'model_dump'):
        serialized = item.model_dump(exclude={'function'})
        # Convert any enum types in param_types
        if 'param_types' in serialized:
            serialized['param_types'] = {
                k: v if isinstance(v, str) else str(v)
                for k, v in serialized['param_types'].items()
            }
        # Double-check function is excluded
        serialized.pop('function', None)
        return serialized
    
    # Handle Pydantic V1 models
    if hasattr(item, 'dict'):
        serialized = item.dict(exclude={'function'})
        if 'param_types' in serialized:
            serialized['param_types'] = {
                k: v if isinstance(v, str) else str(v)
                for k, v in serialized['param_types'].items()
            }
        # Double-check function is excluded
        serialized.pop('function', None)
        return serialized
    
    # Handle regular dicts
    if isinstance(item, dict):
        # Create a clean copy without function field
        serialized = {}
        for k, v in item.items():
            if k != 'function':  # Always skip function field
                serialized[k] = v
        
        # Convert param_types to strings
        if 'param_types' in serialized:
            serialized['param_types'] = {
                k: (v if isinstance(v, str) else str(v))
                for k, v in serialized['param_types'].items()
            }
        
        # Convert required_inputs to strings if present
        if 'required_inputs' in serialized and isinstance(serialized['required_inputs'], dict):
            serialized['required_inputs'] = {
                k: (v if isinstance(v, str) else str(v))
                for k, v in serialized['required_inputs'].items()
            }
        
        return serialized
    
    # Handle objects with __dict__
    if hasattr(item, '__dict__'):
        item_dict = {}
        for k, v in item.__dict__.items():
            if k != 'function':  # Always skip function field
                item_dict[k] = v
        return item_dict
    
    # Fallback to string representation
    return str(item)

def serialize_paths_and_metadata(value, field_name):
    """Serialize path and metadata fields properly."""
    if value is None:
        return None
    
    # Handle all_paths - list of paths, where each path is a list of tools
    if field_name == "all_paths":
        if isinstance(value, list):
            serialized_paths = []
            for path in value:
                if isinstance(path, list):
                    # Each path is a list of tool items
                    serialized_path = [serialize_tool_item(tool) for tool in path]
                    serialized_paths.append(serialized_path)
                elif isinstance(path, dict):
                    # Sometimes might be a dict representation
                    serialized_paths.append(serialize_tool_item(path))
                else:
                    # Unexpected structure
                    serialized_paths.append(str(path))
            return serialized_paths
    
    # Handle chosen_path and tool_metadata - single list of items
    elif field_name in ["chosen_path", "tool_metadata"]:
        if isinstance(value, list):
            return [serialize_tool_item(item) for item in value]
    
    # Default: try to serialize as is
    try:
        import json
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # If not serializable, convert to string
        return str(value)

def get_node_output_fields(node: str) -> List[str]:
    """Get the state fields that a node typically updates."""
    node_fields = {
        "classify": ["objective", "input_type", "type_savepoint", "is_complex", "classify_reasoning"],
        "find_path": ["all_paths", "tool_metadata"],
        "route": ["chosen_path", "route_reasoning", "is_partial"],
        "execute": ["execution_results", "execution_instance"],
        "finalize": ["response", "is_complete", "finalize_reasoning", "summary"]
    }
    return node_fields.get(node, [])


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for streaming orchestrator updates.
    
    Streams:
    - Reasoning content from agents
    - Stage changes
    - Execution progress
    - Tool outputs
    """
    await websocket.accept()
    
    try:
        loop = asyncio.get_running_loop()
        # Verify conversation exists
        conversation = crud.get_conversation(db, conversation_id)
        if not conversation:
            await websocket.close(code=4004, reason="Conversation not found")
            return
        
        # Create queue for streaming events
        event_queue = asyncio.Queue()
        
        # Create stream writer callback (thread-safe)
        def stream_callback(event_dict: Dict[str, Any]):
            """Callback that puts events into the async queue (supports worker threads)."""
            try:
                asyncio.run_coroutine_threadsafe(event_queue.put(event_dict), loop)
            except RuntimeError:
                # Fallback if loop not available
                print("stream_callback: no running loop; dropping event")
        
        # Get orchestrator service
        orchestrator_service = get_orchestrator()
        
        # Task to send queued events to WebSocket
        async def send_events():
            """Send events from queue to WebSocket."""
            while True:
                try:
                    event = await event_queue.get()
                    try:
                        # Ensure payload is JSON-serializable (handles enums, pydantic models, datetimes, etc.)
                        safe_event = jsonable_encoder(event, exclude_none=True)
                        await websocket.send_json(safe_event)
                    except TypeError as te:
                        # Add debug to identify unserializable payloads
                        debug_event = {
                            "type": "ws_error",
                            "message": "Serialization error",
                            "error": str(te),
                            "keys": list(event.keys()) if isinstance(event, dict) else str(type(event))
                        }
                        try:
                            await websocket.send_json(debug_event)
                        except Exception:
                            pass
                        print(f"WebSocket serialization error: {te}\nEvent:{event}")
                except Exception as e:
                    print(f"Error sending event: {e}")
                    break
        
        # Start event sender task
        sender_task = asyncio.create_task(send_events())
        
        # Listen for commands from client
        while True:
            try:
                # Wait for client messages
                data = await websocket.receive_json()
                command = data.get("command")
                
                if command == "ping":
                    await websocket.send_json({"type": "pong"})
                
                elif command == "process_message":
                    # Process message with streaming
                    content = data.get("content", "")
                    frontend_message_id = data.get("message_id")  # Get message ID from frontend
                    file_paths = data.get("file_paths") or []

                    # Map provided file_paths to stable references via inputs mapping
                    def _paths_to_references(paths: List[str]) -> List[str]:
                        try:
                            inputs_root = os.environ.get("GENESIS_INPUTS_ROOT") or str(Path(os.environ.get("GENESIS_PROJECT_ROOT", os.getcwd())) / "inputs")
                            mapping_path = Path(inputs_root) / conversation_id / "mapping.json"
                            if not mapping_path.exists():
                                return [Path(p).name for p in paths]
                            mapping = json.load(open(mapping_path, "r", encoding="utf-8"))
                            # Build reverse lookup by 'original' and 'path'
                            by_original = {}
                            by_path = {}
                            for ref_key, entry in mapping.items():
                                try:
                                    orig = str(Path(entry.get("original", "")).resolve()) if entry.get("original") else None
                                except Exception:
                                    orig = entry.get("original")
                                try:
                                    pth = str(Path(entry.get("path", "")).resolve()) if entry.get("path") else None
                                except Exception:
                                    pth = entry.get("path")
                                reference_name = entry.get("reference", ref_key)
                                if orig:
                                    by_original[orig.lower()] = reference_name
                                if pth:
                                    by_path[pth.lower()] = reference_name
                            refs = []
                            for p in paths:
                                try:
                                    rp = str(Path(p).resolve())
                                except Exception:
                                    rp = p
                                key = rp.lower()
                                ref = by_original.get(key) or by_path.get(key)
                                refs.append(ref if ref else Path(p).name)
                                print(f"new file ref: {ref}")
                            return refs
                        except Exception:
                            return [Path(p).name for p in paths]
                    
                    # Enhanced callback that tracks node completions and saves states
                    last_node = None
                    accumulated_state = {}  # Accumulate state updates
                    reasoning_content = []  # Collect reasoning content for database storage
                    user_message_id = None  # Will be set after creating user message
                    current_state_uid = None  # Track the current state record
                    
                    def enhanced_stream_callback(event_dict: Dict[str, Any]):
                        nonlocal last_node, accumulated_state, reasoning_content, user_message_id, current_state_uid
                        
                        # Handle new consistent event format
                        if isinstance(event_dict, dict) and "event" in event_dict and "data" in event_dict:
                            event_type = event_dict.get("event")
                            event_data = event_dict.get("data", {})
                            print(f"event_type: {event_type}")
                            # Persist execution artifact paths on file_saved
                            if event_type == "execution_event" and isinstance(event_data, dict):
                                try:
                                    status = event_data.get("status")
                                    if status == "file_saved" and current_state_uid and event_data.get("path"):
                                        # Update execution_output_path for convenience
                                        crud.update_state(db, current_state_uid, {
                                            "execution_output_path": event_data.get("path")
                                        })
                                except Exception:
                                    pass
                            if event_type == "reasoning":
                                raw_reasoning = event_data.get('reasoning', '')
                                # Parse pattern: <think>{reasoning}</think>{prompt_eval_duration}</time>
                                think_text = raw_reasoning
                                think_time_seconds = None
                                print(f"raw_reasoning: {raw_reasoning}")
                                try:
                                    if isinstance(raw_reasoning, str) and raw_reasoning.startswith("<think>"):
                                        # Extract inside <think>...</think>
                                        start = raw_reasoning.find("<think>") + len("<think>")
                                        end = raw_reasoning.find("</think>")
                                        if end != -1:
                                            think_text = raw_reasoning[start:end]
                                            time_suffix = raw_reasoning[end + len("</think>"):]
                                            # Expecting e.g. 226282900</time>
                                            time_val = time_suffix.replace("</time>", "").strip()
                                            print(f"time_val: {time_val}")
                                            # Convert ns to seconds if numeric
                                            if time_val.isdigit():
                                                ns = int(time_val)
                                                think_time_seconds = ns / 1_000_000_000
                                                print(f"think_time_seconds: {think_time_seconds}")
                                except Exception:
                                    pass
                                
                                if think_text:
                                    reasoning_content.append({
                                        "node": event_data.get("node"),
                                        "content": think_text,
                                        "timestamp": event_dict.get("timestamp"),
                                        "think_time_seconds": think_time_seconds
                                    })
                                    # Normalize outgoing payload so frontend sees only the inner think text
                                    try:
                                        event_data["reasoning"] = think_text
                                        if think_time_seconds is not None:
                                            event_data["thinking_time"] = think_time_seconds
                                    except Exception:
                                        pass
                            
                            # Handle state updates
                            if event_type == "state_update":
                                node = event_data.get("node")
                                state_update = event_data.get("state_update", {})

                                # Sanitize a deep-copied state_update for WebSocket/DB to avoid mutating orchestrator state
                                if isinstance(state_update, dict):
                                    su = deepcopy(state_update)
                                    # Drop heavy/non-serializable messages; expose count instead
                                    if "messages" in su and isinstance(su["messages"], list):
                                        su["messages_count"] = len(su["messages"])  # expose count for debugging
                                        su.pop("messages", None)
                                    # Convert enums to their values
                                    for key in ["input_type", "output_type"]:
                                        val = su.get(key)
                                        if hasattr(val, "value"):
                                            su[key] = val.value
                                    if isinstance(su.get("type_savepoint"), list):
                                        su["type_savepoint"] = [v.value if hasattr(v, "value") else v for v in su["type_savepoint"]]
                                    # Convert PathItem or pydantic models to dicts (exclude function refs when present)
                                    def _convert_item(item: Any) -> Any:
                                        try:
                                            if hasattr(item, "model_dump"):
                                                return item.model_dump(exclude={"function"})
                                            if hasattr(item, "dict"):
                                                return item.dict(exclude={"function"})
                                        except Exception:
                                            pass
                                        if hasattr(item, "__dict__"):
                                            d = item.__dict__.copy()
                                            d.pop("function", None)
                                            return d
                                        return item
                                    if isinstance(su.get("chosen_path"), list):
                                        su["chosen_path"] = [_convert_item(i) for i in su["chosen_path"]]
                                    # Ensure tool_metadata and all_paths are JSON-safe if present (nested lists)
                                    if isinstance(su.get("tool_metadata"), list):
                                        su["tool_metadata"] = [_convert_item(i) for i in su["tool_metadata"]]
                                    if isinstance(su.get("all_paths"), list):
                                        su["all_paths"] = [
                                            [_convert_item(step) for step in path] if isinstance(path, list) else _convert_item(path)
                                            for path in su["all_paths"]
                                        ]
                                    # Replace event_data copy for downstream (WS + DB), keep original state_update untouched
                                    event_data["state_update"] = su

                                    # Summary debug print for visibility across steps
                                    try:
                                        print(
                                            json.dumps({
                                                "event": "state_update_summary",
                                                "node": node,
                                                "has_all_paths": "all_paths" in su and su.get("all_paths") is not None,
                                                "has_chosen_path": "chosen_path" in su and su.get("chosen_path") is not None,
                                                "has_tool_metadata": "tool_metadata" in su and su.get("tool_metadata") is not None,
                                                "all_paths_len": len(su.get("all_paths", [])) if isinstance(su.get("all_paths"), list) else None,
                                                "chosen_path_len": len(su.get("chosen_path", [])) if isinstance(su.get("chosen_path"), list) else None,
                                                "messages_count": su.get("messages_count")
                                            })
                                        )
                                    except Exception:
                                        pass
                                
                                # Debug logging for route node
                                if node == "route" or node == "find_path":
                                    print(f"\n[WebSocket Debug] {node} state_update received:")
                                    print(f"  - all_paths present: {'all_paths' in state_update}")
                                    print(f"  - chosen_path present: {'chosen_path' in state_update}")
                                    print(f"  - tool_metadata present: {'tool_metadata' in state_update}")
                                    if 'all_paths' in state_update:
                                        print(f"  - all_paths type: {type(state_update['all_paths'])}")
                                        print(f"  - all_paths length: {len(state_update['all_paths']) if isinstance(state_update['all_paths'], list) else 'N/A'}")
                                    if 'chosen_path' in state_update:
                                        print(f"  - chosen_path type: {type(state_update['chosen_path'])}")
                                        print(f"  - chosen_path length: {len(state_update['chosen_path']) if isinstance(state_update['chosen_path'], list) else 'N/A'}")
                                # Only print state_update events
                                try:
                                    print(json.dumps({
                                        "event": "state_update",
                                        "data": {
                                            "node": node,
                                            "fields": list(state_update.keys()) if state_update else []
                                        }
                                    }, ensure_ascii=False))
                                except Exception:
                                    print(f"STATE_UPDATE {node}: {list(state_update.keys()) if state_update else []}")
                                
                                # No reasoning extraction from state_update; handled only via reasoning events
                                
                                # Save checkpoint to database (use sanitized copy if present)
                                sanitized_update = event_data.get("state_update") if isinstance(event_data.get("state_update"), dict) else state_update
                                if user_message_id and sanitized_update:
                                    try:
                                        # Extract relevant fields for state storage
                                        state_fields = {}
                                        for field, value in sanitized_update.items():
                                            # Store simple values directly
                                            if isinstance(value, (str, int, float, bool, type(None))):
                                                state_fields[field] = value
                                            # Special handling for important path/metadata fields
                                            elif field in ["all_paths", "chosen_path", "tool_metadata"]:
                                                # Use the serialization helper to properly convert these fields
                                                state_fields[field] = serialize_paths_and_metadata(value, field)
                                            elif field == "type_savepoint" and isinstance(value, list):
                                                # Preserve full list (already converted to enum values above)
                                                state_fields[field] = value
                                            elif isinstance(value, list):
                                                # For other lists, store count as before
                                                state_fields[f"{field}_count"] = len(value)
                                            elif isinstance(value, dict):
                                                # For other dicts, store keys as before
                                                state_fields[f"{field}_keys"] = list(value.keys())
                                        
                                        state_fields["node"] = node
                                        
                                        # Debug what we're about to save for route/find_path
                                        if node in ["route", "find_path"]:
                                            print(f"\n[WebSocket Debug] About to save {node} state:")
                                            print(f"  - state_fields keys: {list(state_fields.keys())}")
                                            for key in ["all_paths", "chosen_path", "tool_metadata"]:
                                                if key in state_fields:
                                                    val = state_fields[key]
                                                    print(f"  - {key}: type={type(val)}, value={val if isinstance(val, (str, int, float, bool, type(None))) else f'[{type(val).__name__}]'}")
                                        
                                        # Create initial state or update existing one
                                        if current_state_uid is None:
                                            # Create the initial state record
                                            state_record = crud.create_state(db, user_message_id, state_fields)
                                            current_state_uid = state_record.uid
                                            print(f"[WebSocket] Created initial state: {current_state_uid}")
                                        else:
                                            # Update the existing state record
                                            state_record = crud.update_state(db, current_state_uid, state_fields)
                                            print(f"[WebSocket] Updated existing state: {current_state_uid}")
                                        
                                        # Log successful state save for important fields
                                        if any(f in state_fields for f in ["all_paths", "chosen_path", "tool_metadata"]):
                                            print(f"[WebSocket] Saved state with paths/metadata: {[k for k in state_fields.keys() if k in ['all_paths', 'chosen_path', 'tool_metadata']]}")
                                        
                                        # Send state checkpoint to frontend (schedule on main loop)
                                        asyncio.run_coroutine_threadsafe(
                                            websocket.send_json({
                                                "type": "state_checkpoint",
                                                "node": node,
                                                "state_uid": current_state_uid,
                                                "fields": event_data.get("fields", list(sanitized_update.keys())),
                                                "timestamp": event_dict.get("timestamp")
                                            }),
                                            loop
                                        )
                                    except Exception as e:
                                        print(f"Error saving state checkpoint: {e}")
                                
                                last_node = node
                        
                        # Add frontend message ID to all events for proper tracking
                        if frontend_message_id:
                            if isinstance(event_dict, dict):
                                event_dict["frontend_message_id"] = frontend_message_id
                        
                        # Forward event to client via queue (thread-safe)
                        try:
                            asyncio.run_coroutine_threadsafe(event_queue.put(event_dict), loop)
                        except RuntimeError:
                            print("enhanced_stream_callback: no running loop; dropping event")
                    
                    # Create user message first to get message_id
                    # Store original content; use annotated content only for orchestrator
                    original_content = content
                    orchestrator_content = content
                    if file_paths:
                        try:
                            refs = _paths_to_references(file_paths)
                            files_text = "\n".join(refs)
                            orchestrator_content = f"{content}\n\n<files>\n{files_text}\n</files>"
                        except Exception:
                            pass

                    user_message = crud.create_message(
                        db,
                        conversation_id=conversation_id,
                        role="user",
                        content=original_content,
                        reasoning={
                            "additional_kwargs": {
                                "file_references": _paths_to_references(file_paths) if file_paths else []
                            }
                        } if file_paths else None
                    )
                    user_message_id = user_message.id
                    # Set env for isolated execution to route outputs/logs
                    try:
                        import os as _os
                        _os.environ["GENESIS_CONVERSATION_ID"] = conversation_id
                        _os.environ["GENESIS_MESSAGE_ID"] = str(user_message_id)
                    except Exception:
                        pass
                    
                    # Create streaming context
                    with StreamingContext(enhanced_stream_callback):
                        # Get message history (excluding the one we just created)
                        messages = crud.get_messages(db, conversation_id)
                        message_history = [
                            {"role": msg.role, "content": msg.content}
                            for msg in messages[:-1]  # Exclude the message we just added
                        ]
                        
                        # Process through orchestrator
                        result = await orchestrator_service.process_message(
                            conversation_id=conversation_id,
                            user_input=orchestrator_content,
                            message_history=message_history
                        )
                        
                        # Extract response and create assistant message
                        response_text = orchestrator_service.get_response_from_result(result)
                        
                        # Get the final state (should be the updated state from the last node)
                        if current_state_uid:
                            final_state = crud.get_state(db, current_state_uid)
                        else:
                            # Fallback: create final state if no state was created during processing
                            final_state_data = orchestrator_service.extract_state_data(result)
                            final_state = crud.create_state(db, user_message_id, final_state_data)
                            current_state_uid = final_state.uid
                        
                        # Debug final state data
                        print(f"\n[WebSocket Debug] Final state:")
                        print(f"  - state_uid: {current_state_uid}")
                        print(f"  - node: {final_state.node}")
                        print(f"  - next_node: {final_state.next_node}")
                        print(f"  - all_paths: {final_state.all_paths is not None}")
                        print(f"  - chosen_path: {final_state.chosen_path is not None}")
                        print(f"  - tool_metadata: {final_state.tool_metadata is not None}")
                        
                        # Prepare reasoning data for storage (use explicit reasoning events only)
                        reasoning_data = None
                        if reasoning_content:
                            # Sum provided think_time (seconds) if available; fallback to 0
                            total_think_s = sum([e.get("think_time_seconds") or 0 for e in reasoning_content])
                            # combined_reasoning = "\n\n".join([
                            #     f"**{entry['node']}:**\n{entry['content']}" 
                            #     for entry in reasoning_content
                            # ])
                            reasoning_data = {
                                "content": reasoning_content,
                                "thinking_time": total_think_s,  # seconds
                                "thinking_time_seconds": total_think_s,
                                "is_expanded": False,
                                "is_thinking": False,
                                "additional_kwargs": {
                                    "reasoning_content": reasoning_content,
                                    "node_breakdown": reasoning_content
                                }
                            }
                        
                        # Create assistant message linked to final state
                        assistant_message = crud.create_message(
                            db,
                            conversation_id=conversation_id,
                            role="assistant",
                            content=response_text,
                            reasoning=reasoning_data,
                            state_id=current_state_uid
                        )
                        
                        # Send final result with frontend message ID for proper tracking
                        completion_data = {
                            "type": "complete",
                            "result": {
                                "response": response_text,
                                "reasoning": reasoning_data,  # Include the reasoning data
                                "state_uid": current_state_uid,
                                "message_id": assistant_message.id,
                                "has_execution": bool(final_state.execution_instance),
                                "state_summary": {
                                    "paths_found": len(final_state.all_paths or []),
                                    "chosen_path_length": len(final_state.chosen_path or []),
                                    "is_complete": final_state.is_complete or False
                                }
                            }
                        }
                        
                        # Include frontend message ID for proper tracking
                        if frontend_message_id:
                            completion_data["frontend_message_id"] = frontend_message_id
                        
                        await websocket.send_json(completion_data)
                
                elif command == "close":
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
                break
        
        # Cleanup
        sender_task.cancel()
        
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        try:
            from starlette.websockets import WebSocketState
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except Exception as close_error:
            print(f"Error closing WebSocket: {close_error}")
