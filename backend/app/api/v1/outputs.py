"""
Outputs API endpoints: list and stream files from outputs directory.
"""
from typing import List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import mimetypes
import os

from app.config import settings

router = APIRouter()


def _get_outputs_root() -> Path:
    root = settings.genesis_project_root or os.environ.get("GENESIS_PROJECT_ROOT") or ""
    if not root:
        raise HTTPException(status_code=500, detail="GENESIS_PROJECT_ROOT not set")
    outputs = Path(root).resolve() / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    return outputs


@router.get("/{conversation_id}/{message_id}")
async def list_outputs(conversation_id: str, message_id: str):
    """List artifacts under outputs/<conversation_id>/<message_id>."""
    base = _get_outputs_root() / conversation_id / message_id
    if not base.exists():
        return {"files": [], "count": 0}
    files: List[dict] = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            try:
                stat = p.stat()
                mime, _ = mimetypes.guess_type(str(p))
                files.append({
                    "filename": p.name,
                    "path": str(p.relative_to(_get_outputs_root())),
                    "size": stat.st_size,
                    "created_at": stat.st_mtime,
                    "mime_type": mime or "application/octet-stream"
                })
            except Exception:
                pass
    return {"files": files, "count": len(files)}


@router.get("/{conversation_id}/{message_id}/{filename}")
async def get_output_by_parts(conversation_id: str, message_id: str, filename: str):
    """Serve a single file under outputs/<conversation_id>/<message_id>/<filename>."""
    base = _get_outputs_root() / conversation_id / message_id
    abs_path = (base / filename).resolve()
    try:
        abs_path.relative_to(_get_outputs_root())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(str(abs_path), media_type=mime or "application/octet-stream")


@router.get("/file")
async def get_output_file(path: str = Query(..., description="Path relative to outputs/")):
    """Stream a file under outputs/ by relative path. Server validates containment."""
    outputs_root = _get_outputs_root()
    
    # Clean and normalize the incoming path
    print(f"Received path: {path}")
    print(f"Outputs root: {outputs_root}")
    
    incoming_path = Path(path).as_posix()
    abs_path = (outputs_root / incoming_path).resolve()
    
    print(f"Resolved absolute path: {abs_path}")
    print(f"File exists: {abs_path.exists()}")
    print(f"Is file: {abs_path.is_file()}")
    
    # Security check: ensure the resolved path is within outputs_root
    try:
        abs_path.relative_to(outputs_root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path - outside outputs directory")
    
    # Check if file exists
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {incoming_path}")
    
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail=f"Path is not a file: {incoming_path}")
    
    # Determine MIME type and return file
    mime, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(str(abs_path), media_type=mime or "application/octet-stream")



