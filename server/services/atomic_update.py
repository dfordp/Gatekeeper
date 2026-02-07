# server/services/atomic_update.py
"""
Atomic multi-store update pattern for Postgres + Qdrant + Redis
Ensures consistency across all three data stores with rollback capability
"""

from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct
from uuid import UUID
import asyncio

from core.logger import get_logger
from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

logger = get_logger(__name__)


class AtomicStoreUpdate:
    """
    Atomic update across PostgreSQL + Qdrant + Redis with rollback.
    
    Pattern:
    1. Acquire distributed lock (Redis)
    2. Create transaction (Postgres)
    3. Update Postgres (within transaction)
    4. Update Qdrant (with circuit breaker)
    5. Commit Postgres (only if Qdrant succeeded)
    6. Invalidate Redis cache
    7. Release lock
    """
    
    # Circuit breaker for Qdrant to prevent cascade failures
    _qdrant_breaker = CircuitBreaker(
        name="qdrant_upsert",
        failure_threshold=3,
        recovery_timeout=30
    )
    
    @staticmethod
    async def update_ticket_atomic(
        db: AsyncSession,
        ticket_id: str,
        ticket_updates: Dict[str, Any],
        vector_updates: Optional[Dict[str, Any]],
        cache_service: Optional[Any] = None,
        qdrant_client: Optional[AsyncQdrantClient] = None
    ) -> bool:
        """
        Atomically update ticket across stores with rollback.
        
        Args:
            db: Async database session
            ticket_id: UUID of ticket
            ticket_updates: Dict of fields to update in Postgres
            vector_updates: Dict with 'vector', 'payload' for Qdrant (optional)
            cache_service: Redis cache service (optional)
            qdrant_client: Async Qdrant client (optional)
            
        Returns:
            True if successful, False otherwise
            
        Example:
            success = await AtomicStoreUpdate.update_ticket_atomic(
                db=db,
                ticket_id="123e4567-e89b-12d3-a456-426614174000",
                ticket_updates={"status": "resolved", "updated_at": datetime.now()},
                vector_updates={
                    "id": "vector-id-123",
                    "vector": [0.1, 0.2, ...],
                    "payload": {"ticket_id": "123e...", "status": "resolved"}
                },
                cache_service=cache,
                qdrant_client=qdrant
            )
        """
        from core.database import Ticket
        
        lock_key = f"ticket:update:{ticket_id}"
        lock = None
        
        try:
            # STEP 1: Acquire distributed lock
            if cache_service:
                lock = await cache_service.acquire_lock(lock_key, timeout=30)
                if not lock:
                    logger.warning(f"Could not acquire lock for ticket {ticket_id}")
                    return False
            
            try:
                # STEP 2-3: Update Postgres (within transaction savepoint)
                async with db.begin_nested():
                    ticket = await db.get(Ticket, UUID(ticket_id))
                    if not ticket:
                        logger.warning(f"Ticket not found: {ticket_id}")
                        return False
                    
                    # Apply updates
                    for key, value in ticket_updates.items():
                        if hasattr(ticket, key):
                            setattr(ticket, key, value)
                    
                    await db.flush()  # Flush but don't commit yet!
                    
                    # STEP 4: Update Qdrant (with circuit breaker + timeout)
                    if vector_updates and qdrant_client:
                        try:
                            point = PointStruct(
                                id=vector_updates["id"],
                                vector=vector_updates["vector"],
                                payload=vector_updates.get("payload", {})
                            )
                            
                            # Use circuit breaker to prevent cascade failure
                            await asyncio.wait_for(
                                AtomicStoreUpdate._qdrant_breaker.call(
                                    qdrant_client.upsert,
                                    collection_name="tickets",
                                    points=[point]
                                ),
                                timeout=10.0  # Qdrant operation timeout
                            )
                            
                            logger.debug(f"✓ Qdrant updated for ticket {ticket_id}")
                        
                        except CircuitBreakerOpen:
                            # Qdrant circuit is open, rollback and fail
                            await db.rollback()
                            logger.error(f"Qdrant circuit breaker OPEN, rolling back")
                            return False
                        
                        except asyncio.TimeoutError:
                            # Qdrant timeout, rollback and fail
                            await db.rollback()
                            logger.error(f"Qdrant timeout, rolling back")
                            return False
                        
                        except Exception as e:
                            # Qdrant error, rollback and fail
                            await db.rollback()
                            logger.error(f"Qdrant update failed: {e}, rolling back")
                            return False
                    
                    # STEP 5: Commit Postgres (only if Qdrant succeeded)
                    await db.commit()
                    logger.info(f"✓ Atomic update committed for ticket {ticket_id}")
                
                # STEP 6: Invalidate cache (best effort, failures logged but tolerated)
                if cache_service:
                    try:
                        await cache_service.invalidate_by_tag(f"ticket:detail:{ticket_id}")
                        await cache_service.invalidate_by_tag("ticket:list")
                        logger.debug(f"✓ Cache invalidated for ticket {ticket_id}")
                    except Exception as e:
                        logger.warning(
                            f"Cache invalidation failed (non-critical): {e}"
                        )
                
                return True
            
            finally:
                # STEP 7: Always release lock
                if cache_service and lock:
                    try:
                        await cache_service.release_lock(lock_key)
                    except Exception as e:
                        logger.warning(f"Failed to release lock: {e}")
        
        except Exception as e:
            logger.error(f"Atomic update failed: {e}")
            try:
                await db.rollback()
            except:
                pass
            return False