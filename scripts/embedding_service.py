# server/services/embedding_manager.py
"""
Embedding Manager Service - Synchronous wrapper with event emission

This service provides synchronous embedding operations that work with
the asynchronous event-driven system (event_queue.py).

When tickets are created/updated/deleted, this service:
1. Creates/updates/deprecates embeddings in PostgreSQL
2. Chunks large text into manageable pieces
3. Assigns vector IDs from the embedding service
4. Emits events that trigger async processing (Qdrant sync, similarity checks)
5. Maps similar tickets based on vector similarity
"""

import logging
import sys
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# Setup logging
logger = logging.getLogger(__name__)

try:
    from core.database import SessionLocal, Ticket, Embedding, SimilarIssues
except ImportError:
    from core.database import SessionLocal, Ticket, Embedding, SimilarIssues


class EmbeddingManager:
    """Service to synchronously manage embeddings with ticket lifecycle"""
    
    # Configuration constants (match embedding_service.py)
    CHUNK_SIZE = 1500
    CHUNK_OVERLAP = 100
    MAX_TEXT_LENGTH = 2000
    
    @staticmethod
    def _chunk_text(text: str) -> List[str]:
        """
        Split text into overlapping chunks (matches embedding_service.py).
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks (max CHUNK_SIZE chars, with CHUNK_OVERLAP)
        """
        if not text or len(text) <= EmbeddingManager.CHUNK_SIZE:
            return [text] if text else []
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + EmbeddingManager.CHUNK_SIZE, len(text))
            chunk = text[start:end]
            chunks.append(chunk)
            # Move start back by overlap amount for next chunk
            start = end - EmbeddingManager.CHUNK_OVERLAP
        
        return chunks
    
    
    @staticmethod
    def create_ticket_embeddings(
        ticket_id: str,
        company_id: str,
        subject: str,
        description: str,
        category: Optional[str] = None,
        summary: Optional[str] = None
    ) -> bool:
        """
        Create embeddings for a new ticket.
        Stores in PostgreSQL with chunking and vector IDs.
        Emits event for async Qdrant sync and similarity mapping.
        
        Args:
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            subject: Ticket subject
            description: Detailed description
            category: Ticket category
            summary: Optional summary
            
        Returns:
            True if successful, False otherwise
        """
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            company_uuid = UUID(company_id)
            
            logger.info(f"Creating embeddings for ticket {ticket_id}")
            
            # Import embedding service
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
            from embedding_service import EmbeddingService
            
            embedding_count = 0
            
            # Embed subject (with category context)
            subject_text = f"{subject}"
            if category:
                subject_text += f" [{category}]"
            
            try:
                vector = EmbeddingService.get_embedding_vector(subject_text)
                if vector:
                    emb = Embedding(
                        company_id=company_uuid,
                        ticket_id=ticket_uuid,
                        source_type="ticket_summary",
                        chunk_index=0,
                        text_content=subject_text[:EmbeddingManager.MAX_TEXT_LENGTH],
                        vector_id=str(UUID(int=hash(subject_text) & ((1 << 128) - 1))),  # Deterministic ID
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()
                    embedding_count += 1
                    logger.debug(f"✓ Added subject embedding for ticket {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to embed subject: {e}")
            
            # Embed description with chunking
            if description:
                chunks = EmbeddingManager._chunk_text(description)
                logger.debug(f"Chunked description into {len(chunks)} pieces for ticket {ticket_id}")
                
                for idx, chunk in enumerate(chunks):
                    try:
                        vector = EmbeddingService.get_embedding_vector(chunk)
                        if vector:
                            emb = Embedding(
                                company_id=company_uuid,
                                ticket_id=ticket_uuid,
                                source_type="ticket_description",
                                chunk_index=idx,
                                text_content=chunk[:EmbeddingManager.MAX_TEXT_LENGTH],
                                vector_id=str(UUID(int=hash(chunk) & ((1 << 128) - 1))),  # Deterministic ID
                                is_active=True
                            )
                            db.add(emb)
                            db.flush()
                            embedding_count += 1
                            logger.debug(f"✓ Added description embedding chunk {idx} for ticket {ticket_id}")
                    except Exception as e:
                        logger.warning(f"Failed to embed description chunk {idx}: {e}")
            
            db.commit()
            logger.info(f"✓ Created {embedding_count} embeddings for ticket {ticket_id}")
            
            # Emit EMBEDDING_CREATED event for async Qdrant sync
            try:
                from event_queue import EventQueue, EventType
                EventQueue.emit(
                    EventType.EMBEDDING_CREATED,
                    ticket_id=ticket_id,
                    company_id=company_id,
                    embedding_count=embedding_count,
                    source_types=["ticket_summary", "ticket_description"]
                )
                logger.info(f"✓ Emitted EMBEDDING_CREATED event for {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to emit EMBEDDING_CREATED event: {e}")
            
            # Find and map similar older tickets (synchronous)
            EmbeddingManager._find_and_map_similar_tickets(ticket_id, company_id)
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create ticket embeddings: {e}")
            return False
        finally:
            db.close()
    
    
    @staticmethod
    def update_ticket_embeddings(
        ticket_id: str,
        company_id: str,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        summary: Optional[str] = None
    ) -> bool:
        """
        Update embeddings when ticket details change.
        Deprecates old embeddings and creates new ones.
        
        Args:
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            subject: Updated subject
            description: Updated description
            category: Updated category
            summary: Updated summary
            
        Returns:
            True if successful, False otherwise
        """
        db = SessionLocal()
        try:
            logger.info(f"Updating embeddings for ticket {ticket_id}")
            
            # Deprecate old embeddings for these sources
            deprecated_count = db.query(Embedding).filter(
                Embedding.ticket_id == UUID(ticket_id),
                Embedding.source_type.in_(["ticket_summary", "ticket_description"]),
                Embedding.is_active == True
            ).update({
                Embedding.is_active: False,
                Embedding.deprecated_at: datetime.utcnow(),
                Embedding.deprecation_reason: "ticket_updated"
            }, synchronize_session=False)
            
            db.commit()
            logger.info(f"Deprecated {deprecated_count} old embeddings for ticket {ticket_id}")
            
            # Emit EMBEDDING_DEPRECATED event for Qdrant update
            try:
                from event_queue import EventQueue, EventType
                EventQueue.emit(
                    EventType.EMBEDDING_DEPRECATED,
                    ticket_id=ticket_id,
                    reason="ticket_updated",
                    count=deprecated_count
                )
            except Exception as e:
                logger.warning(f"Failed to emit deprecation event: {e}")
            
            # Create new embeddings
            return EmbeddingManager.create_ticket_embeddings(
                ticket_id=ticket_id,
                company_id=company_id,
                subject=subject or "",
                description=description or "",
                category=category,
                summary=summary
            )
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update ticket embeddings: {e}")
            return False
        finally:
            db.close()
    
    
    @staticmethod
    def add_rca_embedding(
        ticket_id: str,
        company_id: str,
        root_cause_description: str,
        contributing_factors: Optional[List[str]] = None,
        prevention_measures: Optional[str] = None
    ) -> bool:
        """
        Create embedding for RCA when added/updated.
        Includes text chunking for large RCAs.
        Emits event for async Qdrant sync.
        
        Args:
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            root_cause_description: RCA description
            contributing_factors: List of factors
            prevention_measures: Prevention measures text
            
        Returns:
            True if successful, False otherwise
        """
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            company_uuid = UUID(company_id)
            
            logger.info(f"Creating RCA embedding for ticket {ticket_id}")
            
            # Deprecate old RCA embedding if it exists
            deprecated_count = db.query(Embedding).filter(
                Embedding.ticket_id == ticket_uuid,
                Embedding.source_type == "rca",
                Embedding.is_active == True
            ).update({
                Embedding.is_active: False,
                Embedding.deprecated_at: datetime.utcnow(),
                Embedding.deprecation_reason: "rca_updated"
            }, synchronize_session=False)
            
            # Build RCA text for embedding
            rca_text = root_cause_description
            if contributing_factors:
                rca_text += " Factors: " + ", ".join(contributing_factors)
            if prevention_measures:
                rca_text += " Prevention: " + prevention_measures
            
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
            from embedding_service import EmbeddingService
            
            embedding_count = 0
            
            # Chunk RCA text
            chunks = EmbeddingManager._chunk_text(rca_text)
            logger.debug(f"Chunked RCA into {len(chunks)} pieces for ticket {ticket_id}")
            
            for idx, chunk in enumerate(chunks):
                try:
                    vector = EmbeddingService.get_embedding_vector(chunk)
                    if vector:
                        emb = Embedding(
                            company_id=company_uuid,
                            ticket_id=ticket_uuid,
                            source_type="rca",
                            chunk_index=idx,
                            text_content=chunk[:EmbeddingManager.MAX_TEXT_LENGTH],
                            vector_id=str(UUID(int=hash(chunk) & ((1 << 128) - 1))),  # Deterministic ID
                            is_active=True
                        )
                        db.add(emb)
                        db.flush()
                        embedding_count += 1
                        logger.debug(f"✓ Added RCA embedding chunk {idx} for ticket {ticket_id}")
                except Exception as e:
                    logger.warning(f"Failed to embed RCA chunk {idx}: {e}")
            
            db.commit()
            logger.info(f"✓ {'Updated' if deprecated_count > 0 else 'Created'} RCA embedding ({embedding_count} chunks) for ticket {ticket_id}")
            
            # Emit RESOLUTION_ADDED event for async Qdrant sync
            try:
                from event_queue import EventQueue, EventType
                EventQueue.emit(
                    EventType.RESOLUTION_ADDED,
                    ticket_id=ticket_id,
                    company_id=company_id,
                    resolution_text=rca_text[:500],
                    source_type="rca"
                )
                logger.info(f"✓ Emitted RESOLUTION_ADDED event for {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to emit RCA event: {e}")
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create RCA embedding: {e}")
            return False
        finally:
            db.close()
    
    
    @staticmethod
    def deprecate_ticket_embeddings(
        ticket_id: str,
        reason: str = "ticket_deleted"
    ) -> bool:
        """
        Deprecate all embeddings for a ticket.
        Called when ticket is deleted, closed, or reopened.
        Emits event for async Qdrant update.
        
        Args:
            ticket_id: UUID of the ticket
            reason: Reason for deprecation
            
        Returns:
            True if successful, False otherwise
        """
        db = SessionLocal()
        try:
            logger.info(f"Deprecating embeddings for ticket {ticket_id}: {reason}")
            
            count = db.query(Embedding).filter(
                Embedding.ticket_id == UUID(ticket_id),
                Embedding.is_active == True
            ).update({
                Embedding.is_active: False,
                Embedding.deprecated_at: datetime.utcnow(),
                Embedding.deprecation_reason: reason
            }, synchronize_session=False)
            
            db.commit()
            logger.info(f"✓ Deprecated {count} embeddings for ticket {ticket_id}")
            
            # Emit EMBEDDING_DEPRECATED event for async Qdrant update
            try:
                from event_queue import EventQueue, EventType
                EventQueue.emit(
                    EventType.EMBEDDING_DEPRECATED,
                    ticket_id=ticket_id,
                    reason=reason,
                    count=count
                )
                logger.info(f"✓ Emitted EMBEDDING_DEPRECATED event for {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to emit deprecation event: {e}")
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to deprecate embeddings: {e}")
            return False
        finally:
            db.close()
    
    
    @staticmethod
    def _find_and_map_similar_tickets(
        new_ticket_id: str,
        company_id: str,
        similarity_threshold: int = 75
    ) -> int:
        """
        Find older tickets similar to the new ticket and create mappings.
        Uses PostgreSQL embeddings for comparison.
        
        Only maps to tickets with smaller ticket numbers (older tickets).
        
        Args:
            new_ticket_id: UUID of the new ticket
            company_id: UUID of the company
            similarity_threshold: Minimum similarity score (0-100)
            
        Returns:
            Number of similar tickets found and mapped
        """
        db = SessionLocal()
        try:
            new_ticket_uuid = UUID(new_ticket_id)
            company_uuid = UUID(company_id)
            
            logger.info(f"Finding similar tickets for {new_ticket_id}")
            
            # Get the new ticket to extract its ticket number
            new_ticket = db.query(Ticket).filter(
                Ticket.id == new_ticket_uuid
            ).first()
            
            if not new_ticket:
                logger.warning(f"Ticket {new_ticket_id} not found")
                return 0
            
            # Extract ticket number as integer (e.g., "TKT-000917" -> 917)
            try:
                new_ticket_num = int(new_ticket.ticket_no.split('-')[-1])
            except (IndexError, ValueError):
                logger.warning(f"Could not extract ticket number from {new_ticket.ticket_no}")
                return 0
            
            # Get active embeddings for the new ticket
            new_embeddings = db.query(Embedding).filter(
                Embedding.ticket_id == new_ticket_uuid,
                Embedding.is_active == True
            ).all()
            
            if not new_embeddings:
                logger.warning(f"No active embeddings found for ticket {new_ticket_id}")
                return 0
            
            # Get all older tickets in the same company
            older_tickets = db.query(Ticket).filter(
                Ticket.company_id == company_uuid,
                Ticket.id != new_ticket_uuid
            ).all()
            
            # Filter to only older tickets (smaller ticket number)
            older_tickets = [
                t for t in older_tickets
                if int(t.ticket_no.split('-')[-1]) < new_ticket_num
            ]
            
            if not older_tickets:
                logger.info(f"No older tickets found for comparison with {new_ticket.ticket_no}")
                return 0
            
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
            from embedding_service import EmbeddingService
            
            mapped_count = 0
            
            # For each older ticket, calculate similarity
            for older_ticket in older_tickets:
                try:
                    older_embeddings = db.query(Embedding).filter(
                        Embedding.ticket_id == older_ticket.id,
                        Embedding.is_active == True
                    ).all()
                    
                    if not older_embeddings:
                        continue
                    
                    # Calculate average similarity score
                    total_similarity = 0
                    comparison_count = 0
                    
                    for new_emb in new_embeddings:
                        for old_emb in older_embeddings:
                            # Both embeddings need vector IDs
                            if new_emb.vector_id and old_emb.vector_id:
                                try:
                                    similarity = EmbeddingService.calculate_similarity(
                                        new_emb.vector_id,
                                        old_emb.vector_id
                                    )
                                    total_similarity += similarity
                                    comparison_count += 1
                                except Exception as e:
                                    logger.debug(f"Error calculating similarity: {e}")
                                    continue
                    
                    if comparison_count == 0:
                        continue
                    
                    avg_similarity = (total_similarity / comparison_count) * 100  # Convert to 0-100
                    
                    if avg_similarity >= similarity_threshold:
                        # Create mapping
                        similar_issue = SimilarIssues(
                            newer_ticket_id=new_ticket_uuid,
                            older_ticket_id=older_ticket.id,
                            similarity_score=int(avg_similarity)
                        )
                        db.add(similar_issue)
                        mapped_count += 1
                        logger.debug(f"Mapped {new_ticket.ticket_no} -> {older_ticket.ticket_no} (similarity: {avg_similarity:.1f}%)")
                        
                except Exception as e:
                    logger.warning(f"Error comparing with {older_ticket.ticket_no}: {e}")
                    continue
            
            db.commit()
            logger.info(f"✓ Mapped {mapped_count} similar tickets for {new_ticket.ticket_no}")
            return mapped_count
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to find similar tickets: {e}")
            return 0
        finally:
            db.close()
    
    
    @staticmethod
    def get_similar_tickets(
        ticket_id: str,
        include_directions: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get similar tickets for a given ticket from SimilarIssues table.
        
        Args:
            ticket_id: UUID of the ticket
            include_directions: "both" (default), "newer", or "older"
            
        Returns:
            List of similar tickets with metadata
        """
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            results = []
            
            if include_directions in ["both", "newer"]:
                # Get newer tickets that are similar to this one
                newer = db.query(SimilarIssues).filter(
                    SimilarIssues.older_ticket_id == ticket_uuid
                ).all()
                
                for sim in newer:
                    ticket = sim.newer_ticket
                    results.append({
                        "ticket_id": str(ticket.id),
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "similarity_score": sim.similarity_score,
                        "direction": "newer",
                        "created_at": ticket.created_at.isoformat()
                    })
            
            if include_directions in ["both", "older"]:
                # Get older tickets similar to this one
                older = db.query(SimilarIssues).filter(
                    SimilarIssues.newer_ticket_id == ticket_uuid
                ).all()
                
                for sim in older:
                    ticket = sim.older_ticket
                    results.append({
                        "ticket_id": str(ticket.id),
                        "ticket_no": ticket.ticket_no,
                        "subject": ticket.subject,
                        "similarity_score": sim.similarity_score,
                        "direction": "older",
                        "created_at": ticket.created_at.isoformat()
                    })
            
            # Sort by similarity score
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get similar tickets: {e}")
            return []
        finally:
            db.close()