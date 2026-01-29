# agent_functions.py - IMPROVED with validation
from typing import Any, Dict
from session import (
    get_or_create_session, 
    IssueCategory, 
    Environment, 
    ImpactLevel,
    ValidationError,
    SUPPORTED_SOFTWARE
)
from ticket import create_ticket_from_session

# Category detection from keywords (used for silent classification)
# More comprehensive and dynamic keyword patterns for engineering/PLM software support
CATEGORY_KEYWORDS = {
    IssueCategory.LOGIN_ACCESS: [
        "login", "access", "password", "authenticate", "credential", "sign in", "sign-in",
        "unable to log", "cannot log", "login failed", "access denied", "unauthorized",
        "authentication", "session expired", "connection refused", "permission denied",
        "cannot connect", "connection timeout", "unreachable", "offline"
    ],
    IssueCategory.LICENSE: [
        "license", "licence", "subscription", "expired", "renewal", "license key",
        "finding license", "error finding", "license expired", "license invalid",
        "license server", "license checkout", "license unavailable", "license limit",
        "license exceeded", "concurrent users", "seat", "checkout", "license manager",
        "no license available", "license not found"
    ],
    IssueCategory.INSTALLATION: [
        "install", "setup", "deploy", "configuration", "uninstall", "reinstall",
        "installer", "installation failed", "setup failed", "cannot install",
        "dependency", "missing file", "corrupt", "installation error", "setup error",
        "upgrade", "patch", "update failed", "installation path", "system requirement",
        "compatibility", "version mismatch"
    ],
    IssueCategory.UPLOAD_SAVE: [
        "upload", "save", "download", "export", "import", "saving",
        "cannot save", "save failed", "upload failed", "download failed",
        "attachment", "file transfer", "disk space", "permission", "write error",
        "file locked", "file in use", "disk full", "storage", "backup",
        "export error", "import error", "file format", "conversion"
    ],
    IssueCategory.WORKFLOW: [
        "workflow", "process", "step", "approval", "automation", "task",
        "workflow failed", "process stuck", "approval pending", "notification",
        "status update", "workflow error", "process error", "automation rule",
        "action item", "routing", "escalation", "lifecycle", "state transition",
        "workflow engine", "business rule"
    ],
    IssueCategory.PERFORMANCE: [
        "slow", "lag", "speed", "performance", "timeout", "sluggish", "hanging",
        "freeze", "crash", "memory", "cpu", "resource", "slow response",
        "loading slow", "rendering slow", "query slow", "database slow",
        "high latency", "bottleneck", "throughput", "responsiveness",
        "hang", "unresponsive", "junk", "garbage collection"
    ],
    IssueCategory.INTEGRATION: [
        "integration", "api", "sync", "connect", "plugin", "integrate",
        "integration failed", "sync error", "connection error", "api error",
        "webhook", "rest", "soap", "data exchange", "third party",
        "external system", "interface", "middleware", "integration point",
        "data sync", "real-time sync", "background sync"
    ],
    IssueCategory.DATA_CONFIG: [
        "data", "config", "setting", "field", "code", "configuration",
        "data corruption", "config error", "field missing", "invalid data",
        "data lost", "data inconsistent", "config file", "parameter",
        "environment variable", "property", "attribute", "metadata",
        "custom field", "mapping", "validation", "schema"
    ],
}

def classify_issue_category(text: str) -> IssueCategory:
    """Classify issue based on keywords - always returns valid enum."""
    desc_lower = text.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    
    return IssueCategory.OTHER

