"""
Database configuration for Genesis backend.
Uses SQLite for local storage similar to Ollama.
"""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Determine database location
if os.name == 'nt':  # Windows
    DB_DIR = Path(os.environ.get('APPDATA', '')) / 'Genesis'
else:  # Unix-like (Mac, Linux)
    DB_DIR = Path.home() / '.genesis'

# Create directory if it doesn't exist
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / 'conversations.db'

# SQLAlchemy setup
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine with connection pooling disabled for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    pool_pre_ping=True,
    echo=False  # Set to True for SQL debugging
)

# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI
def get_db():
    """Dependency to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Output directory configuration
OUTPUT_DIR = DB_DIR / 'outputs'
OUTPUT_DIR.mkdir(exist_ok=True)

def get_output_dir(thread_id: str) -> Path:
    """Get output directory for a specific conversation thread."""
    thread_dir = OUTPUT_DIR / thread_id
    thread_dir.mkdir(exist_ok=True)
    return thread_dir
