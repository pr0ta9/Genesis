"""
Test harness for PathPanel (Propagation graph + Pipeline list with PathsStore)

What it demonstrates:
- Shared PathsStore injected into PathPanel
- Loading 'all_paths' from a mock state (instant or animated)
- Reducing to a chosen_path (animated)
- Sticky highlight of a path (graph + pipeline)

Run:
  python tests/test_path_panel.py
"""

from __future__ import annotations

import sys
from pathlib import Path
import asyncio
import flet as ft
from typing import Any, Dict, List, Optional

# Make repo import-friendly (adjust if your layout differs)
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.gui.panels.path_panel import PathPanel
from src.gui.stores.paths_store import PathsStore


# --- tiny stubs to mirror orchestrator types expected by PathPanel.update_from_state ---

class _EnumStub:
    """Minimal stand-in for WorkflowTypeEnum with a .value attribute."""
    def __init__(self, value: str):
        self.value = value


class _PathItemStub:
    """Minimal stand-in for PathItem with a .name attribute."""
    def __init__(self, name: str):
        self.name = name


# --------------------------------------------------------------------------------------


class PathPanelHarness:
    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.store = PathsStore()
        self.panel: Optional[PathPanel] = None

        # Top bar refs
        self.load_a_btn: Optional[ft.ElevatedButton] = None
        self.populate_a_btn: Optional[ft.ElevatedButton] = None
        self.reduce_to_dd: Optional[ft.Dropdown] = None
        self.reduce_btn: Optional[ft.ElevatedButton] = None
        self.highlight_dd: Optional[ft.Dropdown] = None
        self.highlight_btn: Optional[ft.ElevatedButton] = None
        self.load_b_btn: Optional[ft.ElevatedButton] = None
        self.populate_b_btn: Optional[ft.ElevatedButton] = None
        self.refresh_btn: Optional[ft.IconButton] = None

        # Cached last loaded "all_paths" so we can build chosen_path easily
        self._last_all_paths: List[List[Dict[str, Any]]] = []
        self._last_state_type: str = "A"  # Track which state was last loaded

    # ---------- Flet entry ----------

    def main(self, page: ft.Page):
        self.page = page
        page.title = "Genesis – PathPanel Tester"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1200
        page.window.height = 860
        page.padding = 0

        # Panel (inject shared store; no bridge needed for the test)
        self.panel = PathPanel(store=self.store, orchestrator_bridge=None, on_path_select=self._on_path_select)
        self.panel.set_page(page)
        panel_ui = self.panel.build()

        # Controls
        self.load_a_btn = ft.ElevatedButton("Load State A (instant)", icon=ft.Icons.DOWNLOAD, on_click=self._load_state_a_instant)
        self.populate_a_btn = ft.ElevatedButton("Populate State A (animate)", icon=ft.Icons.MOVIE, on_click=self._populate_state_a)

        self.load_b_btn = ft.ElevatedButton("Load State B (instant)", icon=ft.Icons.DOWNLOAD, on_click=self._load_state_b_instant)
        self.populate_b_btn = ft.ElevatedButton("Populate State B (animate)", icon=ft.Icons.MOVIE, on_click=self._populate_state_b)

        self.reduce_to_dd = ft.Dropdown(label="Target index (chosen_path)", width=180, options=[ft.dropdown.Option("0"), ft.dropdown.Option("1"), ft.dropdown.Option("2")], value="0")
        self.reduce_btn = ft.ElevatedButton("Reduce to chosen (animate)", icon=ft.Icons.AUTO_AWESOME, on_click=self._reduce_to_chosen)

        self.highlight_dd = ft.Dropdown(label="Path ID (from store)", width=340, options=[], value=None)
        self.highlight_btn = ft.ElevatedButton("Highlight (sticky)", icon=ft.Icons.HIGHLIGHT, on_click=self._highlight_selected)

        self.refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Refresh IDs", on_click=self._refresh_ids)

        top_bar = ft.Container(
            ft.Row(
                [
                    self.load_a_btn,
                    self.populate_a_btn,
                    ft.Container(width=12),
                    self.load_b_btn,
                    self.populate_b_btn,
                    ft.Container(width=24),
                    self.reduce_to_dd,
                    self.reduce_btn,
                    ft.Container(width=24),
                    self.highlight_dd,
                    self.highlight_btn,
                    self.refresh_btn,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.BLACK),
        )

        page.add(top_bar, panel_ui)
        page.update()

        # Initial load (so there is something to see)
        self._load_state_a_instant(None)

    # ---------- Mock states ----------

    def _state_A(self) -> Dict[str, Any]:
        """Simple state with 3 candidate paths."""
        all_paths = [
            [{"name": "ocr"}, {"name": "translate"}],
            [{"name": "detect"}, {"name": "enhance"}, {"name": "summarize"}],
            [{"name": "filter"}],
        ]
        state = {
            "input_type": _EnumStub("imagefile"),
            "type_savepoint": [_EnumStub("imagefile")],  # saving image output
            "all_paths": all_paths,
            # chosen_path can be added later dynamically
        }
        return state

    def _state_B(self) -> Dict[str, Any]:
        """Another state with different tools & lengths."""
        all_paths = [
            [{"name": "detect"}, {"name": "erase"}, {"name": "overlay"}],
            [{"name": "ocr"}, {"name": "summarize"}],
            [{"name": "enhance"}, {"name": "filter"}, {"name": "translate"}, {"name": "summarize"}],
        ]
        state = {
            "input_type": _EnumStub("imagefile"),
            "type_savepoint": [_EnumStub("text")],  # save as text
            "all_paths": all_paths,
        }
        return state

    # ---------- UI handlers ----------

    def _load_state_a_instant(self, _):
        st = self._state_A()
        self._last_all_paths = st["all_paths"]
        self._last_state_type = "A"
        self.panel.update_from_state(st, animate_population=False, animate_reduce=False)
        self._refresh_ids(None)

    def _populate_state_a(self, _):
        st = self._state_A()
        self._last_all_paths = st["all_paths"]
        self._last_state_type = "A"
        self.panel.update_from_state(st, animate_population=True, animate_reduce=True)
        self._refresh_ids(None)

    def _load_state_b_instant(self, _):
        st = self._state_B()
        self._last_all_paths = st["all_paths"]
        self._last_state_type = "B"
        self.panel.update_from_state(st, animate_population=False, animate_reduce=False)
        self._refresh_ids(None)

    def _populate_state_b(self, _):
        st = self._state_B()
        self._last_all_paths = st["all_paths"]
        self._last_state_type = "B"
        self.panel.update_from_state(st, animate_population=True, animate_reduce=False)
        self._refresh_ids(None)

    def _reduce_to_chosen(self, _):
        """Build chosen_path from the selected index of the currently cached all_paths and animate prune."""
        if not self._last_all_paths:
            return
        idx = int(self.reduce_to_dd.value or "0")
        idx = max(0, min(idx, len(self._last_all_paths) - 1))

        chosen_tools = self._last_all_paths[idx]
        chosen_steps = [_PathItemStub(tool["name"]) for tool in chosen_tools]

        # Use the correct state based on which was last loaded
        if self._last_state_type == "B":
            st = self._state_B()
        else:
            st = self._state_A()
        st["all_paths"] = self._last_all_paths
        st["chosen_path"] = chosen_steps

        self.panel.update_from_state(st, animate_population=False, animate_reduce=True)

    def _highlight_selected(self, _):
        """Sticky highlight by path id from dropdown."""
        pid = self.highlight_dd.value
        if pid:
            self.panel.highlight_path(pid, persist=True)

    def _refresh_ids(self, _):
        """Update dropdown of path IDs from store (after load/populate)."""
        options = []
        for p in self.store.ordered_paths():
            options.append(ft.dropdown.Option(p.id))
        self.highlight_dd.options = options
        # Keep value if still present
        if self.highlight_dd.value not in [o.key for o in options]:
            self.highlight_dd.value = (options[0].key if options else None)
        self.highlight_dd.update()

    def _on_path_select(self, path_id: str):
        print(f"[Harness] on_path_select -> {path_id}")


def main():
    ft.app(target=PathPanelHarness().main)


if __name__ == "__main__":
    main()
