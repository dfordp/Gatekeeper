# server/utils/validators.py
"""Input validation utilities"""
import re
from .exceptions import ValidationError


def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.
    Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    
    Args:
        password: Password to validate
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If validation fails
    """
    if len(password) < 12:
        raise ValidationError("Password must be at least 12 characters long")
    
    if not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        raise ValidationError("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        raise ValidationError("Password must contain at least one digit")
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        raise ValidationError("Password must contain at least one special character")
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email to validate
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If invalid
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError("Invalid email format")
    return True


def validate_full_name(name: str) -> bool:
    """
    Validate full name.
    
    Args:
        name: Name to validate
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: If invalid
    """
    name = name.strip()
    if len(name) < 2:
        raise ValidationError("Full name must be at least 2 characters long")
    if len(name) > 255:
        raise ValidationError("Full name must not exceed 255 characters")
    return True