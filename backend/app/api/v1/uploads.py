"""
Simple uploads endpoint to receive files and return stored paths.
"""
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os

from app.db.database import get_output_dir
from app.services.input_file_manager import InputFileManager

router = APIRouter()


@router.post("/", response_model=dict)
async def upload_files(
    files: List[UploadFile] = File(...),
    conversation_id: str | None = None
):
    """
    Store uploaded files and register them under project-root inputs/<conversation_id>/ via InputFileManager.
    Returns absolute file paths (temp store) and stable references from mapping.json.
    """
    try:
        # Always stage to a per-conversation temp area under project root before registering
        project_root = Path(os.environ.get("GENESIS_PROJECT_ROOT", Path.cwd()))
        staging_root = (project_root / ".staging_uploads").resolve()
        staging_dir = (staging_root / (conversation_id or "_uploads")).resolve()
        staging_dir.mkdir(parents=True, exist_ok=True)

        saved_paths: List[str] = []
        references: List[str] = []
        manager: InputFileManager | None = None
        if conversation_id:
            manager = InputFileManager(conversation_id)
        for f in files:
            # Ensure filename is safe
            name = Path(f.filename or "file").name
            dest = staging_dir / name
            # Avoid overwrite: add suffix if exists (use constant base stem)
            base_stem = Path(name).stem
            suffix = Path(name).suffix
            counter = 1
            while dest.exists():
                dest = staging_dir / f"{base_stem}_{counter}{suffix}"
                counter += 1
            content = await f.read()
            dest.write_bytes(content)
            saved_paths.append(str(dest.resolve()))
            # Register with InputFileManager to get stable reference (preserve original name)
            if manager is not None:
                try:
                    ref = manager.register_file(str(dest.resolve()), preferred_reference=name)
                    references.append(ref)
                except Exception:
                    references.append(name)

        return {"file_paths": saved_paths, "references": references}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}/{filename}")
async def get_uploaded_file(conversation_id: str, filename: str):
    """Serve an uploaded file for preview/download."""
    try:
        # Serve from inputs store (project-root inputs/<conversation_id>/)
        project_root = Path(os.environ.get("GENESIS_PROJECT_ROOT", Path.cwd()))
        inputs_root = Path(os.environ.get("GENESIS_INPUTS_ROOT", project_root / "inputs"))
        base_dir = (inputs_root / conversation_id).resolve()
        file_path = (base_dir / filename).resolve()
        # Prevent path traversal
        try:
            file_path.relative_to(base_dir)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid file path")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path=str(file_path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


