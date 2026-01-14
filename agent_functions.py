from typing import Any, Dict
from session import get_or_create_session
from ticket import create_ticket_from_session

CATEGORIES = [
    "Login / Access",
    "License",
    "Installation",
    "Upload or Save",
    "Workflow",
    "Performance",
    "Integration",
    "Data / Configuration",
    "Other"
]

ENVIRONMENTS = ["Production", "Test / UAT", "Local system"]
IMPACT_LEVELS = ["Completely blocked", "Partially blocked", "Slow but usable"]


def classify_issue_category(text: str) -> str:
    """Silently classify issue based on keywords."""
    desc_lower = text.lower()
    
    category_keywords = {
        "Login / Access": ["login", "access", "password", "authenticate", "credential", "sign in", "sign-in"],
        "License": ["license", "licence", "subscription", "expired", "renewal", "license key"],
        "Installation": ["install", "setup", "deploy", "configuration", "uninstall", "reinstall"],
        "Upload or Save": ["upload", "save", "download", "export", "import", "saving"],
        "Workflow": ["workflow", "process", "step", "approval", "automation", "workflow"],
        "Performance": ["slow", "lag", "speed", "performance", "timeout", "slow", "sluggish"],
        "Integration": ["integration", "api", "sync", "connect", "plugin", "integrate"],
        "Data / Configuration": ["data", "config", "setting", "field", "code", "configuration"],
    }
    
    for category, keywords in category_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    
    return "Other"


async def _save_any_field(field_name: str, value: str, *, chat_id: int) -> dict:
    """
    Generic function to save any field data.
    Allows LLM flexibility while keeping data collection silent.
    """
    session = get_or_create_session(chat_id)
    field_name = field_name.lower().strip()
    
    if "description" in field_name or "issue" in field_name:
        session.issue_description = value
        session.issue_category = classify_issue_category(value)
        return {"ok": True, "field": "issue_description", "value": value}
    
    elif "name" in field_name:
        session.user_name = value
        return {"ok": True, "field": "user_name", "value": value}
    
    elif "company" in field_name:
        session.company_name = value
        return {"ok": True, "field": "company_name", "value": value}
    
    elif "software" in field_name or "system" in field_name:
        session.software = value
        return {"ok": True, "field": "software", "value": value}
    
    elif "environment" in field_name:
        value_lower = value.lower()
        if "prod" in value_lower:
            session.environment = "Production"
        elif "uat" in value_lower or "test" in value_lower:
            session.environment = "Test / UAT"
        elif "local" in value_lower:
            session.environment = "Local system"
        else:
            return {"ok": False, "error": "Invalid environment"}
        return {"ok": True, "field": "environment", "value": session.environment}
    
    elif "impact" in field_name:
        value_lower = value.lower()
        if "completely" in value_lower or "fully" in value_lower or "blocked" in value_lower:
            session.impact = "Completely blocked"
        elif "partial" in value_lower:
            session.impact = "Partially blocked"
        else:
            session.impact = "Slow but usable"
        return {"ok": True, "field": "impact", "value": session.impact}
    
    else:
        return {"ok": False, "error": "Unknown field"}


async def _confirm_and_create_ticket(confirmed: bool, *, chat_id: int) -> dict:
    """Confirm summary and create ticket if all info present."""
    session = get_or_create_session(chat_id)
    session.is_confirmed = confirmed
    
    if not confirmed:
        return {"ok": True, "confirmed": False}
    
    # Check all required fields
    if not all([
        session.user_name,
        session.company_name,
        session.issue_description,
        session.software,
        session.environment,
        session.impact
    ]):
        return {
            "ok": False,
            "error": "Missing required information"
        }
    
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


async def _get_session_data(*, chat_id: int) -> dict:
    """Get current session data."""
    session = get_or_create_session(chat_id)
    return {
        "user_name": session.user_name,
        "company_name": session.company_name,
        "issue_description": session.issue_description,
        "issue_category": session.issue_category,
        "software": session.software,
        "environment": session.environment,
        "impact": session.impact,
        "attachments": len(session.attachments),
    }


# Tool definitions
FUNCTION_DEFS: list[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_any_field",
            "description": "Save any support session field (name, company, software, environment, impact, description).",
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
]

FUNCTION_MAP: dict[str, Any] = {
    "save_any_field": _save_any_field,
    "confirm_and_create_ticket": _confirm_and_create_ticket,
    "get_session_data": _get_session_data,
}