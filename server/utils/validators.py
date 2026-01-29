# server/utils/validators.py
from uuid import UUID

def validate_uuid(value: str) -> UUID:
    """Validate UUID format."""
    try:
        return UUID(value)
    except ValueError:
        raise ValueError(f"Invalid UUID: {value}")

def validate_email(email: str) -> str:
    """Validate email format."""
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError(f"Invalid email: {email}")
    return email.lower()

def validate_ticket_status_transition(current: str, target: str) -> bool:
    """Validate ticket status transitions."""
    # Valid transitions:
    # draft -> open
    # open -> resolved, ir
    # resolved -> closed
    # closed -> reopened
    # reopened -> resolved, closed, ir
    
    valid_transitions = {
        "draft": ["open"],
        "open": ["resolved", "ir", "closed"],
        "resolved": ["closed", "reopened"],
        "closed": ["reopened"],
        "reopened": ["resolved", "closed", "ir"],
        "ir": ["resolved", "closed", "reopened"],
    }
    
    if current not in valid_transitions:
        return False
    
    return target in valid_transitions[current]