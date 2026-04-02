"""Database engine and async session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Default to async PostgreSQL; override via init_db() for testing.
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str = "postgresql+asyncpg://localhost/pdf_extraction") -> None:
    """Initialize the database engine and session factory."""
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory. Raises if init_db() hasn't been called."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


def get_engine():
    """Return the current engine."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
