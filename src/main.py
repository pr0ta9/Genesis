"""
Genesis Backend Entry Point
==========================

Starts FastAPI, initializes PostgreSQL tables, connects Weaviate client,
and preloads the Orchestrator. Routers are mounted under /api/v1.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware

from src.db.database import engine, Base
from src.db import model as db_models  # ensure models are imported for metadata
from src.db.client import get_weaviate_client, close_weaviate_client
from src.api.chat import router as chat_router
from src.api.message import router as message_router
from src.api.artifact import router as artifact_router


# Application settings
APP_NAME = os.getenv("APP_NAME", "Genesis Backend")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
API_PREFIX = os.getenv("API_PREFIX", "/api/v1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    # Startup: initialize DB tables
    try:
        Base.metadata.create_all(bind=engine)
        logging.getLogger(__name__).info("✅ Database tables ensured")
    except Exception as e:
        logging.getLogger(__name__).exception("Failed to initialize database tables: %s", e)
        raise

    # Startup: initialize Weaviate client
    weaviate_client = None
    try:
        weaviate_client = get_weaviate_client()
        app.state.weaviate_client = weaviate_client
        logging.getLogger(__name__).info("✅ Weaviate client ready")
    except Exception as e:
        logging.getLogger(__name__).warning("Weaviate unavailable or failed to init: %s", e)
        app.state.weaviate_client = None

    # Startup: preload orchestrator (optional; message API will be gated by dependency)
    try:
        from src.orchestrator.core.orchestrator import Orchestrator
        orchestrator = Orchestrator(weaviate_client=weaviate_client)
        app.state.orchestrator = orchestrator
        logging.getLogger(__name__).info("✅ Orchestrator initialized")
    except Exception as e:
        logging.getLogger(__name__).warning("Orchestrator failed to initialize at startup: %s", e)
        app.state.orchestrator = None

    yield

    # Shutdown: close Weaviate client
    try:
        close_weaviate_client()
    except Exception:
        pass
    try:
        engine.dispose()
    except Exception:
        pass

def require_orchestrator(req: Request) -> None:
    if getattr(req.app.state, "orchestrator", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Orchestrator not ready")


def require_weaviate(req: Request) -> None:
    if getattr(req.app.state, "weaviate_client", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector store not ready")

def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

    # CORS (open by default; tighten in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoints
    @app.get("/")
    async def root():
        return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}


    @app.get("/health")
    async def health():
        ok_db = True
        ok_vec = app.state.weaviate_client is not None
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        except Exception:
            ok_db = False
        return {"db": ok_db, "vector": ok_vec, "ok": ok_db and ok_vec}

    app.include_router(
        chat_router,
        prefix=API_PREFIX,
        # Chats can remain available even if vector/orchestrator are down
    )
    app.include_router(
        message_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_orchestrator), Depends(require_weaviate)],
    )
    app.include_router(
        artifact_router,
        prefix=API_PREFIX,
        # Artifacts don't require orchestrator/weaviate dependencies
    )
    return app



app = create_app()


if __name__ == "__main__":
    # Run development server via `python -m src.main` or `python src/main.py`
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() == "true"

    # Only watch src/ directory for changes, ignore tmp/ and outputs/
    uvicorn.run(
        "src.main:app", 
        host=host, 
        port=port, 
        reload=reload,
        reload_dirs=["src"] if reload else None,
        reload_excludes=["tmp/**", "outputs/**", "inputs/**"] if reload else None,
    )


