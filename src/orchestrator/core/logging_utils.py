import logging
import json
from typing import Any, Iterable, List, Dict, Union
from pathlib import Path
import os
import re
from typing import Callable


_LOGGER_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once with a clean, readable format."""
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Tame noisy third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langgraph").setLevel(logging.WARNING)

    _LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the project format."""
    configure_logging()
    return logging.getLogger(name)


def _to_serializable(obj: Any) -> Any:
    """Best-effort conversion of complex objects to JSON-serializable structures."""
    # Lazy imports to avoid hard dependencies at import time
    try:
        from pydantic import BaseModel  # type: ignore
    except Exception:  # pragma: no cover - optional
        BaseModel = None  # type: ignore
    try:
        from langchain_core.messages import BaseMessage  # type: ignore
    except Exception:  # pragma: no cover - optional
        BaseMessage = None  # type: ignore

    # None or primitives
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Enums
    try:
        import enum
        if isinstance(obj, enum.Enum):
            return getattr(obj, "value", str(obj))
    except Exception:
        pass

    # Pydantic models
    if BaseModel is not None and isinstance(obj, BaseModel):  # type: ignore
        try:
            return obj.model_dump()
        except Exception:
            try:
                return obj.dict()  # legacy
            except Exception:
                return str(obj)

    # LangChain messages
    if BaseMessage is not None and isinstance(obj, BaseMessage):  # type: ignore
        return {
            "type": obj.__class__.__name__,
            "content": getattr(obj, "content", None),
            "metadata": getattr(obj, "response_metadata", None) or getattr(obj, "additional_kwargs", None),
        }

    # dict
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in obj.items()}

    # list/tuple/set
    if isinstance(obj, (list, tuple, set)):
        return [_to_serializable(v) for v in obj]

    # Objects with to_dict
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        try:
            return _to_serializable(obj.to_dict())
        except Exception:
            return str(obj)

    # Dataclasses
    try:
        import dataclasses
        if dataclasses.is_dataclass(obj):
            return _to_serializable(dataclasses.asdict(obj))
    except Exception:
        pass

    # Fallback string representation
    return str(obj)


def pretty(obj: Any, indent: int = 2, ensure_ascii: bool = False) -> str:
    """Pretty-format any object as JSON if possible, otherwise use repr."""
    serializable = _to_serializable(obj)
    try:
        return json.dumps(serializable, indent=indent, ensure_ascii=ensure_ascii)
    except Exception:
        # As an ultimate fallback
        try:
            from pprint import pformat
            return pformat(serializable, indent=indent, width=100)
        except Exception:
            return repr(serializable)


def format_messages(messages: Iterable[Any]) -> str:
    """Render a list of LangChain messages in a human-friendly way."""
    lines: List[str] = []
    for idx, m in enumerate(messages):
        try:
            role = m.__class__.__name__.replace("Message", "")
            content = getattr(m, "content", None)
            
            # Handle content blocks format
            if isinstance(content, list):
                # Content is a list of content blocks
                content_summary = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "unknown")
                        if block_type == "text":
                            text_preview = block.get("text", "")
                            if len(text_preview) > 100:
                                text_preview = text_preview[:100] + "..."
                            content_summary.append(f"[text: {text_preview}]")
                        elif block_type == "reasoning":
                            reasoning_preview = block.get("reasoning", "")
                            if len(reasoning_preview) > 100:
                                reasoning_preview = reasoning_preview[:100] + "..."
                            content_summary.append(f"[reasoning: {reasoning_preview}]")
                        elif block_type == "image":
                            mime = block.get("mime_type", "unknown")
                            content_summary.append(f"[image: {mime}]")
                        elif block_type == "audio":
                            mime = block.get("mime_type", "unknown")
                            content_summary.append(f"[audio: {mime}]")
                        elif block_type == "video":
                            mime = block.get("mime_type", "unknown")
                            content_summary.append(f"[video: {mime}]")
                        elif block_type == "file":
                            mime = block.get("mime_type", "unknown")
                            content_summary.append(f"[file: {mime}]")
                        elif block_type == "text-plain":
                            mime = block.get("mime_type", "text/plain")
                            content_summary.append(f"[text-file: {mime}]")
                        else:
                            content_summary.append(f"[{block_type}]")
                    else:
                        content_summary.append(f"[{type(block).__name__}]")
                content_display = " + ".join(content_summary)
            else:
                # Content is a simple string or other type
                content_display = str(content) if content is not None else "None"
                if len(content_display) > 200:
                    content_display = content_display[:200] + "..."
            
            meta = getattr(m, "response_metadata", None) or getattr(m, "additional_kwargs", None)
            line = f"[{idx}] {role}: {content_display}"
            lines.append(line)
            if meta:
                lines.append(f"    metadata: {pretty(meta)}")
        except Exception:
            lines.append(f"[{idx}] {repr(m)}")
    return "\n".join(lines)


