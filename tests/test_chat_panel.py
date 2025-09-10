"""
Test harness for ChatPanel (Sidebar + Chat + ChatStore in one panel)

What it demonstrates:
- A mock OrchestratorBridge that supports:
  * thread management (clear_conversation -> new thread id)
  * callbacks (on_message_update, on_state_change, on_reasoning_update)
  * streaming-style reasoning updates
  * final assistant reply -> hydrates messages in the panel
- Using ChatPanel as a drop-in control that can be placed anywhere.

Run:
  python test_chat_panel.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import flet as ft
from typing import Any, Dict, List, Optional, Callable

# LangChain message types used by the bridge
try:
    from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
except Exception:
    # lightweight fallback if LangChain isn't installed (keeps demo runnable)
    class _Msg:
        def __init__(self, content: str): self.content = content
    class HumanMessage(_Msg): pass
    class AIMessage(_Msg): pass
    AnyMessage = _Msg  # type: ignore


# Try both import roots (adjust if your paths differ)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import flet as ft

# Import from the correct locations

from src.gui.panels.chat_panel import ChatPanel
from src.gui.stores.chat_store import ChatStore

# ------------------------------
# Mock Orchestrator Bridge
# ------------------------------

class MockOrchestratorBridge:
    """
    Minimal, self-contained mock of the orchestrator bridge.

    Exposes:
      - thread_id
      - current_state (includes flags + messages)
      - conversation_history
      - set_callbacks(...)
      - get_available_models()
      - get_session_info()
      - clear_conversation()
      - delete_thread(thread_id)
      - send_message_with_streaming(text)
      - send_clarification_response(text)
    """

    def __init__(self):
        self._tid_counter = 1
        self.thread_id: str = f"thread-{self._tid_counter}"

        # state + history
        self.conversation_history: List[AnyMessage] = [
            HumanMessage("Hello!"),
            AIMessage("Hi — this is a mock assistant in ChatPanel harness."),
        ]
        self.current_state: Dict[str, Any] = {
            "messages": list(self.conversation_history),
            "classify_clarification": False,
            "route_clarification": False,
            # you can add more keys from your backend State here
        }

        # callbacks (panel registers these)
        self._on_message_update: Optional[Callable[[List[AnyMessage]], None]] = None
        self._on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_reasoning_update: Optional[Callable[[Dict[str, Any]], None]] = None

        self._deleted: set[str] = set()

    # ----- bridge API -----

    def set_callbacks(
        self,
        on_message_update: Optional[Callable[[List[AnyMessage]], None]] = None,
        on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_reasoning_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        **_ignored,
    ):
        self._on_message_update = on_message_update
        self._on_state_change = on_state_change
        self._on_reasoning_update = on_reasoning_update

    def get_available_models(self) -> List[str]:
        return ["mock-llm", "gpt-oss:20b"]

    def get_session_info(self) -> Dict[str, str]:
        return {"thread_id": self.thread_id}

    def clear_conversation(self):
        """Simulate backend creating a brand-new thread."""
        self._tid_counter += 1
        self.thread_id = f"thread-{self._tid_counter}"
        self.conversation_history = []
        self.current_state["messages"] = []
        self.current_state["classify_clarification"] = False
        self.current_state["route_clarification"] = False
        # let UI know something changed (optional)
        if self._on_state_change:
            self._on_state_change(self.current_state)

    def delete_thread(self, thread_id: str):
        """Pretend to delete a thread—tracks only for demo purposes."""
        self._deleted.add(thread_id)
        # If deleting the current thread, reset to a new one
        if thread_id == self.thread_id:
            self.clear_conversation()

    # ----- message sending -----

    async def send_message_with_streaming(self, user_text: str) -> Dict[str, Any]:
        """
        Simulate a normal query:
         - stream reasoning updates
         - push final assistant message via on_message_update
        """
        # Add user message to "backend" history
        self.conversation_history.append(HumanMessage(user_text))
        self._push_history()

        # Reasoning stream
        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Thinking..."})
            chunks = [
                "Analyzing user request… ",
                "Drafting an outline… ",
                "Formulating the final response… "
            ]
            for ch in chunks:
                await asyncio.sleep(0.35)
                self._on_reasoning_update({"type": "reasoning", "content": ch})
            await asyncio.sleep(0.25)
            self._on_reasoning_update({"type": "finish_reasoning"})

        # Final assistant reply
        reply = "Here is a streamed-looking response (mocked end result) ✨"
        self.conversation_history.append(AIMessage(reply))
        self._push_history()

        return {"ok": True}

    async def send_clarification_response(self, text: str) -> Dict[str, Any]:
        """
        Simulate clarifications when either classify_clarification or route_clarification is set.
        """
        self.conversation_history.append(HumanMessage(f"[clarification] {text}"))
        self._push_history()

        # Tiny "thinking"
        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Clarifying…"})
            await asyncio.sleep(0.4)
            self._on_reasoning_update({"type": "reasoning", "content": "Thanks, that helps."})
            await asyncio.sleep(0.2)
            self._on_reasoning_update({"type": "finish_reasoning"})

        self.conversation_history.append(AIMessage("Great, I can proceed with your clarification."))
        # clear flags as if backend resolved them
        self.current_state["classify_clarification"] = False
        self.current_state["route_clarification"] = False
        self._push_history()
        return {"ok": True}

    # ----- internals -----

    def _push_history(self):
        """Push full history to callback and mirror in current_state."""
        self.current_state["messages"] = list(self.conversation_history)
        if self._on_message_update:
            self._on_message_update(self.current_state["messages"])
        if self._on_state_change:
            self._on_state_change(self.current_state)


# ------------------------------
# Test app
# ------------------------------

class ChatPanelHarness:
    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.bridge = MockOrchestratorBridge()
        self.store = ChatStore()  # shared UI cache (inject into panel)
        self.panel: Optional[ChatPanel] = None

        # top-bar controls
        self.classify_sw: Optional[ft.Switch] = None
        self.route_sw: Optional[ft.Switch] = None
        self.new_btn: Optional[ft.ElevatedButton] = None
        self.seed_btn: Optional[ft.ElevatedButton] = None

    def main(self, page: ft.Page):
        self.page = page
        page.title = "Genesis – ChatPanel Tester"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1200
        page.window.height = 860
        page.padding = 0

        # Panel: inject shared store + mock bridge
        self.panel = ChatPanel(orchestrator_bridge=self.bridge, store=self.store)
        self.panel.set_page(page)
        panel_ui = self.panel.build()

        # Top bar: toggles & helpers
        self.classify_sw = ft.Switch(label="classify_clarification", value=False, on_change=self._toggle_classify)
        self.route_sw = ft.Switch(label="route_clarification", value=False, on_change=self._toggle_route)
        self.new_btn = ft.ElevatedButton("New chat (via backend)", icon=ft.Icons.ADD, on_click=self._new_chat)
        self.seed_btn = ft.ElevatedButton("Seed assistant reply (no stream)", icon=ft.Icons.DOWNLOAD, on_click=self._seed_reply)

        top_bar = ft.Container(
            ft.Row(
                [
                    self.classify_sw,
                    self.route_sw,
                    ft.Container(width=16),
                    self.new_btn,
                    self.seed_btn,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.BLACK),
        )

        page.add(top_bar, panel_ui)
        page.update()

    # ----- top bar handlers -----

    def _toggle_classify(self, e: ft.ControlEvent):
        v = bool(e.control.value)
        self.bridge.current_state["classify_clarification"] = v
        if self.bridge._on_state_change:
            self.bridge._on_state_change(self.bridge.current_state)

    def _toggle_route(self, e: ft.ControlEvent):
        v = bool(e.control.value)
        self.bridge.current_state["route_clarification"] = v
        if self.bridge._on_state_change:
            self.bridge._on_state_change(self.bridge.current_state)

    def _new_chat(self, _):
        # use the panel’s public intent (it will call backend and update store)
        if self.page and self.panel:
            self.page.run_task(self.panel._create_thread_async)  # intentionally using the panel’s helper

    def _seed_reply(self, _):
        """
        Simulate the backend pushing a system reply immediately (no streaming).
        Useful to verify that on_message_update hydrates the active thread.
        """
        self.bridge.conversation_history.append(AIMessage("Seeded assistant message (no streaming)."))
        self.bridge._push_history()
        print(self.bridge.conversation_history)


def main():
    ft.app(target=ChatPanelHarness().main)


if __name__ == "__main__":
    main()
