"""
Initialize database tables.
"""
from .database import engine, Base
from .models import Conversation, Message, State


def init_db():
    """Create all tables."""
    print(f"Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Verify schema includes precedent_id column
    try:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            # Test query to verify precedent_id column exists
            result = db.execute("PRAGMA table_info(messages)").fetchall()
            columns = [row[1] for row in result]  # Column names are in index 1
            if 'precedent_id' in columns:
                print("✅ precedent_id column exists in messages table")
            else:
                print("❌ precedent_id column MISSING from messages table")
                print(f"Available columns: {columns}")
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ Could not verify schema: {e}")


if __name__ == "__main__":
    init_db()
