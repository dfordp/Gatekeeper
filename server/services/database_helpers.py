
# server/services/database_helpers.py
"""Database helper functions for optimized queries"""
import logging
from typing import List, Optional, Any, Dict
from uuid import UUID
from sqlalchemy.orm import Session

from core.database import (
    Ticket, Company, User, IncidentReport, 
    RootCauseAnalysis, TicketEvent
)
from core.query_optimizer import QueryOptimizer, BatchQuery
from core.db_performance_monitor import get_query_monitor
import time

logger = logging.getLogger(__name__)
monitor = get_query_monitor()


class TicketQueries:
    """Optimized query helpers for Ticket operations"""
    
    @staticmethod
    def get_ticket_with_relations(
        db: Session,
        ticket_id: UUID
    ) -> Optional[Ticket]:
        """Get ticket with all important relationships loaded"""
        start = time.perf_counter()
        
        result = QueryOptimizer.get_with_relationships(
            db,
            Ticket,
            {"id": ticket_id},
            relationships=[
                Ticket.company,
                Ticket.raised_by_user,
                Ticket.assigned_engineer
            ]
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("get_ticket_with_relations", elapsed_ms)
        
        return result
    
    @staticmethod
    def get_company_tickets(
        db: Session,
        company_id: UUID,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Ticket]:
        """Get tickets for a company with relationships"""
        start = time.perf_counter()
        
        filter_by = {"company_id": company_id}
        if status:
            filter_by["status"] = status
        
        results = QueryOptimizer.list_with_relationships(
            db,
            Ticket,
            filter_by=filter_by,
            relationships=[Ticket.company, Ticket.raised_by_user],
            order_by=Ticket.created_at.desc(),
            limit=limit,
            offset=offset
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query(f"get_company_tickets({status or 'all'})", elapsed_ms)
        
        return results
    
    @staticmethod
    def count_company_tickets(
        db: Session,
        company_id: UUID,
        status: Optional[str] = None
    ) -> int:
        """Efficiently count tickets without loading them"""
        start = time.perf_counter()
        
        filter_by = {"company_id": company_id}
        if status:
            filter_by["status"] = status
        
        count = QueryOptimizer.count_efficient(db, Ticket, filter_by)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query(f"count_company_tickets({status or 'all'})", elapsed_ms)
        
        return count


class CompanyQueries:
    """Optimized query helpers for Company operations"""
    
    @staticmethod
    def get_company_with_users(
        db: Session,
        company_id: UUID
    ) -> Optional[Company]:
        """Get company with users loaded"""
        start = time.perf_counter()
        
        result = QueryOptimizer.get_with_relationships(
            db,
            Company,
            {"id": company_id},
            relationships=[Company.users]
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("get_company_with_users", elapsed_ms)
        
        return result


class UserQueries:
    """Optimized query helpers for User operations"""
    
    @staticmethod
    def get_users_by_company(
        db: Session,
        company_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        """Get users for company"""
        start = time.perf_counter()
        
        results = QueryOptimizer.list_with_relationships(
            db,
            User,
            filter_by={"company_id": company_id},
            order_by=User.name,
            limit=limit,
            offset=offset
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("get_users_by_company", elapsed_ms)
        
        return results
    
    @staticmethod
    def batch_get_users(
        db: Session,
        user_ids: List[UUID]
    ) -> List[User]:
        """Get multiple users by IDs"""
        start = time.perf_counter()
        
        results = BatchQuery.batch_get_by_ids(db, User, user_ids)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("batch_get_users", elapsed_ms)
        
        return results


class IncidentReportQueries:
    """Optimized query helpers for IncidentReport operations"""
    
    @staticmethod
    def get_ticket_irs(
        db: Session,
        ticket_id: UUID
    ) -> List[IncidentReport]:
        """Get all IRs for a ticket"""
        start = time.perf_counter()
        
        results = QueryOptimizer.list_with_relationships(
            db,
            IncidentReport,
            filter_by={"ticket_id": ticket_id},
            relationships=[IncidentReport.ticket]
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("get_ticket_irs", elapsed_ms)
        
        return results
    
    @staticmethod
    def count_open_irs(db: Session, company_id: UUID = None) -> int:
        """Count open IRs, optionally filtered by company"""
        start = time.perf_counter()
        
        filter_by = {"status": "open"}
        
        count = QueryOptimizer.count_efficient(db, IncidentReport, filter_by)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("count_open_irs", elapsed_ms)
        
        return count


class RCAQueries:
    """Optimized query helpers for RCA operations"""
    
    @staticmethod
    def get_ticket_rca(
        db: Session,
        ticket_id: UUID
    ) -> Optional[RootCauseAnalysis]:
        """Get RCA for ticket"""
        start = time.perf_counter()
        
        result = QueryOptimizer.get_with_relationships(
            db,
            RootCauseAnalysis,
            {"ticket_id": ticket_id},
            relationships=[
                RootCauseAnalysis.ticket,
                RootCauseAnalysis.created_by_user
            ]
        )
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record_query("get_ticket_rca", elapsed_ms)
        
        return result