"""
Models API endpoints - stub implementation.
"""
from typing import List
from fastapi import APIRouter

from app.models.responses import ModelResponse
from app.services.orchestrator_service import get_orchestrator

router = APIRouter()


@router.get("/", response_model=List[ModelResponse])
async def list_models():
    """List available AI models."""
    orchestrator_service = get_orchestrator()
    models = orchestrator_service.get_available_models()
    
    # Convert to response format
    return [
        ModelResponse(
            id=model,
            name=model.split(":")[-1],
            provider=model.split(":")[0]
        )
        for model in models
    ]


@router.get("/current")
async def get_current_model():
    """Get current model configuration."""
    # TODO: Implement model tracking
    return {
        "current": "ollama:gpt-oss:20b",
        "fallback": None
    }
