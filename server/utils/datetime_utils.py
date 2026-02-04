# server/utils/datetime_utils.py
"""
Strict UTC datetime handling to prevent timezone drift.
All dates must be ISO format with timezone info.
"""
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Union
import logging

logger = logging.getLogger(__name__)


def parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO format date string to UTC datetime (naive).
    
    Requirements:
    - Must have timezone info (ends with 'Z' or ±HH:MM)
    - Returns naive datetime (already converted to UTC)
    
    Args:
        date_str: ISO format string like "2026-01-21T13:58:00Z"
        
    Returns:
        UTC datetime object (naive, no tzinfo)
        
    Raises:
        ValueError: If date lacks timezone info or format is invalid
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # VALIDATION: Must have timezone indicator
    if not date_str.endswith('Z') and '+' not in date_str and date_str.count('-') < 2:
        raise ValueError(
            f"Date must be ISO format WITH timezone (Z or ±HH:MM). Got: {date_str}"
        )
    
    try:
        # Normalize 'Z' to '+00:00' for fromisoformat
        normalized = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(normalized)
        
        # Convert to UTC and strip timezone info (store as naive UTC)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        logger.debug(f"✓ Parsed date: {date_str} → {dt} (UTC)")
        return dt
        
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_str}': {str(e)}")


def to_iso_string(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert datetime to ISO string with UTC timezone.
    
    Args:
        dt: datetime object (assumed UTC if naive)
        
    Returns:
        ISO format string with 'Z' suffix (UTC)
    """
    if dt is None:
        return None
    
    try:
        # If naive, assume it's UTC; if aware, convert to UTC
        if dt.tzinfo is None:
            dt_utc = dt
        else:
            dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        # Format with 'Z' suffix
        iso_str = dt_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        return iso_str
        
    except Exception as e:
        logger.error(f"Failed to convert {dt} to ISO: {e}")
        return None


def get_utc_now() -> datetime:
    """
    Get current UTC time as naive datetime.
    Use this instead of datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def serialize_datetime_fields(obj: Any) -> Any:
    """
    Recursively convert all datetime objects in a dict/list to ISO strings with 'Z' suffix.
    
    This ensures all datetime fields sent to the frontend have timezone info.
    
    Args:
        obj: A dict, list, or primitive value
        
    Returns:
        The same object with all datetime fields converted to ISO strings with 'Z'
        
    Example:
        response_dict = serialize_datetime_fields({
            "created_at": datetime(2026, 1, 21, 4, 28),
            "ticket": {
                "closed_at": datetime(2026, 1, 24, 4, 28)
            },
            "events": [
                {"timestamp": datetime(2026, 2, 4, 8, 45)}
            ]
        })
        # All datetime objects are now ISO strings with 'Z'
    """
    if isinstance(obj, dict):
        return {key: serialize_datetime_fields(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime_fields(item) for item in obj]
    elif isinstance(obj, datetime):
        return to_iso_string(obj)
    else:
        return obj