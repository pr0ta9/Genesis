"""
Test harness for Genesis App - Complete UI testing
Tests stage transitions, panel integration, and orchestrator bridge functionality
"""

import flet as ft
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum
import json

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.gui.panels.chat_panel import ChatPanel
from src.gui.panels.path_panel import PathPanel
from src.gui.panels.execution_panel import ExecutionPanel
from src.gui.app import GenesisApp
from src.gui.services.orchestrator_bridge import OrchestratorBridge, Stage


class MockOrchestrator:
    """Mock orchestrator for testing"""
    
    def __init__(self):
        self.state = {
            "stage": "start",
            "thread_id": "test_thread_123",
            "available_paths": [
                {"name": "image_ocr", "description": "Extract text from images"},
                {"name": "erase", "description": "Remove objects from images"},
                {"name": "inpaint_text", "description": "Fill in missing text"},
                {"name": "translate", "description": "Translate text content"}
            ],
            "chosen_path": None,
            "execution_results": {}
        }
    
    async def send_message(self, message: str) -> Dict[str, Any]:
        """Mock message sending"""
        await asyncio.sleep(0.1)  # Simulate network delay
        
        if "find path" in message.lower():
            self.state["stage"] = "find_path"
            return {"response": "I found several paths for your request. Please select one."}
        elif "execute" in message.lower():
            self.state["stage"] = "execute"
            self.state["chosen_path"] = [
                {"name": "image_ocr", "tool": "image_ocr"},
                {"name": "translate", "tool": "translate"}
            ]
            return {"response": "Executing the selected path..."}
        else:
            return {"response": f"I received your message: {message}"}


class MockOrchestratorBridge(OrchestratorBridge):
    """Mock orchestrator bridge for testing"""
    
    def __init__(self, orchestrator: MockOrchestrator):
        self.orchestrator = orchestrator
        self._current_state = orchestrator.state.copy()
        self.on_state_change = None
        self.on_stage_change = None
        self.on_workspace_update = None
    
    @property
    def current_state(self) -> Dict[str, Any]:
        return self._current_state
    
    async def send_message(self, message: str) -> Dict[str, Any]:
        """Send message through mock orchestrator"""
        result = await self.orchestrator.send_message(message)
        
        # Update state and trigger callbacks
        old_stage = self._current_state.get("stage")
        self._current_state.update(self.orchestrator.state)
        new_stage = self._current_state.get("stage")
        
        # Trigger state change callback
        if self.on_state_change:
            try:
                self.on_state_change(self._current_state)
            except Exception as e:
                print(f"Error in state change callback: {e}")
        
        # Trigger stage change callback if stage changed
        if old_stage != new_stage and self.on_stage_change:
            try:
                stage_enum = Stage(new_stage) if hasattr(Stage, new_stage.upper()) else Stage.START
                self.on_stage_change(stage_enum)
            except Exception as e:
                print(f"Error in stage change callback: {e}")
        
        return result
    
    def simulate_workspace_event(self, event_type: str, data: Dict[str, Any]):
        """Simulate a workspace event for testing"""
        if self.on_workspace_update:
            payload = {
                "event": event_type,
                "timestamp": "2024-01-15T10:30:45.123Z",
                "data": data,
                "workspace_info": {
                    "project_root": "/path/to/Genesis",
                    "tmp_root": "/path/to/Genesis/tmp",
                    "tmp_directories": [
                        {
                            "name": "genesis_test_abc123",
                            "path": "/full/path/to/genesis_test_abc123",
                            "created": 1705312245.123,
                            "size_bytes": 1024,
                            "tool_type": "test"
                        }
                    ],
                    "total_tmp_dirs": 1,
                    "tmp_space_used": 1024
                }
            }
            try:
                self.on_workspace_update(payload)
            except Exception as e:
                print(f"Error in workspace update callback: {e}")


