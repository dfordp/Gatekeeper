# server/middleware/logging.py
from fastapi import Request
from uuid import uuid4
import logging
import time

logger = logging.getLogger(__name__)

async def add_request_id_middleware(request: Request, call_next):
    """Add request ID to all requests for tracing."""
    
    request_id = str(uuid4())
    request.state.request_id = request_id
    
    # Log request
    start_time = time.time()
    logger.info(
        f"[{request_id}] {request.method} {request.url.path}",
        extra={"request_id": request_id}
    )
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = time.time() - start_time
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - {response.status_code} ({duration:.2f}s)",
        extra={"request_id": request_id, "duration": duration}
    )
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    
    return response