def extract_text_from_content_blocks(content: Union[str, List[Dict], Any]) -> str:
    """
    Extract text content from LangChain content blocks or return string content as-is.
    
    Args:
        content: Either a string or list of content blocks
        
    Returns:
        Extracted text content
    """
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "reasoning":
                    # Include reasoning as part of the text for debugging/display
                    reasoning = block.get("reasoning", "")
                    if reasoning:
                        text_parts.append(f"[Reasoning: {reasoning}]")
                elif block_type == "text-plain":
                    text_parts.append(block.get("text", ""))
                # Skip other block types (image, audio, etc.) for text extraction
        return "\n".join(text_parts)
    
    # Fallback for other types
    return str(content) if content is not None else ""


def log_section(logger: logging.Logger, title: str, obj: Any | None = None, level: int = logging.INFO) -> None:
    """Emit a titled, pretty-printed section for structured objects.

    Example output:
    --- classify result ---
    { ... pretty json ... }
    -----------------------
    """
    divider = "-" * max(20, len(title) + 8)
    logger.log(level, "--- %s ---", title)
    if obj is not None:
        logger.log(level, "%s\n%s", divider, pretty(obj))
        logger.log(level, "%s", divider)
    else:
        logger.log(level, "%s", divider)



def _get_project_root() -> Path:
    """Resolve project root from env or current working directory."""
    root = os.environ.get("GENESIS_PROJECT_ROOT") or os.getcwd()
    return Path(root).resolve()


def _sanitize_component(name: str) -> str:
    """Make a safe filename component (keep alnum, dash, underscore)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "step")
    return safe.strip("._-") or "step"


def build_step_file_prefix(
    chat_id: str,
    message_id: str | int,
    step_index: int,
    tool_name: str,
) -> Path:
    """
    Build outputs path prefix for a step's artifacts.

    Example: <root>/outputs/<chat_id>/<message_id>/01_image_ocr
    """
    conv = _sanitize_component(str(chat_id))
    msg = _sanitize_component(str(message_id))
    step = int(step_index) if step_index is not None else 0
    tool = _sanitize_component(tool_name)

    outputs_dir = _get_project_root() / "outputs" / conv / msg
    outputs_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{step:02d}_{tool}"
    return outputs_dir / filename


def open_log_writers(prefix: Path):
    """
    Open stdout/stderr log files for a given prefix and return
    (stdout_path, stderr_path, stdout_file, stderr_file).
    """
    prefix.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = prefix.with_name(f"{prefix.name}_stdout.log")
    stderr_path = prefix.with_name(f"{prefix.name}_stderr.log")
    stdout_file = open(stdout_path, "a", encoding="utf-8", buffering=1)
    stderr_file = open(stderr_path, "a", encoding="utf-8", buffering=1)
    return stdout_path, stderr_path, stdout_file, stderr_file
