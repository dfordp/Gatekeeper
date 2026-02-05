# session.py - CORRECTED with validation and fixes
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

from utils.datetime_utils import to_iso_date

# Define all enum options as dynamic sources
class Environment(str, Enum):
    PRODUCTION = "Production"
    TEST_UAT = "Test / UAT"
    LOCAL = "Local system"

class ImpactLevel(str, Enum):
    COMPLETELY_BLOCKED = "Completely blocked"
    PARTIALLY_BLOCKED = "Partially blocked"
    SLOW_USABLE = "Slow but usable"

class IssueCategory(str, Enum):
    LOGIN_ACCESS = "Login / Access"
    LICENSE = "License"
    INSTALLATION = "Installation"
    UPLOAD_SAVE = "Upload or Save"
    WORKFLOW = "Workflow"
    PERFORMANCE = "Performance"
    INTEGRATION = "Integration"
    DATA_CONFIG = "Data / Configuration"
    OTHER = "Other"

# Dynamic software registry (can be loaded from database/config)
# Maps lowercase keywords to canonical software names
SUPPORTED_SOFTWARE = {
    "teamcenter": "Teamcenter",
    "creo": "Creo",
    "nx": "NX",
    "or-cad": "OR-CAD",
    "orcad": "OR-CAD",
    "autocad": "AutoCAD",
    "fusion": "Fusion 360",
    "solidworks": "SolidWorks",
    "inventor": "Inventor",
    "richclient": "Rich Client",  # Rich Client is part of Teamcenter
    "rich client": "Rich Client",
    "activeworkspace": "Active Workspace",  # Active Workspace is also Teamcenter
    "active workspace": "Active Workspace",
}

class ValidationError(Exception):
    """Custom validation error."""
    pass

def validate_string(value: str, field_name: str, min_len: int = 1, max_len: int = 500) -> str:
    """Validate string input."""
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    value = value.strip()
    
    if len(value) < min_len:
        raise ValidationError(f"{field_name} is too short (minimum {min_len} characters)")
    
    if len(value) > max_len:
        raise ValidationError(f"{field_name} exceeds maximum length ({max_len} characters)")
    
    # Prevent injection/hallucination by checking for reasonable character sets
    if not all(c.isalnum() or c.isspace() or c in "'-@.," for c in value):
        raise ValidationError(f"{field_name} contains invalid characters")
    
    return value

def validate_environment(value: str) -> Environment:
    """Validate and convert environment value."""
    value_lower = value.lower().strip()
    
    # Map user input to enum
    mapping = {
        "prod": Environment.PRODUCTION,
        "production": Environment.PRODUCTION,
        "uat": Environment.TEST_UAT,
        "test": Environment.TEST_UAT,
        "local": Environment.LOCAL,
    }
    
    for key, enum_val in mapping.items():
        if key in value_lower:
            return enum_val
    
    raise ValidationError(f"Environment must be one of: {', '.join([e.value for e in Environment])}")

def validate_impact(value: str) -> ImpactLevel:
    """Validate and convert impact value."""
    value_lower = value.lower()
    
    # Strict mapping to enum
    if any(word in value_lower for word in ["completely", "fully", "blocked", "unable"]):
        return ImpactLevel.COMPLETELY_BLOCKED
    elif any(word in value_lower for word in ["partial"]):
        return ImpactLevel.PARTIALLY_BLOCKED
    elif any(word in value_lower for word in ["slow", "sluggish", "usable"]):
        return ImpactLevel.SLOW_USABLE
    
    raise ValidationError(f"Impact must be one of: {', '.join([e.value for e in ImpactLevel])}")

def validate_software(value: str) -> str:
    """Validate software against known list."""
    if not value:
        raise ValidationError("Software cannot be empty")
    
    value_lower = value.lower().strip()
    
    # Check if matches known software (use longest match to avoid partial matches)
    matches = []
    for keyword, software_name in SUPPORTED_SOFTWARE.items():
        if keyword in value_lower:
            matches.append((len(keyword), software_name))
    
    if matches:
        # Return the match with the longest keyword (most specific)
        matches.sort(reverse=True)
        return matches[0][1]
    
    # If not in list, raise error - don't hallucinate
    supported = sorted(set(SUPPORTED_SOFTWARE.values()))
    raise ValidationError(f"Software not recognized. Supported: {', '.join(supported)}")

