# server/utils/exceptions.py
"""Custom exceptions for Gatekeeper"""


class GatekeeperException(Exception):
    """Base exception for Gatekeeper"""
    
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationError(GatekeeperException):
    """Validation error"""
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400)


class NotFoundError(GatekeeperException):
    """Resource not found"""
    def __init__(self, message: str):
        super().__init__(message, "NOT_FOUND", 404)


class UnauthorizedError(GatekeeperException):
    """Unauthorized access"""
    def __init__(self, message: str):
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(GatekeeperException):
    """Forbidden access"""
    def __init__(self, message: str):
        super().__init__(message, "FORBIDDEN", 403)


class ConflictError(GatekeeperException):
    """Resource conflict (e.g., duplicate)"""
    def __init__(self, message: str):
        super().__init__(message, "CONFLICT", 409)