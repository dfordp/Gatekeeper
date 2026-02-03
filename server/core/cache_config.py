# server/core/cache_config.py
"""
Cache configuration with TTL mappings and invalidation rules
"""
from typing import List, Dict, Optional
from enum import Enum


class CacheTTL(str, Enum):
    """Cache TTL constants (in seconds)"""
    # Hot data - frequently changing
    TICKET_LIST = "30"
    TICKET_DETAIL = "60"
    TICKET_STATUS = "10"
    
    # Medium data - moderate changes
    RCA_DETAIL = "120"
    SEARCH_RESULTS = "120"
    ATTACHMENT_METADATA = "300"
    
    # Slower data - infrequent changes
    ANALYTICS = "300"
    USER_LIST = "600"
    USER_DETAIL = "600"
    QUEUE_STATS = "30"
    
    # Static data - rarely changes
    COMPANY_LIST = "3600"
    COMPANY_DETAIL = "3600"


# Cache key patterns
CACHE_KEY_PATTERNS = {
    # Ticket endpoints
    "ticket:list": "ticket:list:company-{company_id}:status-{status}:page-{page}",
    "ticket:detail": "ticket:detail:{ticket_id}:company-{company_id}",
    "ticket:rca": "ticket:rca:{ticket_id}:company-{company_id}",
    "ticket:status": "ticket:status:{ticket_id}",
    
    # Search endpoints
    "search:similar": "search:similar:{query_hash}:company-{company_id}:limit-{limit}",
    "search:rca": "search:rca:{query_hash}:company-{company_id}",
    
    # Analytics
    "analytics": "analytics:company-{company_id}:period-{period}",
    
    # User endpoints
    "user:list": "user:list:company-{company_id}:page-{page}",
    "user:detail": "user:detail:{user_id}:company-{company_id}",
    
    # Company endpoints
    "company:list": "company:list:page-{page}",
    "company:detail": "company:detail:{company_id}",
    
    # Queue
    "queue:stats": "queue:stats:company-{company_id}",
    "queue:status": "queue:status:{task_id}",
}

# Invalidation tag hierarchy (what gets invalidated when)
INVALIDATION_RULES = {
    "ticket:create": {
        "invalidate_tags": ["ticket:list", "analytics", "search:*"],
        "cascade": True,
    },
    "ticket:update": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "ticket:list", "analytics"],
        "cascade": True,
    },
    "ticket:delete": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "ticket:list", "search:*", "analytics"],
        "cascade": True,
    },
    "ticket:status_change": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "ticket:list", "analytics"],
        "cascade": True,
    },
    "rca:create": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "ticket:rca:{ticket_id}", "search:*"],
        "cascade": True,
    },
    "rca:update": {
        "invalidate_tags": ["ticket:rca:{ticket_id}", "ticket:detail:{ticket_id}", "search:*"],
        "cascade": True,
    },
    "rca:delete": {
        "invalidate_tags": ["ticket:rca:{ticket_id}", "ticket:detail:{ticket_id}", "search:*"],
        "cascade": True,
    },
    "attachment:add": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "search:*"],
        "cascade": False,
    },
    "attachment:delete": {
        "invalidate_tags": ["ticket:detail:{ticket_id}", "search:*"],
        "cascade": False,
    },
    "user:create": {
        "invalidate_tags": ["user:list"],
        "cascade": False,
    },
    "user:update": {
        "invalidate_tags": ["user:detail:{user_id}", "user:list"],
        "cascade": False,
    },
    "user:delete": {
        "invalidate_tags": ["user:detail:{user_id}", "user:list"],
        "cascade": False,
    },
}

# DO NOT CACHE these endpoints (sensitive operations)
NO_CACHE_ENDPOINTS = [
    "/api/admin/",
    "/api/auth/",
    "/api/tickets/create",
    "/api/tickets/{ticket_id}/rca",
    "/api/tickets/{ticket_id}/resolution",
    "/api/tickets/{ticket_id}/attachments",
]

# Methods that should never be cached
NO_CACHE_METHODS = ["POST", "PUT", "DELETE", "PATCH"]


def get_ttl(cache_type: str) -> int:
    """Get TTL in seconds for cache type"""
    try:
        return int(CacheTTL[cache_type.upper()].value)
    except KeyError:
        return 60  # Default 60 seconds


def get_invalidation_tags(event_type: str, **kwargs) -> List[str]:
    """Get tags to invalidate for an event"""
    rule = INVALIDATION_RULES.get(event_type, {})
    tags = rule.get("invalidate_tags", [])
    
    # Format tags with provided kwargs
    formatted_tags = []
    for tag in tags:
        # Handle wildcards
        if "*" in tag:
            # Store the pattern for pattern-based invalidation
            formatted_tags.append(tag)
        else:
            # Format specific tags
            try:
                formatted_tags.append(tag.format(**kwargs))
            except KeyError:
                formatted_tags.append(tag)
    
    return formatted_tags


def should_cache_endpoint(method: str, path: str) -> bool:
    """Check if endpoint should be cached"""
    if method in NO_CACHE_METHODS:
        return False
    
    for no_cache_path in NO_CACHE_ENDPOINTS:
        if path.startswith(no_cache_path):
            return False
    
    return True