async def _save_any_field(field_name: str, value: str, *, chat_id: int) -> dict:
    """Save any field with validation."""
    session = get_or_create_session(chat_id)
    field_name = field_name.lower().strip()
    
    try:
        if "description" in field_name or "issue" in field_name:
            session.issue_description = value
            session.issue_category = classify_issue_category(value)
            return {
                "ok": True, 
                "field": "issue_description", 
                "value": value,
                "category": session.issue_category.value
            }
        
        elif "name" in field_name and "company" not in field_name:
            session.user_name = value
            return {"ok": True, "field": "user_name", "value": value}
        
        elif "company" in field_name:
            session.company_name = value
            return {"ok": True, "field": "company_name", "value": value}
        
        elif "software" in field_name or "system" in field_name:
            session.software = value
            return {"ok": True, "field": "software", "value": session.software}
        
        elif "environment" in field_name:
            session.environment = value
            return {"ok": True, "field": "environment", "value": session.environment.value}
        
        elif "impact" in field_name:
            session.impact = value
            return {"ok": True, "field": "impact", "value": session.impact.value}
        
        else:
            return {"ok": False, "error": f"Unknown field: {field_name}"}
    
    except ValidationError as e:
        return {"ok": False, "error": str(e)}

async def _confirm_and_create_ticket(confirmed: bool, *, chat_id: int) -> dict:
    """Confirm summary and create ticket with validation."""
    session = get_or_create_session(chat_id)
    session.is_confirmed = confirmed
    
    if not confirmed:
        return {"ok": True, "confirmed": False}
    
    # Check all required fields are present and valid
    required_fields = {
        "user_name": session.user_name,
        "company_name": session.company_name,
        "issue_description": session.issue_description,
        "software": session.software,
        "environment": session.environment,
        "impact": session.impact
    }
    
    missing = [name for name, value in required_fields.items() if not value]
    
    if missing:
        return {
            "ok": False,
            "error": f"Missing required information: {', '.join(missing)}"
        }
    
    try:
        ticket = create_ticket_from_session(session)
        if ticket:
            session.ticket_created = True
            return {
                "ok": True,
                "confirmed": True,
                "ticket_id": ticket.ticket_id,
            }
        else:
            return {"ok": False, "error": "Could not create ticket"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def _get_session_data(*, chat_id: int) -> dict:
    """Get current session data with type safety."""
    session = get_or_create_session(chat_id)
    return {
        "user_name": session.user_name,
        "company_name": session.company_name,
        "issue_description": session.issue_description,
        "issue_category": session.issue_category.value if session.issue_category else None,
        "software": session.software,
        "environment": session.environment.value if session.environment else None,
        "impact": session.impact.value if session.impact else None,
        "attachments_count": len(session.attachments),
        "completeness": _calculate_completeness(session),
    }

def _calculate_completeness(session) -> dict:
    """Calculate what's been collected."""
    fields = {
        "user_name": session.user_name is not None,
        "company_name": session.company_name is not None,
        "issue_description": session.issue_description is not None,
        "software": session.software is not None,
        "environment": session.environment is not None,
        "impact": session.impact is not None,
    }
    collected = sum(1 for v in fields.values() if v)
    return {
        "collected": collected,
        "total": len(fields),
        "percentage": (collected / len(fields)) * 100,
        "missing_fields": [k for k, v in fields.items() if not v]
    }

def _get_available_options() -> dict:
    """Return all available enum options dynamically."""
    return {
        "environments": [e.value for e in Environment],
        "impact_levels": [e.value for e in ImpactLevel],
        "categories": [e.value for e in IssueCategory],
        "software": list(SUPPORTED_SOFTWARE.values()),
    }

# Tool definitions with validation
FUNCTION_DEFS: list[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_any_field",
            "description": "Save any support session field with validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "Field to save: 'user name', 'company', 'issue description', 'software', 'environment', or 'impact'"
                    },
                    "value": {"type": "string", "description": "The value to save"}
                },
                "required": ["field_name", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_and_create_ticket",
            "description": "Confirm the summary and create a support ticket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {"type": "boolean", "description": "True if user confirms the summary"}
                },
                "required": ["confirmed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_data",
            "description": "Get current session data for summary display.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_options",
            "description": "Get all available enum options (environments, impact levels, categories, software).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

FUNCTION_MAP: dict[str, Any] = {
    "save_any_field": _save_any_field,
    "confirm_and_create_ticket": _confirm_and_create_ticket,
    "get_session_data": _get_session_data,
    "get_available_options": _get_available_options,
}