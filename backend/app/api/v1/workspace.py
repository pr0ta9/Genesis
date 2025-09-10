"""
Workspace API endpoints - stub implementation.
"""
from typing import List
from fastapi import APIRouter
from pathlib import Path
import os

from app.models.responses import WorkspaceInfoResponse
from app.config import settings

router = APIRouter()


@router.get("/", response_model=WorkspaceInfoResponse)
async def get_workspace_info():
    """Get workspace information including tmp directories."""
    project_root = Path(settings.genesis_project_root)
    tmp_root = project_root / "tmp"
    output_root = Path(os.environ.get('APPDATA', '')) / 'Genesis' / 'outputs' if os.name == 'nt' else Path.home() / '.genesis' / 'outputs'
    
    # TODO: Implement actual directory scanning
    return WorkspaceInfoResponse(
        project_root=str(project_root),
        tmp_root=str(tmp_root),
        output_root=str(output_root),
        tmp_directories=[],
        total_tmp_dirs=0,
        tmp_space_used=0,
        output_space_used=0
    )


@router.delete("/")
async def cleanup_workspace():
    """Clean all tmp directories."""
    # TODO: Implement cleanup
    return {"status": "cleanup_not_implemented"}


@router.delete("/{dir_name}")
async def cleanup_specific_directory(dir_name: str):
    """Clean specific tmp directory."""
    # TODO: Implement cleanup
    return {"status": "cleanup_not_implemented", "directory": dir_name}
