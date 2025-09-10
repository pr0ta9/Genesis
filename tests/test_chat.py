"""
ChatPanel test harness with reasoning and streaming demonstrations.

What it demonstrates:
- Full ChatPanel with sidebar and chat functionality  
- Mock orchestrator bridge with reasoning and streaming
- Thread management through the sidebar
- Simulated assistant streaming and reasoning updates
- User input flow through the complete panel system

Run:
  python test_chat.py
"""

import asyncio
import sys
import os
from pathlib import Path
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

# Add project root to Python path so we can import from src
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import flet as ft

# Import from the correct locations
try:
    from src.gui.panels.chat_panel import ChatPanel
    from src.gui.stores.chat_store import ChatStore, ChatMessage
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


class MockOrchestratorBridge:
    """
    Enhanced mock of the orchestrator bridge for demonstration purposes.
    
    Exposes:
      - thread_id, current_state, conversation_history
      - set_callbacks, get_available_models, get_session_info
      - clear_conversation, delete_thread
      - send_message_with_streaming, send_clarification_response
    """

    def __init__(self):
        self._tid_counter = 1
        self.thread_id: str = f"demo-{self._tid_counter}"

        # state + history - start with some demo messages
        self.conversation_history: List[AnyMessage] = [
            HumanMessage("Hello there!"),
            AIMessage("Hi! I'm ready to demonstrate reasoning and streaming. Try sending me a message!"),
        ]
        self.current_state: Dict[str, Any] = {
            "messages": list(self.conversation_history),
            "classify_clarification": False,
            "route_clarification": False,
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
        return ["mock-llm", "gpt-oss:20b", "claude-3.5-sonnet"]

    def get_session_info(self) -> Dict[str, str]:
        return {"thread_id": self.thread_id}

    def clear_conversation(self):
        """Simulate backend creating a brand-new thread."""
        self._tid_counter += 1
        self.thread_id = f"demo-{self._tid_counter}"
        self.conversation_history = []
        self.current_state["messages"] = []
        self.current_state["classify_clarification"] = False
        self.current_state["route_clarification"] = False
        # let UI know something changed
        if self._on_state_change:
            self._on_state_change(self.current_state)

    def delete_thread(self, thread_id: str):
        """Pretend to delete a thread."""
        self._deleted.add(thread_id)
        if thread_id == self.thread_id:
            self.clear_conversation()

    # ----- enhanced message sending for demos -----

    async def send_message_with_streaming(self, user_text: str) -> Dict[str, Any]:
        """Enhanced version with more interesting demo responses."""
        # Add user message to "backend" history
        self.conversation_history.append(HumanMessage(user_text))
        self._push_history()

        # Enhanced reasoning stream based on message content
        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Thinking..."})
            
            # Customize reasoning based on user input
            if "reason" in user_text.lower() or "think" in user_text.lower():
                reasoning_chunks = [
                    "🧠 Analyzing your request for reasoning demonstration… ",
                    "💭 Breaking down the problem into components… ",
                    "🔍 Examining different approaches… ",
                    "⚡ Synthesizing the best response strategy… "
                ]
            elif "stream" in user_text.lower():
                reasoning_chunks = [
                    "📡 Preparing streaming response demonstration… ",
                    "🌊 Setting up token-by-token delivery… ",
                    "⚙️ Configuring response parameters… "
                ]
            else:
                reasoning_chunks = [
                    "🔄 Processing your message… ",
                    "📝 Generating thoughtful response… ",
                    "✨ Adding final touches… "
                ]
            
            for chunk in reasoning_chunks:
                await asyncio.sleep(0.4)
                self._on_reasoning_update({"type": "reasoning", "content": chunk})
            
            await asyncio.sleep(0.3)
            self._on_reasoning_update({"type": "finish_reasoning"})

        # Generate contextual response
        if "reasoning" in user_text.lower():
            reply = "🧠 Here's a demonstration of reasoning! The expandable panel above showed my thought process step-by-step. This is how complex AI reasoning can be visualized for transparency."
        elif "stream" in user_text.lower():
            reply = "🌊 This response demonstrates streaming! Each word appeared gradually, simulating real-time AI generation. Great for showing progress on longer responses."
        elif "hello" in user_text.lower() or "hi" in user_text.lower():
            reply = "👋 Hello! Try asking me to 'show reasoning' or 'demonstrate streaming' to see the different features in action!"
        else:
            reply = f"✨ Thanks for your message: '{user_text}'. This is a demo response showing the full ChatPanel in action with reasoning, streaming, and sidebar functionality!"

        self.conversation_history.append(AIMessage(reply))
        self._push_history()

        return {"ok": True}

    async def send_clarification_response(self, text: str) -> Dict[str, Any]:
        """Handle clarification responses."""
        self.conversation_history.append(HumanMessage(f"[clarification] {text}"))
        self._push_history()

        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Processing clarification…"})
            await asyncio.sleep(0.4)
            self._on_reasoning_update({"type": "reasoning", "content": "Thanks for the clarification!"})
            await asyncio.sleep(0.2)
            self._on_reasoning_update({"type": "finish_reasoning"})

        self.conversation_history.append(AIMessage("Perfect! I can proceed with your clarification."))
        self.current_state["classify_clarification"] = False
        self.current_state["route_clarification"] = False
        self._push_history()
        return {"ok": True}

    # ----- enhanced demo methods -----

    async def simulate_reasoning_demo(self):
        """Standalone reasoning demonstration."""
        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Manual Reasoning Demo"})
            
            demo_steps = [
                "🎯 This is a manual reasoning demonstration… ",
                "🧩 Breaking down complex problems step by step… ",
                "🔬 Analyzing different solution approaches… ",
                "💡 Weighing pros and cons of each option… ",
                "🎲 Making informed decisions based on analysis… ",
                "✅ Arriving at the optimal solution!"
            ]
            
            for step in demo_steps:
                await asyncio.sleep(0.5)
                self._on_reasoning_update({"type": "reasoning", "content": step})
            
            await asyncio.sleep(0.3)
            self._on_reasoning_update({"type": "finish_reasoning"})

        # Add the final message
        reply = "🎭 This was a manual reasoning demonstration! Notice how the thought process was shown step-by-step in the expandable panel above."
        self.conversation_history.append(AIMessage(reply))
        self._push_history()

    async def simulate_streaming_demo(self):
        """Standalone streaming demonstration."""
        # Start with reasoning
        if self._on_reasoning_update:
            self._on_reasoning_update({"type": "start_reasoning", "title": "Preparing stream..."})
            await asyncio.sleep(0.3)
            self._on_reasoning_update({"type": "reasoning", "content": "Setting up streaming response..."})
            await asyncio.sleep(0.2)
            self._on_reasoning_update({"type": "finish_reasoning"})

        # Stream a response token by token
        full_message = "🚀 This demonstrates token-by-token streaming! Each word appears individually to show real-time AI generation. This creates a more engaging user experience and provides immediate feedback that the AI is working on your request."
        
        # Add initial empty message that we'll stream into
        self.conversation_history.append(AIMessage(""))
        self._push_history()
        
        # Simulate streaming by updating the last message
        current_text = ""
        for word in full_message.split():
            current_text += word + " "
            # Update the last message in place
            if self.conversation_history:
                self.conversation_history[-1] = AIMessage(current_text.strip())
                self._push_history()
            await asyncio.sleep(0.08)

    # ----- internals -----

    def _push_history(self):
        """Push full history to callback and mirror in current_state."""
        self.current_state["messages"] = list(self.conversation_history)
        if self._on_message_update:
            self._on_message_update(self.current_state["messages"])
        if self._on_state_change:
            self._on_state_change(self.current_state)


class ChatHarnessApp:
    def __init__(self):
        self.page: ft.Page | None = None
        self.bridge = MockOrchestratorBridge()
        self.store = ChatStore()
        self.panel: Optional[ChatPanel] = None

        # UI refs for demo controls
        self.reasoning_btn: ft.ElevatedButton | None = None
        self.stream_btn: ft.ElevatedButton | None = None
        self.seed_btn: ft.ElevatedButton | None = None

    def main(self, page: ft.Page):
        self.page = page
        page.title = "Genesis – ChatPanel Demonstration"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 1200
        page.window.height = 860
        page.padding = 0

        # Create ChatPanel with mock bridge and shared store
        self.panel = ChatPanel(orchestrator_bridge=self.bridge, store=self.store)
        self.panel.set_page(page)
        panel_ui = self.panel.build()

        # Demo controls row (top)
        self.reasoning_btn = ft.ElevatedButton(
            "Manual Reasoning Demo", 
            icon=ft.Icons.PSYCHOLOGY, 
            on_click=self._simulate_reasoning
        )
        self.stream_btn = ft.ElevatedButton(
            "Manual Streaming Demo", 
            icon=ft.Icons.STACKED_LINE_CHART, 
            on_click=self._simulate_stream
        )
        self.seed_btn = ft.ElevatedButton(
            "Seed Assistant Reply", 
            icon=ft.Icons.DOWNLOAD, 
            on_click=self._seed_reply
        )

        demo_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "💡 Demo Controls:", 
                        size=16, 
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_GREY_700
                    ),
                    ft.Container(width=16),
                    self.reasoning_btn,
                    self.stream_btn,
                    self.seed_btn,
                    ft.Container(width=16),
                    ft.Text(
                        "Try typing: 'show reasoning' or 'demonstrate streaming'",
                        size=14,
                        color=ft.Colors.BLUE_GREY_500,
                        italic=True
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.BLUE),
        )

        # Layout
        page.controls.clear()
        page.add(demo_bar, panel_ui)
        page.update()

    # ---------- Demo button handlers ----------

    def _simulate_reasoning(self, _):
        """Manual reasoning demonstration."""
        if not self.page:
            return
        self.page.run_task(self.bridge.simulate_reasoning_demo)

    def _simulate_stream(self, _):
        """Manual streaming demonstration."""
        if not self.page:
            return
        self.page.run_task(self.bridge.simulate_streaming_demo)

    def _seed_reply(self, _):
        """Add a seeded assistant message immediately."""
        self.bridge.conversation_history.append(
            AIMessage("🌱 Seeded assistant message added instantly (no streaming).")
        )
        self.bridge._push_history()

def main():
    ft.app(target=ChatHarnessApp().main)

if __name__ == "__main__":
    main()
