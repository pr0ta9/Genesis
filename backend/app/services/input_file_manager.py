"""
InputFileManager: Maps user-uploaded files to stable references with size-aware storage policy.
"""
from __future__ import annotations

import os
import json
import shutil
import platform
import uuid
from pathlib import Path
from threading import Lock
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List


class FileModifiedError(Exception):
    pass


class SecurityError(Exception):
    pass


class InputFileManager:
    def __init__(self, conversation_id: str, copy_threshold_mb: int | None = None):
        self.conversation_id = conversation_id
        threshold_mb = copy_threshold_mb if copy_threshold_mb is not None else int(os.getenv("FILE_COPY_THRESHOLD_MB", "100"))
        self.copy_threshold = threshold_mb * 1024 * 1024
        inputs_root = os.getenv("GENESIS_INPUTS_ROOT")
        if not inputs_root:
            project_root = os.getenv("GENESIS_PROJECT_ROOT", os.getcwd())
            inputs_root = str(Path(project_root) / "inputs")
        self.inputs_dir = (Path(inputs_root) / conversation_id).resolve()
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_roots: List[Path] = self._get_allowed_roots()
        self.mapping: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._name_counter: Dict[str, int] = defaultdict(int)
        self._load_mapping()

    def _get_allowed_roots(self) -> List[Path]:
        roots_env = os.getenv("ALLOWED_FILE_ROOTS")
        if roots_env:
            return [Path(p).resolve() for p in roots_env.split(os.pathsep) if p]
        if platform.system() == "Windows":
            candidates = [
                Path(os.environ.get('USERPROFILE', str(Path.home())))/'Downloads',
                Path(os.environ.get('USERPROFILE', str(Path.home())))/'Documents',
                Path(os.environ.get('TEMP', 'C:/Windows/Temp')),
            ]
        else:
            candidates = [Path.home(), Path('/tmp')]
        return [p.resolve() for p in candidates]

    def _is_under_allowed_root(self, path: Path) -> bool:
        path = path.resolve()
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return True
            except Exception:
                continue
        return False

    def _normalize_reference(self, reference: str) -> str:
        ref = reference.strip().strip("\"'")
        if platform.system() == "Windows":
            ref = ref.lower()
        return ref

    def _generate_unique_reference(self, basename: str) -> str:
        """Always prefer original basename; add _vN only if already registered."""
        name, ext = os.path.splitext(basename)
        # Use normalized key for collision check (Windows-insensitive)
        key = self._normalize_reference(basename)
        if key not in self.mapping and basename not in self._name_counter:
            self._name_counter[basename] = 1
            return basename
        # Increment version until unused reference is found
        version = self._name_counter.get(basename, 1)
        while True:
            version += 1
            candidate = f"{name}_v{version}{ext}"
            if self._normalize_reference(candidate) not in self.mapping:
                self._name_counter[basename] = version
                return candidate

    def _get_fingerprint(self, path: Path) -> Dict[str, Any]:
        try:
            stat = path.stat()
            return {"size": stat.st_size, "mtime": int(stat.st_mtime)}
        except Exception:
            return {"size": None, "mtime": None}

    def register_file(self, original_path: str, preferred_reference: str | None = None) -> str:
        with self._lock:
            src = Path(original_path).resolve()
            if not src.exists() or not src.is_file():
                raise FileNotFoundError(str(src))
            if not self._is_under_allowed_root(src):
                raise SecurityError(f"File outside allowed directories: {src}")

            # Use preferred reference name if provided (e.g., original upload name),
            # only adding _vN when mapping already contains that name
            base_name = Path(preferred_reference).name if preferred_reference else src.name
            reference = self._generate_unique_reference(base_name)
            target = (self.inputs_dir / reference).resolve()
            size = src.stat().st_size

            # storage method
            method = "reference"
            if size <= self.copy_threshold:
                try:
                    os.link(str(src), str(target))
                    method = "hardlink"
                except Exception:
                    shutil.copy2(src, target)
                    method = "copy"
            else:
                try:
                    os.link(str(src), str(target))
                    method = "hardlink"
                except Exception:
                    method = "reference"
                    target = src

            entry = {
                "reference": reference,
                "method": method,
                "path": str(target),
                "original": str(src),
                "fingerprint": self._get_fingerprint(src),
                "uuid": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(),
            }
            self.mapping[self._normalize_reference(reference)] = entry
            self._save_mapping()
            return reference

    def resolve(self, reference: str, verify: bool = True) -> str | None:
        entry = self.mapping.get(self._normalize_reference(reference))
        if not entry:
            return None
        path = Path(entry["path"]).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {reference}")
        if verify and entry["method"] == "reference":
            if self._get_fingerprint(path) != entry.get("fingerprint"):
                raise FileModifiedError(f"File '{reference}' modified since registration")
        return str(path)

    def _save_mapping(self) -> None:
        fpath = self.inputs_dir / "mapping.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(self.mapping, f, indent=2)

    def _load_mapping(self) -> None:
        fpath = self.inputs_dir / "mapping.json"
        if fpath.exists():
            try:
                self.mapping = json.load(open(fpath, "r", encoding="utf-8"))
            except Exception:
                self.mapping = {}


