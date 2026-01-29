from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from uuid import UUID
from models.ticket import Ticket
from models.embedding import Embedding
from models.rca import RCA, RCAStatus
from schemas.common import APIResponse
from utils.database import get_db
from dependencies import get_current_role
from services.rbac_service import RBACService, Permission
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{company_id}/analytics/duplicates")
async def get_duplicate_insights(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Get duplicate ticket insights (admin only)."""
    
    # RBAC check
    RBACService.require_permission(current_role, Permission.ANALYTICS_VIEW)
    
    try:
        # Find tickets with similar subjects (simple substring matching)
        # TODO: Use semantic similarity via embeddings
        
        tickets = db.query(Ticket).filter(
            Ticket.company_id == company_id
        ).all()
        
        # Group by category + similar subjects
        duplicates = []
        seen = set()
        
        for i, ticket1 in enumerate(tickets):
            if ticket1.id in seen:
                continue
            
            similar = [ticket1]
            for ticket2 in tickets[i+1:]:
                if ticket2.id in seen:
                    continue
                
                # Simple similarity: same category
                if ticket1.category == ticket2.category:
                    if ticket1.subject.lower() == ticket2.subject.lower():
                        similar.append(ticket2)
                        seen.add(ticket2.id)
            
            if len(similar) > 1:
                seen.add(ticket1.id)
                duplicates.append({
                    "group_id": str(ticket1.id),
                    "count": len(similar),
                    "tickets": [
                        {
                            "id": str(t.id),
                            "ticket_no": t.ticket_no,
                            "subject": t.subject,
                            "status": t.status,
                        }
                        for t in similar
                    ]
                })
        
        return APIResponse(
            success=True,
            data={"duplicates": duplicates},
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"Error getting duplicate insights: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/analytics/categories")
async def get_category_distribution(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Get ticket distribution by category."""
    
    RBACService.require_permission(current_role, Permission.ANALYTICS_VIEW)
    
    try:
        categories = db.query(
            Ticket.category,
            func.count(Ticket.id).label("count")
        ).filter(
            Ticket.company_id == company_id
        ).group_by(
            Ticket.category
        ).all()
        
        data = [
            {
                "category": cat or "uncategorized",
                "count": count
            }
            for cat, count in categories
        ]
        
        return APIResponse(
            success=True,
            data={"categories": data},
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"Error getting category distribution: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/analytics/embeddings")
async def get_embedding_metrics(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Get embedding quality metrics."""
    
    RBACService.require_permission(current_role, Permission.ANALYTICS_VIEW)
    
    try:
        total = db.query(func.count(Embedding.id)).filter(
            Embedding.company_id == company_id
        ).scalar()
        
        active = db.query(func.count(Embedding.id)).filter(
            and_(Embedding.company_id == company_id, Embedding.is_active == True)
        ).scalar()
        
        deprecated = db.query(func.count(Embedding.id)).filter(
            and_(Embedding.company_id == company_id, Embedding.is_active == False)
        ).scalar()
        
        by_source = db.query(
            Embedding.source_type,
            func.count(Embedding.id).label("count")
        ).filter(
            and_(Embedding.company_id == company_id, Embedding.is_active == True)
        ).group_by(
            Embedding.source_type
        ).all()
        
        data = {
            "total": total,
            "active": active,
            "deprecated": deprecated,
            "by_source": [
                {
                    "type": source,
                    "count": count
                }
                for source, count in by_source
            ]
        }
        
        return APIResponse(
            success=True,
            data=data,
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"Error getting embedding metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{company_id}/analytics/approvals")
async def get_approval_analytics(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_role: str = Depends(get_current_role),
) -> APIResponse:
    """Get RCA approval turnaround time analytics."""
    
    RBACService.require_permission(current_role, Permission.ANALYTICS_VIEW)
    
    try:
        # Find RCAs that were submitted and approved
        from sqlalchemy import extract
        from datetime import timedelta
        
        approved_rcas = db.query(RCA).filter(
            and_(RCA.status == RCAStatus.APPROVED, RCA.submitted_at.isnot(None))
        ).all()
        
        turnaround_times = []
        for rca in approved_rcas:
            if rca.submitted_at and rca.approved_at:
                delta = rca.approved_at - rca.submitted_at
                turnaround_times.append(delta.total_seconds() / 3600)  # Convert to hours
        
        pending_rcas = db.query(RCA).filter(
            RCA.status == RCAStatus.PENDING_APPROVAL
        ).count()
        
        avg_turnaround = sum(turnaround_times) / len(turnaround_times) if turnaround_times else 0
        
        data = {
            "avg_turnaround_hours": round(avg_turnaround, 2),
            "pending_count": pending_rcas,
            "approved_count": len(turnaround_times),
        }
        
        return APIResponse(
            success=True,
            data=data,
            meta={"timestamp": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"Error getting approval analytics: {e}")
        raise HTTPException(status_code=400, detail=str(e))