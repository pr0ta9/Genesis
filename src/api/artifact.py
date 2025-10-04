"""
Artifacts API

Endpoints:
- POST /artifacts/{chat_id}/upload  → Upload files into inputs/<chat_id>
- GET  /artifacts/{chat_id}         → List all files under outputs/<chat_id>
"""
from typing import List, Dict
from pathlib import Path
import mimetypes
import os

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _project_root() -> Path:
    root = os.environ.get("GENESIS_PROJECT_ROOT") or os.getcwd()
    return Path(root).resolve()


def _inputs_root() -> Path:
    return Path(os.environ.get("GENESIS_INPUTS_ROOT", _project_root() / "inputs")).resolve()


def _outputs_root() -> Path:
    return Path(os.environ.get("GENESIS_OUTPUTS_ROOT", _project_root() / "outputs")).resolve()


@router.post("/{chat_id}/upload")
async def upload_artifacts(chat_id: str, files: List[UploadFile] = File(...)) -> Dict:
    """Upload files into inputs/<chat_id> and return stored metadata."""
    try:
        base_dir = (_inputs_root() / chat_id).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        saved: List[Dict] = []
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
            dest.write_bytes(content)
            size = dest.stat().st_size
            mime, _ = mimetypes.guess_type(str(dest))
            saved.append({
                "filename": dest.name,
                "path": str(dest),
                "relative_path": str(dest.relative_to(_inputs_root())),
                "size": size,
                "mime_type": mime or "application/octet-stream",
            })

        return {"files": saved, "count": len(saved)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chat_id}")
async def list_output_artifacts(chat_id: str) -> Dict:
    """List all files under outputs/<chat_id> recursively with metadata."""
    base = (_outputs_root() / chat_id).resolve()
    if not base.exists():
        return {"files": [], "count": 0}

    files: List[Dict] = []
    try:
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            stat = p.stat()
            mime, _ = mimetypes.guess_type(str(p))
            files.append({
                "filename": p.name,
                "path": str(p),
                "relative_path": str(p.relative_to(_outputs_root())),
                "size": stat.st_size,
                "created_at": stat.st_mtime,
                "mime_type": mime or "application/octet-stream",
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"files": files, "count": len(files)}


@router.get("/{chat_id}/file/{filename}")
async def serve_uploaded_file(chat_id: str, filename: str):
    """Serve an uploaded file from inputs/<chat_id>/<filename>."""
    try:
        file_path = (_inputs_root() / chat_id / filename).resolve()
        
        # Security: ensure the resolved path is within the inputs directory
        inputs_root = _inputs_root().resolve()
        if not str(file_path).startswith(str(inputs_root)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Not a file")
        
        # Determine media type
        media_type, _ = mimetypes.guess_type(str(file_path))
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type or "application/octet-stream",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outputs/file")
async def serve_output_file(path: str):
    """Serve an output file from outputs/<path> (e.g., chat_id/msg_id/file.png or chat_id/msg_id/logs/stdout.log)."""
    try:
        file_path = (_outputs_root() / path).resolve()
        
        # Security: ensure the resolved path is within the outputs directory
        outputs_root = _outputs_root().resolve()
        if not str(file_path).startswith(str(outputs_root)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Not a file")
        
        # Determine media type
        media_type, _ = mimetypes.guess_type(str(file_path))
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type or "application/octet-stream",
            filename=file_path.name
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/source/{tool_name}")
async def get_tool_source(tool_name: str):
    """Return the source code for a registered path tool."""
    try:
        project_root = _project_root()
        tools_dir = project_root / "src" / "orchestrator" / "tools" / "path_tools"
        
        # Try direct file match first
        tool_file = tools_dir / f"{tool_name}.py"
        
        if not tool_file.exists():
            # Fallback: scan for file that defines the function
            found = None
            for py_file in tools_dir.glob("*.py"):
                try:
                    text = py_file.read_text(encoding="utf-8")
                    if f"def {tool_name}(" in text:
                        found = py_file
                        break
                except Exception:
                    continue
            
            if not found:
                raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
            
            tool_file = found
        
        # Read and return source code
        source = tool_file.read_text(encoding="utf-8")
        relative_path = tool_file.relative_to(project_root)
        
        return {
            "tool": tool_name,
            "path": str(relative_path),
            "source": source
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tool source: {str(e)}")


