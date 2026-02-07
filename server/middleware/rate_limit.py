# server/middleware/rate_limit.py
"""
Rate limiting middleware with per-vendor and global limits
Prevents DOS attacks and protects against resource exhaustion
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from typing import Dict
import asyncio
from core.logger import get_logger
import time

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-vendor rate limiting to prevent DOS.
    
    Limits:
    - 100 requests per minute per IP (per vendor)
    - 1000 requests per minute total (system-wide)
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.request_log: Dict[str, list] = {}  # IP -> timestamp list
        self.global_log: list = []
        self.lock = asyncio.Lock()
        
        # Configuration
        self.PER_IP_LIMIT = 100  # requests/minute per vendor
        self.GLOBAL_LIMIT = 1000  # requests/minute system-wide
        self.WINDOW_SIZE = 60  # seconds
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        async with self.lock:
            # Clean old timestamps older than window
            cutoff = now - self.WINDOW_SIZE
            self.global_log = [ts for ts in self.global_log if ts > cutoff]
            
            if client_ip not in self.request_log:
                self.request_log[client_ip] = []
            
            self.request_log[client_ip] = [
                ts for ts in self.request_log[client_ip] if ts > cutoff
            ]
            
            # Check per-IP limit
            if len(self.request_log[client_ip]) >= self.PER_IP_LIMIT:
                logger.warning(
                    f"Rate limit exceeded for {client_ip}: "
                    f"{len(self.request_log[client_ip])} requests in {self.WINDOW_SIZE}s"
                )
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Max 100 requests per minute."
                )
            
            # Check global limit
            if len(self.global_log) >= self.GLOBAL_LIMIT:
                logger.warning(
                    f"Global rate limit reached: "
                    f"{len(self.global_log)} requests in {self.WINDOW_SIZE}s"
                )
                raise HTTPException(
                    status_code=503,
                    detail="System at capacity. Please retry in 60 seconds."
                )
            
            # Record request
            self.request_log[client_ip].append(now)
            self.global_log.append(now)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self.PER_IP_LIMIT - len(self.request_log[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.PER_IP_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now) + self.WINDOW_SIZE)
        
        return response