# server/middleware/rate_limit.py
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# In-memory rate limit store (use Redis in production)
rate_limits = defaultdict(list)

async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    
    # Only rate limit auth endpoints
    if not request.url.path.startswith("/api/auth"):
        return await call_next(request)
    
    client_ip = request.client.host
    now = datetime.utcnow()
    
    # Remove old entries (older than 1 minute)
    rate_limits[client_ip] = [
        timestamp for timestamp in rate_limits[client_ip]
        if now - timestamp < timedelta(minutes=1)
    ]
    
    # Check limit (max 5 requests per minute per IP)
    if len(rate_limits[client_ip]) >= 5:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        )
    
    # Record request
    rate_limits[client_ip].append(now)
    
    return await call_next(request)