# server/utils/date_utils.py
"""
Date handling utilities - working with dates only (no time component)
All dates are in the user's local timezone and stored as date objects
"""
from datetime import datetime, date
from typing import Optional, Any, Dict, List, Union
import logging

logger = logging.getLogger(__name__)


def parse_iso_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parse ISO format date string (YYYY-MM-DD) to date object.
    
    Args:
        date_str: ISO format string like "2026-01-21" or "2026-01-21T14:30:00Z"
        
    Returns:
        date object
        
    Raises:
        ValueError: If format is invalid
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    try:
        # Handle full ISO datetime strings - extract date part only
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        
        # Parse YYYY-MM-DD format
        return datetime.strptime(date_str, '%Y-%m-%d').date()
        
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_str}': {str(e)}")


def to_iso_date(d: Optional[date]) -> Optional[str]:
    """
    Convert date object to ISO string (YYYY-MM-DD).
    
    Args:
        d: date object
        
    Returns:
        ISO format string like "2026-01-21"
    """
    if d is None:
        return None
    
    try:
        if isinstance(d, datetime):
            d = d.date()
        return d.strftime('%Y-%m-%d')
    except Exception as e:
        logger.error(f"Failed to convert {d} to ISO date: {e}")
        return None


def get_today() -> date:
    """Get today's date"""
    return date.today()


def serialize_date_fields(obj: Any) -> Any:
    """
    Recursively convert all date objects in a dict/list to ISO strings (YYYY-MM-DD).
    
    Args:
        obj: A dict, list, or primitive value
        
    Returns:
        The same object with all date fields converted to ISO strings
    """
    if isinstance(obj, dict):
        return {key: serialize_date_fields(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_date_fields(item) for item in obj]
    elif isinstance(obj, date) and not isinstance(obj, datetime):
        return to_iso_date(obj)
    elif isinstance(obj, datetime):
        # Convert datetime to date first
        return to_iso_date(obj.date())
    else:
        return obj