# server/routes/company_routes.py
"""Company management routes"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from middleware.auth_middleware import get_current_admin
from services.company_service import CompanyService
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger
from middleware.cache_decorator import cache_endpoint, invalidate_on_mutation

logger = get_logger(__name__)

router = APIRouter(prefix="/api/companies", tags=["Companies"])


class CreateCompanyRequest(BaseModel):
    """Request model for creating a company"""
    name: str = Field(..., min_length=2, description="Company name")


@router.post("/create")
@invalidate_on_mutation(tags=["company:list"])
async def create_company(
    request: CreateCompanyRequest,
    admin_payload: dict = Depends(get_current_admin)
):
    """Create a new company"""
    try:
        result = CompanyService.create_company(
            name=request.name,
            created_by_admin_id=admin_payload.get("sub")
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating company: {e}")
        raise HTTPException(status_code=500, detail="Failed to create company")


@router.get("")
@cache_endpoint(ttl=3600, tag="company:list", key_params=[])
async def get_companies(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_payload: dict = Depends(get_current_admin)
):
    """Get list of all companies"""
    try:
        result = CompanyService.get_companies(limit=limit, offset=offset)
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting companies: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve companies")


@router.get("/{company_id}")
@cache_endpoint(ttl=3600, tag="company:detail", key_params=["company_id"])
async def get_company(
    company_id: str,
    admin_payload: dict = Depends(get_current_admin)
):
    """Get company details"""
    try:
        result = CompanyService.get_company_by_id(company_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting company: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve company")