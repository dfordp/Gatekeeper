# server/core/async_database.py
"""Async database configuration and session management for async routes"""
import logging
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from typing import AsyncGenerator
from sqlalchemy import text
from .config import DATABASE_URL
from core.async_database import startup_async_db
from core.async_database import shutdown_async_db


# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Convert PostgreSQL URL to async format
# postgresql://user:pass@host/db -> postgresql+asyncpg://user:pass@host/db
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Create async engine with optimized pool settings
# pool_size=20: number of connections to keep in pool
# max_overflow=10: allow up to 10 extra connections beyond pool_size
# pool_recycle=3600: recycle connections after 1 hour (PostgreSQL closes after 30min of inactivity)
# pool_pre_ping=True: test connections before using them
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args={
        "timeout": 30,
        "server_settings": {"jit": "off"},  # Disable JIT for predictable performance
    },
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit (async-safe)
    autocommit=False,
    autoflush=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection function for FastAPI routes.
    
    Usage in routes:
        @app.get("/endpoint")
        async def my_route(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(stmt)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def test_async_connection():
    """Test async database connection"""
    try:
        async with async_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("✓ Async database connection test passed")
            return True
    except Exception as e:
        logger.error(f"✗ Async database connection test failed: {e}")
        return False


async def startup_async_db():
    """Initialize async database on application startup"""
    logger.info("Starting async database initialization...")
    test_result = await test_async_connection()
    await startup_async_db()
    if test_result:
        logger.info("✓ Async database ready")
    else:
        logger.error("✗ Async database initialization failed")


async def shutdown_async_db():
    """Clean up async database on application shutdown"""
    logger.info("Shutting down async database...")
    await async_engine.dispose()
    await shutdown_async_db()  
    logger.info("✓ Async database disposed")