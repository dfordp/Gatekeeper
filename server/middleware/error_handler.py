# server/middleware/error_handler.py
"""Global error handling middleware"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from utils.exceptions import GatekeeperException
from core.logger import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI):
    """Register error handlers with FastAPI app"""
    
    @app.exception_handler(GatekeeperException)
    async def gatekeeper_exception_handler(request: Request, exc: GatekeeperException):
        """Handle custom Gatekeeper exceptions"""
        logger.error(f"{exc.code}: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "path": str(request.url.path)
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions"""
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "path": str(request.url.path)
            }
        )