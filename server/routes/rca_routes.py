# server/routes/rca_routes.py
"""RCA management routes"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from core.database import SessionLocal
from services.rca_service import RCAService
from utils.exceptions import ValidationError, NotFoundError
from middleware.cache_decorator import cache_endpoint, cache_endpoint_with_body, invalidate_on_mutation


# ==================== REQUEST MODELS ====================

class CreateRCARequest(BaseModel):
    """Request model for creating/updating RCA"""
    root_cause: str = Field(..., min_length=10, description="Root cause description")
    contributing_factors: Optional[List[str]] = Field(None, description="List of contributing factors")
    prevention_measures: Optional[str] = Field(None, description="Prevention measures")
    resolution_steps: Optional[List[str]] = Field(None, description="List of resolution steps")
    rca_attachments: Optional[List[str]] = Field(None, description="File paths for RCA attachments")
    visual_guide: Optional[str] = Field(None, description="Visual guide or documentation")
    created_by_user_id: Optional[str] = Field(None, description="User ID creating RCA")


# ==================== ROUTES ====================

router = APIRouter(prefix="/api/rca", tags=["RCA"])


@router.post("/tickets/{ticket_id}/rca")
@invalidate_on_mutation(tags=["ticket:rca", "ticket:detail", "search:*"])
async def create_rca(
    ticket_id: str,
    request: CreateRCARequest
):
    """
    Create or update RCA for a ticket with attachments and documentation (invalidates related caches).
    
    Args:
        ticket_id: Ticket UUID
        request: RCA request body with all details
    
    Returns:
        Created/updated RCA with metadata
    """
    try:
        result = RCAService.create_or_update_rca(
            ticket_id=ticket_id,
            root_cause_description=request.root_cause,
            contributing_factors=request.contributing_factors,
            prevention_measures=request.prevention_measures,
            resolution_steps=request.resolution_steps,
            rca_attachment_paths=request.rca_attachments,
            created_by_user_id=request.created_by_user_id
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create RCA: {str(e)}")


@router.get("/tickets/{ticket_id}/rca")
@cache_endpoint(ttl=120, tag="ticket:rca", key_params=["ticket_id"])
async def get_rca(ticket_id: str):
    """
    Get RCA details with caching
    
    Args:
        ticket_id: Ticket UUID
    
    Returns:
        RCA details with attachments and metadata
    """
    try:
        rca = RCAService.get_rca_with_details(ticket_id)
        if not rca:
            raise HTTPException(status_code=404, detail="No RCA found for this ticket")
        return rca
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch RCA: {str(e)}")


@router.get("/search")
@cache_endpoint_with_body(
    ttl=120,
    tag="search:rca",
    request_body_fields=["keyword"],
    endpoint_name="search_rcas"
)
async def search_rcas(
    keyword: str,
    company_id: Optional[str] = None,
    limit: int = 5
):
    """
    Search RCAs by keyword in root cause or prevention measures.
    
    Args:
        keyword: Search term
        company_id: Optional company filter
        limit: Max results to return
    
    Returns:
        Search results with RCA details
    """
    try:
        results = RCAService.search_rcas_by_keyword(
            keyword=keyword,
            company_id=company_id,
            limit=limit
        )
        return {
            "query": keyword,
            "total_results": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")