class AppTestHarness:
    """Complete app test harness with persistent controls"""
    
    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.mock_orchestrator = MockOrchestrator()
        self.mock_bridge = MockOrchestratorBridge(self.mock_orchestrator)
        self.app: Optional[GenesisApp] = None
        
        # Test control panel
        self.stage_dropdown: Optional[ft.Dropdown] = None
        self.test_message_input: Optional[ft.TextField] = None
        self.send_btn: Optional[ft.ElevatedButton] = None
        
        # App content container (separate from test controls)
        self.app_content_container: Optional[ft.Container] = None
        
        # Original page methods (to override)
        self._original_page_add = None
        self._original_page_clean = None
    
    def main(self, page: ft.Page):
        """Main entry point for Flet app with persistent test controls"""
        self.page = page
        page.title = "Genesis App Test Harness"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1200
        page.window.height = 900
        page.window.resizable = True
        
        print("🚀 Starting Genesis App Test Harness...")
        print("This will test the complete app UI structure and stage transitions.")
        print("Use the test controls at the top to simulate different scenarios.")
        
        # Create persistent test controls at the top
        self._create_test_controls()
        
        # Create app content container
        self.app_content_container = ft.Container(
            expand=True,
            bgcolor=ft.Colors.GREY_50
        )
        
        # Override page.add and page.clean to manage app content separately
        self._original_page_add = page.add
        self._original_page_clean = page.clean
        
        def custom_add(*controls):
            """Add controls to app content container instead of page"""
            for control in controls:
                self.app_content_container.content = control
            page.update()
        
        def custom_clean():
            """Clear only app content, not test controls"""
            if self.app_content_container:
                self.app_content_container.content = None
            page.update()
        
        page.add = custom_add
        page.clean = custom_clean
        
        # Create main layout with test controls at top and app content below
        main_layout = ft.Column(
            controls=[
                # Test controls at top (persistent)
                ft.Container(
                    content=ft.Column([
                        ft.Text("🧪 Test Controls", size=16, weight=ft.FontWeight.BOLD),
                        ft.Row([
                            ft.Text("Stage:", size=12),
                            self.stage_dropdown,
                            ft.Text("Message:", size=12),
                            self.test_message_input,
                            self.send_btn,
                        ], alignment=ft.MainAxisAlignment.START),
                        ft.Divider(height=1, color=ft.Colors.GREY_300)
                    ]),
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    padding=ft.padding.all(10),
                    border_radius=5
                ),
                # App content below (dynamic)
                self.app_content_container
            ],
            expand=True,
            spacing=0
        )
        
        # Add the main layout to the actual page
        self._original_page_add(main_layout)
        
        # Initialize the Genesis app
        self.app = GenesisApp(self.mock_bridge)
        self.app.main(page)
        
        # Set initial stage
        self._set_stage("find_path")
    
    def _create_test_controls(self):
        """Create the test control panel"""
        # Stage selection dropdown
        self.stage_dropdown = ft.Dropdown(
            width=120,
            options=[
                ft.dropdown.Option("start", text="Start"),
                ft.dropdown.Option("find_path", text="Find Path"),
                ft.dropdown.Option("route", text="Route"),
                ft.dropdown.Option("execute", text="Execute"),
            ],
            value="find_path",
            on_change=self._on_stage_change
        )
        
        # Test message input
        self.test_message_input = ft.TextField(
            width=200,
            hint_text="Enter test message...",
            value="Find path for image processing"
        )
        
        # Send button
        self.send_btn = ft.ElevatedButton(
            text="Send",
            on_click=self._send_test_message
        )
    
    def _on_stage_change(self, e):
        """Handle stage change from dropdown"""
        if e.control.value:
            self._set_stage(e.control.value)
    
    def _set_stage(self, stage_name: str):
        """Set the app stage programmatically"""
        print(f"[TEST] Setting stage to: {stage_name}")
        
        # Update mock orchestrator state
        self.mock_orchestrator.state["stage"] = stage_name
        self.mock_bridge._current_state["stage"] = stage_name
        
        # Convert to Stage enum and trigger app stage change
        if self.app:
            try:
                if hasattr(Stage, stage_name.upper()):
                    stage_enum = getattr(Stage, stage_name.upper())
                    self.app.current_stage = stage_enum
                    self.app._update_stage_ui()
                else:
                    print(f"Warning: Unknown stage '{stage_name}'")
            except Exception as e:
                print(f"Error setting stage: {e}")
    
    def _send_test_message(self, e):
        """Send test message through the app"""
        if self.test_message_input and self.test_message_input.value:
            message = self.test_message_input.value
            print(f"[TEST] Sending message: '{message}'")
            
            if self.app and hasattr(self.app, '_handle_user_message_sync'):
                try:
                    self.app._handle_user_message_sync(message)
                except Exception as ex:
                    print(f"Error sending message: {ex}")


def main():
    """Run the test harness"""
    harness = AppTestHarness()
    ft.app(target=harness.main)


if __name__ == "__main__":
    main()
