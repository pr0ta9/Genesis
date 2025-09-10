# backend_client.py
import asyncio
from typing import AsyncIterator, Optional

class BackendClient:
    """Replace this with your real HTTP/WebSocket client."""
    def __init__(self, model: Optional[str] = None):
        self.model = model or "gemma3:4b"

    async def chat_stream(self, message: str) -> AsyncIterator[str]:
        # Simulated thinking / token stream
        text = f"Using model `{self.model}`.\nYou said: {message}\n\nHere is a simulated response "
        for ch in text:
            await asyncio.sleep(0.01)  # simulate token latency
            yield ch

    async def chat_once(self, message: str) -> str:
        await asyncio.sleep(0.3)
        return f"(one-shot) [{self.model}] → Echo: {message}"