@dataclass
class SupportSession:
    """Stores session state with validation."""
    chat_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Collected information - validated on assignment
    _user_name: Optional[str] = None
    _company_name: Optional[str] = None
    _issue_description: Optional[str] = None
    _issue_category: Optional[IssueCategory] = None
    _software: Optional[str] = None
    _environment: Optional[Environment] = None
    _impact: Optional[ImpactLevel] = None
    
    # File attachments
    attachments: list[str] = field(default_factory=list)
    
    # Process tracking
    is_confirmed: bool = False
    ticket_created: bool = False
    ticket_id: Optional[str] = None
    summary_shown: bool = False
    edit_mode: bool = False
    edit_ticket_id: Optional[str] = None
    edit_ticket_data: Optional[dict] = None

    # Properties with validation
    @property
    def user_name(self) -> Optional[str]:
        return self._user_name
    
    @user_name.setter
    def user_name(self, value: str) -> None:
        if value is None:
            self._user_name = None
        else:
            self._user_name = validate_string(value, "User name", min_len=2, max_len=100)
    
    @property
    def company_name(self) -> Optional[str]:
        return self._company_name
    
    @company_name.setter
    def company_name(self, value: str) -> None:
        if value is None:
            self._company_name = None
        else:
            self._company_name = validate_string(value, "Company name", min_len=2, max_len=150)
    
    @property
    def issue_description(self) -> Optional[str]:
        return self._issue_description
    
    @issue_description.setter
    def issue_description(self, value: str) -> None:
        if value is None:
            self._issue_description = None
        else:
            self._issue_description = validate_string(value, "Issue description", min_len=10, max_len=2000)
    
    @property
    def issue_category(self) -> Optional[IssueCategory]:
        return self._issue_category
    
    @issue_category.setter
    def issue_category(self, value: IssueCategory) -> None:
        if isinstance(value, str):
            # Try to match against enum values
            for category in IssueCategory:
                if category.value == value:
                    self._issue_category = category
                    return
            raise ValidationError(f"Invalid category: {value}")
        elif isinstance(value, IssueCategory):
            self._issue_category = value
        elif value is None:
            self._issue_category = None
        else:
            raise ValidationError("Category must be IssueCategory enum")
    
    @property
    def software(self) -> Optional[str]:
        return self._software
    
    @software.setter
    def software(self, value: str) -> None:
        if value is None:
            self._software = None
        else:
            self._software = validate_software(value)
    
    @property
    def environment(self) -> Optional[Environment]:
        return self._environment
    
    @environment.setter
    def environment(self, value) -> None:
        if isinstance(value, str):
            self._environment = validate_environment(value)
        elif isinstance(value, Environment):
            self._environment = value
        elif value is None:
            self._environment = None
        else:
            raise ValidationError("Environment must be Environment enum or string")
    
    @property
    def impact(self) -> Optional[ImpactLevel]:
        return self._impact
    
    @impact.setter
    def impact(self, value) -> None:
        if isinstance(value, str):
            self._impact = validate_impact(value)
        elif isinstance(value, ImpactLevel):
            self._impact = value
        elif value is None:
            self._impact = None
        else:
            raise ValidationError("Impact must be ImpactLevel enum or string")
    
    def to_dict(self) -> dict:
        """Export session data for ticket creation."""
        return {
            "chat_id": self.chat_id,
            "user_name": self.user_name,
            "company_name": self.company_name,
            "issue_description": self.issue_description,
            "issue_category": self.issue_category.value if self.issue_category else None,
            "software": self.software,
            "environment": self.environment.value if self.environment else None,
            "impact": self.impact.value if self.impact else None,
            "attachments": self.attachments,
            "created_at": to_iso_date(self.created_at),
        }

# Global session store (in production, use Redis or database)
sessions: dict[int, SupportSession] = {}

def get_or_create_session(chat_id: int) -> SupportSession:
    """Get or create a session for a chat."""
    if chat_id not in sessions:
        sessions[chat_id] = SupportSession(chat_id=chat_id)
    return sessions[chat_id]

def clear_session(chat_id: int) -> None:
    """Clear a session."""
    sessions.pop(chat_id, None)