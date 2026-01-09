"""
Database initialization and session management
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import logging

from .models import Base
from .config_parser import get_config

logger = logging.getLogger(__name__)


class Database:
    """Database manager"""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialized = False

    def init(self):
        """Initialize database connection"""
        if self._initialized:
            return

        config = get_config()
        db_config = config.database

        if db_config.type == "sqlite":
            # SQLite configuration
            db_url = f"sqlite:///{db_config.path}"
            self.engine = create_engine(
                db_url, connect_args={"check_same_thread": False}, echo=False
            )
        elif db_config.type == "postgresql":
            # PostgreSQL configuration
            db_url = (
                f"postgresql://{db_config.username}:{db_config.password}"
                f"@{db_config.host}:{db_config.port}/{db_config.database}"
            )
            self.engine = create_engine(db_url, echo=False)
        else:
            raise ValueError(f"Unsupported database type: {db_config.type}")

        # Create session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Create all tables
        Base.metadata.create_all(bind=self.engine)

        self._initialized = True
        logger.info(f"Database initialized: {db_url}")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session context manager"""
        if not self._initialized:
            self.init()

        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Global database instance
db = Database()


def get_db():
    """Dependency for FastAPI routes"""
    with db.get_session() as session:
        yield session
