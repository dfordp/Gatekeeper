from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class SupportSession:
    """Stores session state for a single support request."""
    chat_id: int
    created_at: datetime = field(default_factory=datetime.now)
    
    # Collected information
    user_name: Optional[str] = None
    company_name: Optional[str] = None
    issue_description: Optional[str] = None
    issue_category: Optional[str] = None
    software: Optional[str] = None
    environment: Optional[str] = None
    impact: Optional[str] = None
    
    # File attachments
    attachments: list[str] = field(default_factory=list)
    
    # Process tracking (simplified - just need confirmation and ticket state)
    is_confirmed: bool = False
    ticket_created: bool = False
    ticket_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Export session data for ticket creation."""
        return {
            "chat_id": self.chat_id,
            "user_name": self.user_name,
            "company_name": self.company_name,
            "issue_description": self.issue_description,
            "issue_category": self.issue_category,
            "software": self.software,
            "environment": self.environment,
            "impact": self.impact,
            "attachments": self.attachments,
            "created_at": self.created_at.isoformat(),
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