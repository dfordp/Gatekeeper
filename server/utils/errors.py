from fastapi import status
from typing import Any, Optional

class GatekeeperException(Exception):
    """Base exception for Gatekeeper."""
    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

class ValidationError(GatekeeperException):
    """Validation error."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__("VALIDATION_ERROR", message, details)

class NotFoundError(GatekeeperException):
    """Resource not found."""
    def __init__(self, resource: str, identifier: str = None):
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        super().__init__("NOT_FOUND", message)

class UnauthorizedError(GatekeeperException):
    """User not authenticated."""
    def __init__(self, message: str = "Not authenticated"):
        super().__init__("UNAUTHORIZED", message)

class ForbiddenError(GatekeeperException):
    """User not authorized (RBAC)."""
    def __init__(self, message: str = "Permission denied"):
        super().__init__("FORBIDDEN", message)

class CompanyIsolationError(GatekeeperException):
    """Company ID mismatch."""
    def __init__(self):
        super().__init__("COMPANY_MISMATCH", "Company ID mismatch")

class InvalidStatusTransition(GatekeeperException):
    """Invalid ticket status transition."""
    def __init__(self, current_status: str, attempted_status: str):
        message = f"Cannot transition from {current_status} to {attempted_status}"
        super().__init__("INVALID_TRANSITION", message, {
            "current_status": current_status,
            "attempted_status": attempted_status,
        })

class RCANotInDraftError(GatekeeperException):
    """RCA not in draft status."""
    def __init__(self, current_status: str):
        message = f"RCA must be in draft status to edit. Current status: {current_status}"
        super().__init__("RCA_NOT_IN_DRAFT", message, {"status": current_status})

class DuplicateRCAError(GatekeeperException):
    """RCA already exists for ticket."""
    def __init__(self):
        super().__init__("DUPLICATE_RCA", "RCA already exists for this ticket")

def gatekeeper_exception_handler(request, exc: GatekeeperException):
    """Convert Gatekeeper exceptions to HTTP responses."""
    from fastapi.responses import JSONResponse
    from datetime import datetime
    
    status_code_map = {
        "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "COMPANY_MISMATCH": status.HTTP_403_FORBIDDEN,
        "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_TRANSITION": status.HTTP_400_BAD_REQUEST,
        "RCA_NOT_IN_DRAFT": status.HTTP_400_BAD_REQUEST,
        "DUPLICATE_RCA": status.HTTP_400_BAD_REQUEST,
    }
    
    status_code = status_code_map.get(exc.code, status.HTTP_400_BAD_REQUEST)
    
    response = {
        "success": False,
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details if exc.details else None,
        },
        "meta": {
            "timestamp": datetime.utcnow().isoformat(),
        }
    }
    
    return JSONResponse(status_code=status_code, content=response)