# server/routes/__init__.py
from fastapi import APIRouter
from .auth import router as auth_router
from .tickets import router as tickets_router
from .rca import router as rca_router
from .attachments import router as attachments_router
from .events import router as events_router
from .analytics import router as analytics_router

def include_routes(app):
    """Include all routes in the FastAPI app."""
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(tickets_router, prefix="/api/companies", tags=["tickets"])
    app.include_router(rca_router, prefix="/api/companies", tags=["rca"])
    app.include_router(attachments_router, prefix="/api/companies", tags=["attachments"])
    app.include_router(events_router, prefix="/api/companies", tags=["events"])
    app.include_router(analytics_router, prefix="/api/companies", tags=["analytics"])