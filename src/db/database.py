"""
PostgreSQL database configuration for Genesis backend.

This module defines a single place to create and export the SQLAlchemy
engine, session factory, and the declarative Base. All ORM models must
inherit from the same `Base` defined here so that metadata is shared
and migrations/table creation operate on a single registry.
"""
import os
from contextlib import contextmanager
from typing import Iterator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session


# Connection string from environment, falling back to a sensible local default
# Example: postgresql+psycopg://username:password@localhost:5432/gen
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/gen",
)


# SQLAlchemy engine and session factory
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


# Declarative base for ORM models. All models should inherit from this Base.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it afterward."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations.

    Commits on success, rolls back on exception, and always closes the session.
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
    "session_scope",
]


