"""
Main FastAPI application for Genesis backend.
"""
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.db.init_db import init_db
from app.api.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Genesis project root: {settings.genesis_project_root}")
    
    # Initialize database
    init_db()
    
    # Initialize global components during startup
    from app.services.orchestrator_service import get_orchestrator
    from app.db.precedent import initialize_global_clients
    
    # Initialize TiDB client and orchestrator once globally
    try:
        # This will create and validate the global TiDB client
        initialize_global_clients()
        print("✅ TiDB client initialized globally for precedent search")
        
        # Initialize orchestrator singleton 
        orchestrator = get_orchestrator()
        print("✅ Orchestrator initialized globally")
        
    except Exception as e:
        print(f"⚠️  Warning: Global initialization failed - some features may be unavailable: {e}")
        # Still try to initialize orchestrator without TiDB
        try:
            orchestrator = get_orchestrator()
            print("✅ Orchestrator initialized (without TiDB)")
        except Exception as orch_error:
            print(f"❌ Critical: Orchestrator initialization failed: {orch_error}")
            # Don't fail startup completely, but log critical error
    
    yield
    
    # Shutdown
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
