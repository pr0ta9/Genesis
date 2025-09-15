"""
API v1 router aggregation.
"""
from fastapi import APIRouter

from .conversations import router as conversations_router
from .messages import router as messages_router
from .models import router as models_router
from .workspace import router as workspace_router
from .websocket import router as ws_router
from .states import router as states_router
from .uploads import router as uploads_router
from .outputs import router as outputs_router
from .tools import router as tools_router
from .precedents import router as precedents_router

# Create main v1 router
api_router = APIRouter()

# Include all sub-routers
api_router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
api_router.include_router(messages_router, prefix="/conversations", tags=["messages"])
api_router.include_router(models_router, prefix="/models", tags=["models"])
api_router.include_router(workspace_router, prefix="/workspace", tags=["workspace"])
api_router.include_router(states_router, prefix="/states", tags=["states"])
api_router.include_router(ws_router, tags=["websocket"])
api_router.include_router(uploads_router, prefix="/uploads", tags=["uploads"])
api_router.include_router(outputs_router, prefix="/outputs", tags=["outputs"])
api_router.include_router(tools_router, prefix="/tools", tags=["tools"])
api_router.include_router(precedents_router, prefix="/conversations", tags=["precedents"])
