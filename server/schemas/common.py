from pydantic import BaseModel
from typing import Any, Optional, Generic, TypeVar

T = TypeVar('T')

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None

class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    meta: dict[str, Any] = {}

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int

class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: ErrorDetail