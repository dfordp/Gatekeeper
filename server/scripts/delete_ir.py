#!/usr/bin/env python3
"""Delete a specific IR and its related events"""
import sys
from pathlib import Path
from uuid import UUID

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal, IncidentReport, IREvent, Ticket
from core.logger import get_logger

logger = get_logger(__name__)

def delete_ir_by_number(ir_number: str):
    """Delete IR by number and all related events"""
    db = SessionLocal()
    try:
        # Find all IRs with this number
        irs = db.query(IncidentReport).filter(
            IncidentReport.ir_number == ir_number
        ).all()
        
        if not irs:
            print(f"❌ No IR found with number: {ir_number}")
            return False
        
        print(f"Found {len(irs)} IR(s) with number {ir_number}")
        
        deleted_count = 0
        for ir in irs:
            ticket_id = ir.ticket_id
            ir_id = ir.id
            
            print(f"\nDeleting IR {ir.ir_number} (ID: {ir_id}) from ticket {ticket_id}...")
            
            # Delete all related IR events first
            event_count = db.query(IREvent).filter(
                IREvent.incident_report_id == ir_id
            ).delete(synchronize_session=False)
            
            print(f"  ✓ Deleted {event_count} related IR events")
            
            # Delete the IR
            db.delete(ir)
            print(f"  ✓ Deleted IR record")
            
            # Update ticket to remove IR tracking
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if ticket:
                ticket.has_ir = False
                ticket.ir_number = None
                ticket.ir_raised_at = None
                ticket.ir_closed_at = None
                ticket.ir_expected_resolution_date = None
                ticket.ir_notes = None
                print(f"  ✓ Updated ticket to remove IR tracking")
            
            deleted_count += 1
        
        db.commit()
        print(f"\n✅ Successfully deleted {deleted_count} IR(s) and all related events")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete IR: {e}")
        print(f"❌ Error: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python delete_ir.py <ir_number>")
        print("Example: python delete_ir.py 11155213")
        sys.exit(1)
    
    ir_number = sys.argv[1]
    delete_ir_by_number(ir_number)