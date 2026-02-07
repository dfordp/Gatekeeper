# server/services/async_company_service.py
"""Async Company Service - NO asyncio.to_thread()"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.async_database import AsyncSessionLocal
from core.database import Company
from core.logger import get_logger
from utils.exceptions import ValidationError, NotFoundError, ConflictError

logger = get_logger(__name__)


class AsyncCompanyService:
    """Fully async company operations"""
    
    @staticmethod
    async def create_company(name: str) -> Dict[str, Any]:
        """Create a new company"""
        if not name or len(name.strip()) < 2:
            raise ValidationError("Company name must be at least 2 characters")
        
        async with AsyncSessionLocal() as session:
            try:
                # Check if company exists
                result = await session.execute(
                    select(Company).where(Company.name == name.strip())
                )
                if result.scalar_one_or_none():
                    raise ConflictError(f"Company '{name}' already exists")
                
                company = Company(name=name.strip())
                session.add(company)
                await session.commit()
                
                logger.info(f"✓ Company created: {name}")
                
                return {
                    "id": str(company.id),
                    "name": company.name,
                    "created_at": str(company.created_at)
                }
            
            except (ValidationError, ConflictError):
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error creating company: {e}")
                raise ValidationError(f"Failed to create company: {str(e)}")
    
    @staticmethod
    async def get_company(company_id: str) -> Dict[str, Any]:
        """Get company by ID"""
        async with AsyncSessionLocal() as session:
            try:
                company = await session.get(Company, UUID(company_id))
                if not company:
                    raise NotFoundError(f"Company not found")
                
                return {
                    "id": str(company.id),
                    "name": company.name,
                    "created_at": str(company.created_at)
                }
            
            except NotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error fetching company: {e}")
                raise ValidationError(f"Failed to fetch company: {str(e)}")
    
    @staticmethod
    async def list_companies(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all companies"""
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(Company).limit(limit).offset(offset)
                )
                companies = result.scalars().all()
                
                return [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "created_at": str(c.created_at)
                    }
                    for c in companies
                ]
            
            except Exception as e:
                logger.error(f"Error listing companies: {e}")
                raise ValidationError(f"Failed to list companies: {str(e)}")