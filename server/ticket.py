# ticket.py - ENHANCED with edit functionality
import uuid
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from utils.datetime_utils import to_iso_date
from session import SupportSession, IssueCategory, Environment, ImpactLevel

class Ticket:
    """Support ticket object."""
    def __init__(self, session: SupportSession, ticket_id: str = None):
        self.ticket_id = ticket_id or str(uuid.uuid4())[:8].upper()
        self.session = session
        self.created_at = datetime.today()
        self.updated_at = datetime.today()
        self.status = "open"
    
    def to_dict(self) -> dict:
        """Serialize ticket for storage/logging."""
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "created_at": to_iso_date(self.created_at),
            "updated_at": to_iso_date(self.updated_at),
            "chat_id": self.session.chat_id,
            "user_name": self.session.user_name,
            "company_name": self.session.company_name,
            "issue_description": self.session.issue_description,
            "issue_category": self.session.issue_category.value if isinstance(self.session.issue_category, Enum) else self.session.issue_category,
            "software": self.session.software,
            "environment": self.session.environment.value if isinstance(self.session.environment, Enum) else self.session.environment,
            "impact": self.session.impact.value if isinstance(self.session.impact, Enum) else self.session.impact,
        }
    
    def log_to_file(self, filepath: str = "tickets.log") -> None:
        """Append ticket to a log file (in production, use a database)."""
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


def load_ticket_by_id(ticket_id: str, filepath: str = "tickets.log") -> Optional[Dict[str, Any]]:
    """Load ticket data from log file by ticket ID."""
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data.get("ticket_id") == ticket_id.upper():
                        return data
    except Exception as e:
        return None
    
    return None


def update_ticket(ticket_id: str, updates: Dict[str, Any], filepath: str = "tickets.log") -> bool:
    """Update an existing ticket by replacing its entry in the log file."""
    if not os.path.exists(filepath):
        return False
    
    try:
        # Read all tickets
        all_tickets = []
        with open(filepath, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data.get("ticket_id") == ticket_id.upper():
                        # Update this ticket
                        data.update(updates)
                        data["updated_at"] = to_iso_date(datetime.today())
                    all_tickets.append(data)
        
        # Write all tickets back
        with open(filepath, "w") as f:
            for ticket_data in all_tickets:
                f.write(json.dumps(ticket_data) + "\n")
        
        return True
    except Exception as e:
        return False