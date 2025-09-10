"""
Configuration settings for Genesis backend.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # App settings
    app_name: str = "Genesis Backend"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # API settings
    api_v1_prefix: str = "/api/v1"
    
    # CORS settings
    cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    
    # Genesis project settings
    genesis_project_root: Optional[str] = None
    
    # Database settings (handled in db/database.py)
    
    # WebSocket settings
    ws_heartbeat_interval: int = 30  # seconds
    
    class Config:
        env_prefix = "GENESIS_"
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set Genesis project root if not provided
        if not self.genesis_project_root:
            # Go up two levels from backend/app to get to project root
            self.genesis_project_root = str(Path(__file__).parent.parent.parent.resolve())
            # Set in environment for orchestrator
            os.environ["GENESIS_PROJECT_ROOT"] = self.genesis_project_root
            # Also set inputs root under project root unless already provided
            os.environ.setdefault("GENESIS_INPUTS_ROOT", str(Path(self.genesis_project_root) / "inputs"))


# Create settings instance
settings = Settings()
