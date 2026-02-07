# server/services/cached_queries.py
"""
Intelligent Query Result Caching - Automatic caching with invalidation
Caches frequently-accessed database queries to reduce load

Features:
- Automatic caching based on query type
- Intelligent cache key generation from parameters
- Tag-based invalidation tied to mutations
- Performance tracking
- TTL configuration per query type
"""

import asyncio
import hashlib
import json
from typing import Optional, Any, List, Dict, TypeVar, Callable
from uuid import UUID
from functools import wraps
from datetime import datetime
import time

from sqlalchemy.orm import Session
from sqlalchemy import select

from core.database import Company, Ticket, User, IncidentReport, RootCauseAnalysis
from core.config import CACHE_DEFAULT_TTL
from core.logger import get_logger
from services.redis_cache_service import get_cache
from core.cache_config import CacheTTL, CACHE_KEY_PATTERNS, INVALIDATION_RULES

logger = get_logger(__name__)

T = TypeVar('T')


class CachedQueries:
    """Intelligent query result caching system"""
    
    @staticmethod
    def _generate_cache_key(base_key: str, **params) -> str:
        """
        Generate cache key from base key and parameters
        
        Args:
            base_key: Base key pattern (e.g., "ticket:list")
            **params: Dynamic parameters
            
        Returns:
            Generated cache key
        """
        # Build key with parameters
        key = base_key
        for k, v in sorted(params.items()):
            if v is not None:
                # Hash large values
                if isinstance(v, str) and len(v) > 50:
                    v = hashlib.md5(v.encode()).hexdigest()
                key = key.replace(f"{{{k}}}", str(v))
        
        return key
    
    @staticmethod
    async def get_ticket_list(
        db: Session,
        company_id: UUID,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> List[Ticket]:
        """
        Get list of tickets with intelligent caching
        
        Cache TTL: 30 seconds (high change frequency)
        Cache tags: ticket:list
        """
        cache = await get_cache()
        
        # Generate cache key
        cache_key = CachedQueries._generate_cache_key(
            CACHE_KEY_PATTERNS["ticket:list"],
            company_id=company_id,
            status=status or "all",
            page=page
        )
        
        # Try to get from cache
        cached = await cache.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return cached
        
        logger.debug(f"Cache MISS: {cache_key}")
        
        # Query database
        query = select(Ticket).where(Ticket.company_id == company_id)
        
        if status:
            query = query.where(Ticket.status == status)
        
        query = query.order_by(Ticket.created_at.desc())
        query = query.offset((page - 1) * limit).limit(limit)
        
        start = time.perf_counter()
        result = db.execute(query).scalars().all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Convert to dict for caching
        cached_result = [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in result
        ]
        
        # Cache with tag
        ttl = int(CacheTTL.TICKET_LIST)
        await cache.set(
            cache_key,
            cached_result,
            ttl=ttl,
            tags=["ticket:list", f"company:{company_id}"]
        )
        
        return cached_result
    
    @staticmethod
    async def get_ticket_detail(
        db: Session,
        ticket_id: UUID,
        company_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed ticket with relationships and caching
        
        Cache TTL: 60 seconds
        Cache tags: ticket:detail, ticket:list
        """
        cache = await get_cache()
        
        # Generate cache key
        cache_key = CachedQueries._generate_cache_key(
            CACHE_KEY_PATTERNS["ticket:detail"],
            ticket_id=ticket_id,
            company_id=company_id
        )
        
        # Try cache first
        cached = await cache.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return cached
        
        logger.debug(f"Cache MISS: {cache_key}")
        
        # Query with relationships
        from core.query_optimizer import QueryOptimizer
        
        start = time.perf_counter()
        ticket = QueryOptimizer.get_with_relationships(
            db,
            Ticket,
            {"id": ticket_id, "company_id": company_id},
            relationships=[
                Ticket.company,
                Ticket.raised_by_user,
                Ticket.assigned_engineer,
            ]
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if not ticket:
            return None
        
        # Prepare cached response
        cached_response = {
            "id": str(ticket.id),
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "company_id": str(ticket.company_id),
        }
        
        # Cache with tags
        ttl = int(CacheTTL.TICKET_DETAIL)
        await cache.set(
            cache_key,
            cached_response,
            ttl=ttl,
            tags=[
                "ticket:detail",
                f"ticket:{ticket_id}",
                f"company:{company_id}",
                "ticket:list"
            ]
        )
        
        return cached_response
    
    @staticmethod
    async def get_company_detail(
        db: Session,
        company_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get company with user count
        
        Cache TTL: 3600 seconds (static data)
        Cache tags: company, company:list
        """
        cache = await get_cache()
        
        cache_key = CachedQueries._generate_cache_key(
            CACHE_KEY_PATTERNS["company:detail"],
            company_id=company_id
        )
        
        cached = await cache.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return cached
        
        logger.debug(f"Cache MISS: {cache_key}")
        
        from core.query_optimizer import QueryOptimizer
        from sqlalchemy import func
        
        # Get company with user count
        start = time.perf_counter()
        company = db.execute(
            select(Company).where(Company.id == company_id)
        ).scalar_one_or_none()
        
        if not company:
            return None
        
        user_count = db.execute(
            select(func.count(User.id)).where(User.company_id == company_id)
        ).scalar()
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        cached_response = {
            "id": str(company.id),
            "name": company.name,
            "created_at": company.created_at.isoformat() if company.created_at else None,
            "user_count": user_count,
        }
        
        ttl = int(CacheTTL.COMPANY_DETAIL)
        await cache.set(
            cache_key,
            cached_response,
            ttl=ttl,
            tags=["company:detail", f"company:{company_id}", "company:list"]
        )
        
        return cached_response
    
    @staticmethod
    async def search_similar(
        db: Session,
        query: str,
        company_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for similar tickets (cached)
        
        Cache TTL: 120 seconds
        Cache tags: search
        """
        cache = await get_cache()
        
        # Hash query for key
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        
        cache_key = CachedQueries._generate_cache_key(
            CACHE_KEY_PATTERNS["search:similar"],
            query_hash=query_hash,
            company_id=company_id,
            limit=limit
        )
        
        cached = await cache.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return cached
        
        logger.debug(f"Cache MISS: {cache_key}")
        
        # Simulated search - in real implementation would use embeddings
        start = time.perf_counter()
        results = db.execute(
            select(Ticket)
            .where(Ticket.company_id == company_id)
            .where(Ticket.title.ilike(f"%{query}%"))
            .limit(limit)
        ).scalars().all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        cached_results = [
            {
                "id": str(t.id),
                "title": t.title,
                "description": t.description[:100] if t.description else None,
                "status": t.status,
            }
            for t in results
        ]
        
        ttl = int(CacheTTL.SEARCH_RESULTS)
        await cache.set(
            cache_key,
            cached_results,
            ttl=ttl,
            tags=["search:similar", f"company:{company_id}"]
        )
        
        return cached_results
    
    @staticmethod
    async def get_user_list(
        db: Session,
        company_id: UUID,
        page: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get users in company
        
        Cache TTL: 600 seconds
        Cache tags: user:list
        """
        cache = await get_cache()
        
        cache_key = CachedQueries._generate_cache_key(
            CACHE_KEY_PATTERNS["user:list"],
            company_id=company_id,
            page=page
        )
        
        cached = await cache.get(cache_key)
        if cached:
            logger.debug(f"Cache HIT: {cache_key}")
            return cached
        
        logger.debug(f"Cache MISS: {cache_key}")
        
        start = time.perf_counter()
        users = db.execute(
            select(User)
            .where(User.company_id == company_id)
            .order_by(User.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        ).scalars().all()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        cached_users = [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
        
        ttl = int(CacheTTL.USER_LIST)
        await cache.set(
            cache_key,
            cached_users,
            ttl=ttl,
            tags=["user:list", f"company:{company_id}"]
        )
        
        return cached_users


async def invalidate_cache_for_ticket(
    ticket_id: UUID,
    company_id: UUID,
    operation: str = "update"
) -> None:
    """
    Invalidate cache entries for a ticket operation
    
    Args:
        ticket_id: Ticket ID
        company_id: Company ID  
        operation: Operation type (create, update, delete)
    """
    cache = await get_cache()
    
    if not cache.enabled:
        return
    
    # Get invalidation rules
    if operation == "create":
        rules = INVALIDATION_RULES.get("ticket:create", {})
    elif operation == "update":
        rules = INVALIDATION_RULES.get("ticket:update", {})
    elif operation == "delete":
        rules = INVALIDATION_RULES.get("ticket:delete", {})
    else:
        rules = {}
    
    # Invalidate tags
    for tag in rules.get("invalidate_tags", []):
        # Replace placeholders
        tag = tag.replace("{ticket_id}", str(ticket_id))
        tag = tag.replace("{company_id}", str(company_id))
        
        # Handle wildcards
        if "*" in tag:
            pattern = tag.replace("*", "*")
            await cache.invalidate_by_pattern(pattern)
        else:
            await cache.invalidate_by_tag(tag)
    
    logger.info(f"Cache invalidated for ticket:{ticket_id} operation:{operation}")


async def invalidate_cache_for_company(company_id: UUID) -> None:
    """Invalidate all cache for a company"""
    cache = await get_cache()
    
    if not cache.enabled:
        return
    
    # Invalidate by company pattern
    await cache.invalidate_by_pattern(f"*company:{company_id}*")
    await cache.invalidate_by_tag(f"company:{company_id}")
    
    logger.info(f"Cache invalidated for company:{company_id}")