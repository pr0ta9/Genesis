#!/usr/bin/env python3
"""
Database Migration Script for Genesis Backend

This script automatically checks and updates the PostgreSQL database schema
to match the current SQLAlchemy models. It's designed to run at startup
to ensure the database schema is always up-to-date.

Usage:
    python src/db/migrations.py
"""

import os
import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# Add project root to path so we can import our models
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.model import Base, Message
from src.db.database import DATABASE_URL

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        return any(col['name'] == column_name for col in columns)
    except Exception as e:
        logger.error(f"Error checking column {table_name}.{column_name}: {e}")
        return False


def add_missing_columns(engine):
    """Add any missing columns to existing tables."""
    migrations_applied = []
    
    try:
        with engine.connect() as conn:
            # Check if messages.attachments column exists
            if not check_column_exists(engine, 'messages', 'attachments'):
                logger.info("Adding 'attachments' column to messages table...")
                conn.execute(text('ALTER TABLE messages ADD COLUMN attachments JSONB'))
                migrations_applied.append("messages.attachments")
            
            # Add future migrations here as needed
            # Example:
            # if not check_column_exists(engine, 'chats', 'new_column'):
            #     conn.execute(text('ALTER TABLE chats ADD COLUMN new_column VARCHAR(255)'))
            #     migrations_applied.append("chats.new_column")
            
            # Commit all changes
            conn.commit()
            
    except SQLAlchemyError as e:
        logger.error(f"Failed to apply migrations: {e}")
        raise
    
    return migrations_applied


def create_missing_tables(engine):
    """Create any missing tables."""
    try:
        # Get list of existing tables
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        
        # Get expected tables from our models
        expected_tables = set(Base.metadata.tables.keys())
        
        # Find missing tables
        missing_tables = expected_tables - existing_tables
        
        if missing_tables:
            logger.info(f"Creating missing tables: {missing_tables}")
            # Create only the missing tables
            Base.metadata.create_all(engine, tables=[Base.metadata.tables[table] for table in missing_tables])
            return list(missing_tables)
        else:
            logger.info("All expected tables exist")
            return []
            
    except SQLAlchemyError as e:
        logger.error(f"Failed to create missing tables: {e}")
        raise


def run_migrations():
    """Main migration function."""
    logger.info("🔄 Starting database migrations...")
    
    try:
        # Use database URL from environment
        logger.info(f"Connecting to database...")
        
        # Create engine
        engine = create_engine(DATABASE_URL)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
        
        # Create missing tables first
        created_tables = create_missing_tables(engine)
        if created_tables:
            logger.info(f"✅ Created tables: {created_tables}")
        
        # Add missing columns
        migrations_applied = add_missing_columns(engine)
        if migrations_applied:
            logger.info(f"✅ Applied migrations: {migrations_applied}")
        
        if not created_tables and not migrations_applied:
            logger.info("✅ Database schema is up-to-date, no migrations needed")
        else:
            logger.info(f"✅ Database migrations completed successfully")
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
