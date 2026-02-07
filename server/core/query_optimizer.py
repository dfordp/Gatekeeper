# server/core/query_optimizer.py
"""Database query optimization utilities and patterns"""
import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, List
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Utilities for optimizing database queries"""
    
    @staticmethod
    def log_query_time(threshold_ms: float = 100):
        """
        Decorator to log slow queries.
        
        Args:
            threshold_ms: Log queries taking longer than this (milliseconds)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                
                if elapsed_ms > threshold_ms:
                    logger.warning(
                        f"Slow query in {func.__name__}: {elapsed_ms:.2f}ms"
                    )
                
                return result
            return wrapper
        return decorator
    
    @staticmethod
    def log_async_query_time(threshold_ms: float = 100):
        """
        Async decorator to log slow queries.
        
        Args:
            threshold_ms: Log queries taking longer than this (milliseconds)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = await func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                
                if elapsed_ms > threshold_ms:
                    logger.warning(
                        f"Slow async query in {func.__name__}: {elapsed_ms:.2f}ms"
                    )
                
                return result
            return wrapper
        return decorator
    
    @staticmethod
    def eager_load_relationships(query, *relationships):
        """
        Apply eager loading to prevent N+1 queries.
        
        Args:
            query: SQLAlchemy query object
            *relationships: Relationship attributes to eager load
            
        Returns:
            Query with joinedload applied
            
        Example:
            query = db.query(Ticket)
            query = QueryOptimizer.eager_load_relationships(
                query, 
                Ticket.company,
                Ticket.raised_by_user,
                Ticket.assigned_engineer
            )
        """
        for relationship in relationships:
            query = query.options(joinedload(relationship))
        return query
    
    @staticmethod
    async def eager_load_async(stmt, *relationships):
        """
        Apply eager loading to async select statement.
        
        Args:
            stmt: SQLAlchemy select() statement
            *relationships: Relationship attributes to eager load
            
        Returns:
            Statement with selectinload applied
            
        Example:
            stmt = select(Ticket).where(Ticket.id == ticket_id)
            stmt = QueryOptimizer.eager_load_async(
                stmt,
                selectinload(Ticket.company),
                selectinload(Ticket.raised_by_user)
            )
        """
        for relationship in relationships:
            stmt = stmt.options(relationship)
        return stmt
    
    @staticmethod
    def get_with_relationships(
        db: Session,
        model: Any,
        filter_by: dict,
        relationships: List[Any] = None
    ) -> Optional[Any]:
        """
        Get single record with eager loaded relationships.
        
        Args:
            db: SQLAlchemy Session
            model: SQLAlchemy model class
            filter_by: Dictionary of filter conditions
            relationships: List of relationship attributes to eager load
            
        Returns:
            Model instance or None
        """
        query = db.query(model)
        
        if relationships:
            for rel in relationships:
                query = query.options(joinedload(rel))
        
        for key, value in filter_by.items():
            query = query.filter(getattr(model, key) == value)
        
        return query.first()
    
    @staticmethod
    def list_with_relationships(
        db: Session,
        model: Any,
        filter_by: dict = None,
        relationships: List[Any] = None,
        order_by: Any = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Any]:
        """
        Get list of records with eager loaded relationships.
        
        Args:
            db: SQLAlchemy Session
            model: SQLAlchemy model class
            filter_by: Dictionary of filter conditions
            relationships: List of relationship attributes to eager load
            order_by: Column to order by
            limit: Number of records to return
            offset: Number of records to skip
            
        Returns:
            List of model instances
        """
        query = db.query(model)
        
        if relationships:
            for rel in relationships:
                query = query.options(joinedload(rel))
        
        if filter_by:
            for key, value in filter_by.items():
                query = query.filter(getattr(model, key) == value)
        
        if order_by is not None:
            query = query.order_by(order_by)
        
        return query.limit(limit).offset(offset).all()
    
    @staticmethod
    def count_efficient(db: Session, model: Any, filter_by: dict = None) -> int:
        """
        Efficient count query (avoids loading full objects).
        
        Args:
            db: SQLAlchemy Session
            model: SQLAlchemy model class
            filter_by: Dictionary of filter conditions
            
        Returns:
            Count of matching records
        """
        from sqlalchemy import func
        
        query = db.query(func.count(model.id))
        
        if filter_by:
            for key, value in filter_by.items():
                query = query.filter(getattr(model, key) == value)
        
        return query.scalar()


class BatchQuery:
    """Utilities for batch database operations"""
    
    @staticmethod
    def batch_get_by_ids(
        db: Session,
        model: Any,
        ids: List[Any],
        id_column: Any = None
    ) -> List[Any]:
        """
        Get multiple records by IDs in batch (avoids N queries).
        
        Args:
            db: SQLAlchemy Session
            model: SQLAlchemy model class
            ids: List of IDs to fetch
            id_column: ID column (defaults to model.id)
            
        Returns:
            List of model instances
        """
        if not ids:
            return []
        
        if id_column is None:
            id_column = model.id
        
        return db.query(model).filter(id_column.in_(ids)).all()
    
    @staticmethod
    def batch_update(
        db: Session,
        model: Any,
        updates: dict,
        filter_by: dict
    ) -> int:
        """
        Update multiple records matching filter.
        
        Args:
            db: SQLAlchemy Session
            model: SQLAlchemy model class
            updates: Dictionary of columns to update
            filter_by: Dictionary of filter conditions
            
        Returns:
            Number of rows updated
        """
        query = db.query(model)
        
        for key, value in filter_by.items():
            query = query.filter(getattr(model, key) == value)
        
        count = query.update(updates, synchronize_session=False)
        db.commit()
        
        return count