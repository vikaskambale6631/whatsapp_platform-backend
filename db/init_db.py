from .base import Base, engine
# Import ALL models to ensure they're registered with Base.metadata
from models import *


def init_db():
    """Create database tables."""
    try:
        from sqlalchemy.exc import IntegrityError
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except IntegrityError as e:
        # Handle race condition where another process created the types/tables simultaneously
        print(f"Warning: Database initialization race condition detected (safe to ignore if other workers succeed): {e}")
    except Exception as e:
        print(f"Error initializing database: {e}")
    
    # 🔥 AUTOMATIC MIGRATION: Increase status column length in message_logs
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE message_logs ALTER COLUMN status TYPE VARCHAR(255)"))
            conn.commit()
            print("✅ Successfully applied migration: Increased message_logs.status length to 255")
    except Exception as e:
        # Ignore if table doesn't exist yet or column already correct
        pass

