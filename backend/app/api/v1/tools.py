"""
Tools API endpoints: serve canonical tool source code from src/tools/path_tools.
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import os

from app.config import settings

router = APIRouter()


@router.get("/source/{tool_name}")
async def get_tool_source(tool_name: str):
    """Return the source code for a registered path tool (read-only)."""
    root = settings.genesis_project_root or os.environ.get("GENESIS_PROJECT_ROOT") or ""
    if not root:
        raise HTTPException(status_code=500, detail="GENESIS_PROJECT_ROOT not set")
    # Allow-list directory
    tools_dir = Path(root).resolve() / "src" / "tools" / "path_tools"
    path = tools_dir / f"{tool_name}.py"
    if not path.exists() or not path.is_file():
        # Fallback: scan for file that defines the function name (e.g., image_ocr in ocr.py)
        found = None
        try:
            for py_file in tools_dir.glob("*.py"):
                try:
                    text = py_file.read_text(encoding="utf-8")
                except Exception:
                    continue
                needle = f"def {tool_name}("
                if needle in text:
                    found = py_file
                    break
        except Exception:
            found = None
        if not found:
            raise HTTPException(status_code=404, detail="Tool not found")
        path = found
    try:
        content = path.read_text(encoding="utf-8")
        return {"tool": tool_name, "path": str(path.relative_to(Path(root).resolve())), "source": content}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read tool source")



