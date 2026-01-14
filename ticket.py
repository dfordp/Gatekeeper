# ticket.py
import uuid
from datetime import datetime
from typing import Optional
from session import SupportSession

class Ticket:
    """Support ticket object."""
    def __init__(self, session: SupportSession):
        self.ticket_id = str(uuid.uuid4())[:8].upper()
        self.session = session
        self.created_at = datetime.now()
        self.status = "open"
    
    def to_dict(self) -> dict:
        """Serialize ticket for storage/logging."""
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "chat_id": self.session.chat_id,
            "user_name": self.session.user_name,
            "company_name": self.session.company_name,
            "issue_description": self.session.issue_description,
            "issue_category": self.session.issue_category,
            "software": self.session.software,
            "environment": self.session.environment,
            "impact": self.session.impact,
        }
    
    def log_to_file(self, filepath: str = "tickets.log") -> None:
        """Append ticket to a log file (in production, use a database)."""
        import json
        with open(filepath, "a") as f:
            f.write(json.dumps(self.to_dict()) + "\n")


def create_ticket_from_session(session: SupportSession) -> Optional[Ticket]:
    """Create and persist a ticket from a session."""
    # Validate required fields
    if not all([
        session.user_name,
        session.company_name,
        session.issue_description,
        session.issue_category,
        session.software,
        session.environment,
        session.impact,
    ]):
        return None
    
    ticket = Ticket(session)
    ticket.log_to_file()
    
    session.ticket_created = True
    session.ticket_id = ticket.ticket_id
    
    return ticket