"""Database migration script"""

from backend.database import db, Base
from sqlalchemy import text

print("🔧 Running database migration...")

try:
    # Initialize database first
    db.init()

    with db.engine.connect() as conn:
        # Add trading_mode
        try:
            conn.execute(
                text("ALTER TABLE bot_instances ADD COLUMN trading_mode VARCHAR(10) DEFAULT 'spot'")
            )
            print("✅ Added trading_mode")
        except Exception as e:
            if "duplicate" in str(e).lower():
                print("ℹ️  trading_mode exists")
            else:
                print(f"⚠️  {e}")

        # Add leverage
        try:
            conn.execute(text("ALTER TABLE bot_instances ADD COLUMN leverage INTEGER DEFAULT 1"))
            print("✅ Added leverage")
        except Exception as e:
            if "duplicate" in str(e).lower():
                print("ℹ️  leverage exists")
            else:
                print(f"⚠️  {e}")

        conn.commit()

    # Create all new tables
    Base.metadata.create_all(db.engine)
    print("✅ All tables created")

except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback

    traceback.print_exc()
