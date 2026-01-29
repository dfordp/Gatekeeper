# server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import logging
from config import settings
from utils.database import init_db
from utils.logger import setup_logger
from middleware.auth import verify_jwt_middleware
from utils.errors import gatekeeper_exception_handler, GatekeeperException
from routes import include_routes
from middleware.logging import add_request_id_middleware
from middleware.rate_limit import rate_limit_middleware

# Setup logging
setup_logger()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("🚀 Starting Gatekeeper API...")
    init_db()
    yield
    # Shutdown
    logger.info("🛑 Shutting down Gatekeeper API...")

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=verify_jwt_middleware)

# Exception handlers
app.add_exception_handler(GatekeeperException, gatekeeper_exception_handler)
app.add_middleware(BaseHTTPMiddleware, dispatch=add_request_id_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)

# Include routes
include_routes(app)

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )