"""
Test harness for ExecutionPanel (Real workspace integration)

What it demonstrates:
- Real ExecutionPanel with initial_sync and workspace event handling
- Loads actual scripts and results from tmp/ directories
- Simulates real orchestrator events and workspace data
- Shows Python scripts, console output, and JSON results

Run:
  python tests/test_execution_panel.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import flet as ft
from typing import Any, Dict, List, Optional
import json
import time

# Make repo import-friendly (adjust if your layout differs)
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.gui.panels.execution_panel import ExecutionPanel
from src.gui.stores.execution_store import ExecutionStore


class ExecutionPanelHarness:
    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.store = ExecutionStore()
        self.panel: Optional[ExecutionPanel] = None
        
        # Use real tmp directories for testing
        self.available_workspaces = [
            "genesis_image_ocr_q4yq787f",
            "genesis_erase_w9i9mdnp", 
            "genesis_inpaint_text_5h325c6v",
            "genesis_translate_5bpzi54s",
        ]
        self.current_workspace = self.available_workspaces[0]
        
        # Top bar controls
        self.workspace_dropdown: Optional[ft.Dropdown] = None
        self.load_workspace_btn: Optional[ft.ElevatedButton] = None
        self.simulate_created_btn: Optional[ft.ElevatedButton] = None
        self.simulate_start_btn: Optional[ft.ElevatedButton] = None
        self.simulate_complete_btn: Optional[ft.ElevatedButton] = None
        self.clear_btn: Optional[ft.ElevatedButton] = None

    def main(self, page: ft.Page):
        self.page = page
        page.title = "Genesis – ExecutionPanel Tester (Real Workspace)"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1400
        page.window.height = 900
        page.padding = 0

        # Panel: inject shared store
        self.panel = ExecutionPanel(store=self.store)
        self.panel.set_page(page)
        panel_ui = self.panel.build()

        # Top bar controls
        self.workspace_dropdown = ft.Dropdown(
            label="Workspace",
            width=220,
            options=[ft.dropdown.Option(ws) for ws in self.available_workspaces],
            value=self.current_workspace,
            on_change=self._on_workspace_selected
        )
        
        self.load_workspace_btn = ft.ElevatedButton(
            "Load Workspace Data",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self._load_workspace_data
        )
        
        self.simulate_created_btn = ft.ElevatedButton(
            "Simulate 'created' Event",
            icon=ft.Icons.CREATE_NEW_FOLDER,
            on_click=self._simulate_created_event
        )
        
        self.simulate_start_btn = ft.ElevatedButton(
            "Simulate 'execution_start'",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._simulate_start_event
        )
        
        self.simulate_complete_btn = ft.ElevatedButton(
            "Simulate 'execution_complete'",
            icon=ft.Icons.CHECK_CIRCLE,
            on_click=self._simulate_complete_event
        )
        
        self.clear_btn = ft.ElevatedButton(
            "Clear Panel",
            icon=ft.Icons.CLEAR,
            on_click=self._clear_panel
        )
        
        self.animate_btn = ft.ElevatedButton(
            "Animate Code",
            icon=ft.Icons.ANIMATION,
            on_click=self._animate_code
        )

        # Layout controls
        top_row = ft.Row([
            self.workspace_dropdown,
            self.load_workspace_btn,
            ft.Container(width=16),
            self.simulate_created_btn,
            self.simulate_start_btn,
            self.simulate_complete_btn,
            ft.Container(width=16),
            self.animate_btn,
            self.clear_btn,
        ], alignment=ft.MainAxisAlignment.START)

        top_bar = ft.Container(
            top_row,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.BLACK),
        )

        page.add(top_bar, panel_ui)
        page.update()

        # Load initial workspace
        self._load_workspace_data(None)

    # ---------- Event handlers ----------

    def _on_workspace_selected(self, e: ft.ControlEvent):
        """Handle workspace selection from dropdown."""
        self.current_workspace = e.control.value
        self._load_workspace_data(None)

    def _load_workspace_data(self, _):
        """Load real workspace data and display using initial_sync."""
        workspace_dir = project_root / "tmp" / self.current_workspace
        
        if not workspace_dir.exists():
            self._show_error(f"Workspace not found: {workspace_dir}")
            return
        
        # Load Python script
        code_lines = []
        python_files = list(workspace_dir.glob("run_*.py"))
        if python_files:
            script_path = python_files[0]
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    code_lines = f.read().splitlines()
            except Exception as e:
                code_lines = [f"# Error loading {script_path.name}: {e}"]
        else:
            code_lines = ["# No run_*.py script found in workspace"]
        
        # Load execution state for results and create realistic artifacts
        artifacts = []
        state_file = workspace_dir / "execution_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                
                # Convert to artifacts with real images and data
                for key, value in state_data.items():
                    if key.endswith('.return'):
                        tool_name = key.replace('.return', '')
                        
                        # Add JSON results
                        artifacts.append({
                            "kind": "json",
                            "text": json.dumps(value, indent=2, ensure_ascii=False),
                            "meta": {
                                "description": f"{tool_name} execution results",
                                "tool": tool_name,
                                "workspace": self.current_workspace
                            }
                        })
                        
                        # Add sample images based on tool type
                        if tool_name == "image_ocr":
                            artifacts.extend([
                                {
                                    "kind": "image",
                                    "path": str(project_root / "test.png"),
                                    "mime": "image/png",
                                    "meta": {
                                        "description": "Original input image",
                                        "role": "input"
                                    }
                                },
                                {
                                    "kind": "image", 
                                    "path": str(project_root / "test_clean.png"),
                                    "mime": "image/png",
                                    "meta": {
                                        "description": "Cleaned image (text detection overlay)",
                                        "role": "output"
                                    }
                                }
                            ])
                        elif tool_name == "translate":
                            # Add translation results
                            artifacts.append({
                                "kind": "text",
                                "text": "Translation Results:\n- うん そうだなあ… 優しいよね → Yeah, that's right... He's kind, isn't he?\n- ねえねえ、めいは坂本のこと どう思う? → Hey, hey, what do you think about Sakamoto?",
                                "meta": {
                                    "description": "Human-readable translation",
                                    "tool": "translate"
                                }
                            })
                        elif tool_name in ["erase", "inpaint_text"]:
                            artifacts.extend([
                                {
                                    "kind": "image",
                                    "path": str(project_root / "test.png"),
                                    "mime": "image/png", 
                                    "meta": {"description": "Original image", "role": "input"}
                                },
                                {
                                    "kind": "image",
                                    "path": str(project_root / "test_translated.png"), 
                                    "mime": "image/png",
                                    "meta": {"description": "Processed image", "role": "output"}
                                }
                            ])
                            
            except Exception as e:
                # Add error as artifact
                artifacts.append({
                    "kind": "text",
                    "text": f"Error loading execution state: {e}",
                    "meta": {"description": "Load error"}
                })
        
        # Create console lines
        console_lines = [
            f"[system] Loading workspace: {self.current_workspace}",
            f"[info] Found {len(python_files)} Python scripts",
            f"[info] Found {len(artifacts)} result artifacts",
        ]
        
        if python_files:
            console_lines.append(f"[debug] Script: {python_files[0].name}")
        if state_file.exists():
            console_lines.append(f"[debug] State file: {state_file.stat().st_size} bytes")
        
        # Tool name from workspace directory
        tool_name = self.current_workspace.split('_')[1] if '_' in self.current_workspace else "unknown"
        
        # Create snapshot and sync
        snapshot = {
            "code_lines": code_lines,
            "console_lines": console_lines,
            "artifacts": artifacts,
            "selected_node": tool_name,
            "current_node": tool_name,
            "workspace_dir": str(workspace_dir),
            "tool_name": tool_name,
        }
        
        self.panel.initial_sync(snapshot)

    def _simulate_created_event(self, _):
        """Simulate workspace 'created' event."""
        workspace_dir = project_root / "tmp" / self.current_workspace
        tool_name = self.current_workspace.split('_')[1] if '_' in self.current_workspace else "unknown"
        
        event = {
            "event": "created",
            "timestamp": f"{time.strftime('%Y-%m-%dT%H:%M:%S')}.123Z",
            "data": {
                "tool_name": tool_name,
                "workspace_dir": str(workspace_dir),
                "status": f"Created workspace: {self.current_workspace}",
                "node": tool_name,
                "isolated": True
            },
            "workspace_info": {
                "project_root": str(project_root),
                "tmp_root": str(project_root / "tmp"),
                "tmp_directories": [{"name": self.current_workspace, "tool_type": tool_name}],
                "total_tmp_dirs": 1
            }
        }
        
        self.panel.handle_workspace_event(event)

    def _simulate_start_event(self, _):
        """Simulate execution_start event."""
        workspace_dir = project_root / "tmp" / self.current_workspace
        tool_name = self.current_workspace.split('_')[1] if '_' in self.current_workspace else "unknown"
        
        event = {
            "event": "execution_start",
            "timestamp": f"{time.strftime('%Y-%m-%dT%H:%M:%S')}.123Z",
            "data": {
                "tool_name": tool_name,
                "workspace_dir": str(workspace_dir),
                "status": f"Starting {tool_name} execution...",
                "node": tool_name,
                "isolated": True
            },
            "workspace_info": {}
        }
        
        self.panel.handle_workspace_event(event)

    def _simulate_complete_event(self, _):
        """Simulate execution_complete event with full artifacts."""
        workspace_dir = project_root / "tmp" / self.current_workspace
        tool_name = self.current_workspace.split('_')[1] if '_' in self.current_workspace else "unknown"
        
        # First send the event
        event = {
            "event": "execution_complete",
            "timestamp": f"{time.strftime('%Y-%m-%dT%H:%M:%S')}.123Z",
            "data": {
                "tool_name": tool_name,
                "workspace_dir": str(workspace_dir),
                "status": f"{tool_name} execution completed successfully ✓",
                "node": tool_name,
                "isolated": True
            },
            "workspace_info": {}
        }
        
        self.panel.handle_workspace_event(event)
        
        # Now simulate complete results by directly setting artifacts (what the real system would do)
        # This is what the test environment needs to provide
        self._load_complete_artifacts_for_tool(tool_name)
    
    def _load_complete_artifacts_for_tool(self, tool_name: str):
        """Load complete artifacts for the specified tool (test environment responsibility)."""
        artifacts = []
        
        # Load base execution results from actual workspace
        workspace_dir = project_root / "tmp" / self.current_workspace
        state_file = workspace_dir / "execution_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                
                # Add JSON results
                for key, value in state_data.items():
                    if key.endswith('.return'):
                        function_name = key.replace('.return', '')
                        artifacts.append({
                            "kind": "json",
                            "text": json.dumps(value, indent=2, ensure_ascii=False),
                            "meta": {
                                "description": f"{function_name} execution results",
                                "tool": function_name,
                                "workspace": self.current_workspace
                            }
                        })
            except Exception as e:
                print(f"Error loading execution state: {e}")
        
        # Add tool-specific artifacts (test environment's job to define these)
        if tool_name == "image_ocr":
            artifacts.extend([
                {
                    "kind": "image",
                    "path": str(project_root / "test.png"),
                    "mime": "image/png",
                    "meta": {"description": "Original input image", "role": "input"}
                },
                {
                    "kind": "image", 
                    "path": str(project_root / "test_clean.png"),
                    "mime": "image/png",
                    "meta": {"description": "Cleaned image (text detection overlay)", "role": "output"}
                }
            ])
        elif tool_name == "translate":
            artifacts.extend([
                {
                    "kind": "text",
                    "text": "Translation Results:\n- うん そうだなあ… 優しいよね → Yeah, that's right... He's kind, isn't he?\n- ねえねえ、めいは坂本のこと どう思う? → Hey, hey, what do you think about Sakamoto?",
                    "meta": {"description": "Human-readable translation", "tool": "translate"}
                },
                {
                    "kind": "image",
                    "path": str(project_root / "test.png"),
                    "mime": "image/png",
                    "meta": {"description": "Original image", "role": "input"}
                },
                {
                    "kind": "image",
                    "path": str(project_root / "test_translated.png"),
                    "mime": "image/png",
                    "meta": {"description": "Processed image", "role": "output"}
                }
            ])
        elif tool_name in ["erase", "inpaint_text"]:
            artifacts.extend([
                {
                    "kind": "image",
                    "path": str(project_root / "test.png"),
                    "mime": "image/png", 
                    "meta": {"description": "Original image", "role": "input"}
                },
                {
                    "kind": "image",
                    "path": str(project_root / "test_translated.png"), 
                    "mime": "image/png",
                    "meta": {"description": "Processed image", "role": "output"}
                }
            ])
        
        # Directly set the complete artifact set (bypassing the generic loader)
        if hasattr(self.panel.preview, 'set_artifacts'):
            self.panel.preview.set_artifacts(artifacts)
        self.panel.console.append(f"[system] Loaded {len(artifacts)} complete result artifacts", level="info")

    def _animate_code(self, _):
        """Trigger code animation."""
        self.panel.animate_current_script()

    def _clear_panel(self, _):
        """Clear the panel."""
        self.panel.codeblock.clear()
        self.panel.console.clear()
        # Clear preview if possible
        if hasattr(self.panel.preview, 'clear'):
            self.panel.preview.clear()

    def _show_error(self, message: str):
        """Show error in console."""
        self.panel.console.clear()
        self.panel.console.append(f"[error] {message}", level="error")


def main():
    ft.app(target=ExecutionPanelHarness().main)


if __name__ == "__main__":
    main()