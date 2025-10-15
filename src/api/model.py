"""
Model management API.

Endpoints:
- GET /models        → list available models (from env/config and dynamic sources)
- POST /models/select → select model; resets orchestrator with chosen provider/model
"""
from typing import List, Dict, Any, Optional
import os
import json
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.db.client import get_weaviate_client


router = APIRouter(prefix="/models", tags=["models"])


class ModelSelectRequest(BaseModel):
    """Request body for model selection"""
    provider: Optional[str] = None
    model: str
    # AWS Bedrock credentials (optional, required if provider is "bedrock")
    aws_region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None


def _env_models() -> List[Dict[str, str]]:
    """Parse AVAILABLE_MODELS env: comma-separated entries like 'ollama:gpt-oss:20b,openai:gpt-4o'"""
    env_val = os.getenv("AVAILABLE_MODELS", "")
    models: List[Dict[str, str]] = []
    for raw in [s.strip() for s in env_val.split(",") if s.strip()]:
        if ":" in raw:
            provider, model = raw.split(":", 1)
        else:
            provider, model = "ollama", raw
        models.append({"id": f"{provider}:{model}", "provider": provider, "name": model})
    return models


def _ollama_models() -> List[Dict[str, str]]:
    """Fetch available models from a local Ollama instance if reachable."""
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    # Support both formats: "host:port" and "http://host:port"
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    url = f"{host.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models: List[Dict[str, str]] = []
        for m in data.get("models", []) or []:
            name = m.get("name") or ""
            if not name:
                continue
            models.append({"id": f"ollama:{name}", "provider": "ollama", "name": name})
        return models
    except Exception as e:
        # Log the error for debugging
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch Ollama models from {host}: {e}")
        return []


def list_available_models() -> List[Dict[str, str]]:
    """Aggregate available models from env and dynamic sources (Ollama)."""
    seen: set[str] = set()
    results: List[Dict[str, str]] = []
    for entry in (_env_models() + _ollama_models()):
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        results.append(entry)
    # Sensible fallback if none discovered
    if not results:
        results = [
            {"id": "ollama:gpt-oss:20b", "provider": "ollama", "name": "gpt-oss:20b"},
        ]
    return results


@router.get("/")
def get_models(req: Request) -> Dict[str, Any]:
    models = list_available_models()
    current: Optional[str] = None
    orch = getattr(req.app.state, "orchestrator", None)
    if orch is not None:
        # Best-effort: expose provider:model if available from orchestrator config
        try:
            llm_obj = getattr(orch, "llm", None)
            if llm_obj:
                class_name = llm_obj.__class__.__name__
                # Map class names to provider names
                if "ChatOllama" in class_name or "Ollama" in class_name:
                    provider = "ollama"
                elif "ChatOpenAI" in class_name or "OpenAI" in class_name:
                    provider = "openai"
                else:
                    provider = class_name.replace("Chat", "").lower()
            else:
                provider = None
        except Exception:
            provider = None
        try:
            # Many LLM clients expose model name on .model or .model_name
            model_name = getattr(getattr(orch, "llm", None), "model", None) or getattr(getattr(orch, "llm", None), "model_name", None)
        except Exception:
            model_name = None
        if provider and model_name:
            current = f"{provider}:{model_name}"
    return {"models": models, "count": len(models), "current": current}


@router.post("/select")
def select_model(req: Request, body: ModelSelectRequest) -> Dict[str, Any]:
    """Select model and reset orchestrator.

    Args:
        body: Model selection request containing provider, model name, and optional AWS credentials.
    """
    if not body.model:
        raise HTTPException(status_code=400, detail="model is required")

    # Allow provider embedded in model (provider:model)
    provider = body.provider
    model = body.model
    if ":" in model and not provider:
        provider, model = model.split(":", 1)

    provider = provider or "ollama"

    # Validate AWS credentials if provider is bedrock
    if provider == "bedrock":
        if not body.aws_region or not body.aws_access_key_id or not body.aws_secret_access_key:
            raise HTTPException(
                status_code=400,
                detail="AWS credentials (aws_region, aws_access_key_id, aws_secret_access_key) are required for Bedrock provider"
            )

    # Optionally validate against discovered models
    available_ids = {m["id"] for m in list_available_models()}
    target_id = f"{provider}:{model}"
    if available_ids and target_id not in available_ids:
        # Soft validation: warn client but allow selection to proceed
        pass

    # Recreate orchestrator with chosen provider/model
    try:
        from src.orchestrator.core.orchestrator import Orchestrator
        
        # Get Weaviate client for precedent search
        weaviate_client = get_weaviate_client()
        
        req.app.state.orchestrator = Orchestrator(
            llm_type=provider,
            model_name=model,
            weaviate_client=weaviate_client,
            aws_region=body.aws_region,
            aws_access_key_id=body.aws_access_key_id,
            aws_secret_access_key=body.aws_secret_access_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize orchestrator: {e}")

    return {"selected": target_id}


