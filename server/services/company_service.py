# server/services/company_service.py
"""Company management service"""
from typing import Dict, Any, Optional, List
from uuid import UUID

from core.database import SessionLocal, Company, AdminAuditLog
from utils.datetime_utils import to_iso_string
from utils.exceptions import ValidationError, NotFoundError, ConflictError
from core.logger import get_logger

logger = get_logger(__name__)


class CompanyService:
    """Service for managing companies"""
    
    @staticmethod
    def create_company(
        name: str,
        created_by_admin_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new company.
        
        Args:
            name: Company name (must be unique)
            created_by_admin_id: Admin creating the company
            
        Returns:
            Dict with company details
            
        Raises:
            ValidationError: If validation fails
            ConflictError: If company already exists
        """
        db = SessionLocal()
        try:
            # Validate input
            if not name or len(name.strip()) < 2:
                raise ValidationError("Company name must be at least 2 characters")
            
            name = name.strip()
            
            # Check if company already exists
            existing = db.query(Company).filter(Company.name == name).first()
            if existing:
                raise ConflictError(f"Company '{name}' already exists")
            
            # Create company
            company = Company(name=name)
            db.add(company)
            db.commit()
            
            # Audit log
            if created_by_admin_id:
                try:
                    AdminAuditLog.create(
                        admin_user_id=UUID(created_by_admin_id),
                        action="company_created",
                        resource="company",
                        resource_id=str(company.id),
                        changes={"name": name}
                    )
                except Exception as e:
                    logger.warning(f"Failed to create audit log: {e}")
            
            logger.info(f"✓ Company created: {name}")
            
            return {
                "id": str(company.id),
                "name": company.name,
                "created_at": to_iso_string(company.created_at)
            }
            
        except (ValidationError, ConflictError):
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create company: {e}")
            raise ValidationError(f"Failed to create company: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_companies(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get paginated list of companies.
        
        Returns:
            Dict with companies list and total count
        """
        db = SessionLocal()
        try:
            query = db.query(Company)
            total = query.count()
            
            companies = query.order_by(Company.created_at.desc()).limit(limit).offset(offset).all()
            
            companies_data = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "created_at": to_iso_string(c.created_at),
                    "user_count": len(c.users),
                    "ticket_count": len(c.tickets)
                }
                for c in companies
            ]
            
            return {
                "companies": companies_data,
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Failed to get companies: {e}")
            raise ValidationError("Failed to retrieve companies")
        finally:
            db.close()
    
    @staticmethod
    def get_company_by_id(company_id: str) -> Dict[str, Any]:
        """
        Get company details by ID.
        
        Returns:
            Dict with company details
        """
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == UUID(company_id)).first()
            if not company:
                raise NotFoundError("Company not found")
            
            return {
                "id": str(company.id),
                "name": company.name,
                "created_at": to_iso_string(company.created_at),
                "user_count": len(company.users),
                "ticket_count": len(company.tickets)
            }
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get company: {e}")
            raise ValidationError("Failed to retrieve company")
        finally:
            db.close()