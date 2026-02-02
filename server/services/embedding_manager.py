# server/services/embedding_manager.py
"""
Embedding Manager Service - Synchronous with Qdrant sync

This service provides synchronous embedding operations with immediate Qdrant syncing.

When tickets are created/updated/deleted, this service:
1. Creates/updates/deprecates embeddings in PostgreSQL
2. Immediately syncs embeddings to Qdrant
3. Updates vector_id for tracking
4. Maps similar tickets based on vector similarity
"""

import logging
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import uuid as uuid_lib

from core.database import SessionLocal, Embedding
from .embedding_api_client import EmbeddingAPIClient
from .event_queue import EventQueue, EventType
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams
from sqlalchemy.orm.attributes import flag_modified

# Setup logging
logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Service to synchronously manage embeddings with Qdrant sync"""
    
    # Initialize API client once
    _api_client = EmbeddingAPIClient()
    
    # Qdrant configuration
    QDRANT_URL = "http://qdrant:6333"
    QDRANT_API_KEY = "qdrant_secure_key_123"
    QDRANT_COLLECTION = "tickets"
    VECTOR_SIZE = 1536
    
    @staticmethod
    def _get_qdrant_client() -> QdrantClient:
        """Get Qdrant client instance"""
        return QdrantClient(
            url=EmbeddingManager.QDRANT_URL,
            api_key=EmbeddingManager.QDRANT_API_KEY,
            timeout=30.0
        )
    
    @staticmethod
    def _ensure_qdrant_collection() -> bool:
        """Ensure Qdrant collection exists"""
        try:
            client = EmbeddingManager._get_qdrant_client()
            try:
                client.get_collection(EmbeddingManager.QDRANT_COLLECTION)
                return True
            except Exception as e:
                error_str = str(e).lower()
                
                # If it's a validation error from parsing a successful response, treat it as collection exists
                # (Qdrant returned 200 but Pydrant client failed to parse due to schema mismatch)
                if "validation error" in error_str and "parsing" in error_str:
                    logger.debug(f"Collection check returned validation error (likely schema mismatch), assuming collection exists")
                    return True
                
                # Only try to create if collection doesn't exist
                if "not found" in error_str:
                    logger.info(f"Creating Qdrant collection '{EmbeddingManager.QDRANT_COLLECTION}'...")
                    try:
                        client.create_collection(
                            collection_name=EmbeddingManager.QDRANT_COLLECTION,
                            vectors_config=VectorParams(
                                size=EmbeddingManager.VECTOR_SIZE,
                                distance=Distance.COSINE
                            )
                        )
                        logger.info(f"✓ Created Qdrant collection")
                        return True
                    except Exception as create_error:
                        if "already exists" in str(create_error).lower():
                            logger.debug("Collection already exists, continuing...")
                            return True
                        raise create_error
                else:
                    # Some other error, re-raise
                    raise e
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")
            return False
    
    @staticmethod
    def _sync_embedding_to_qdrant(
        db,
        embedding_obj: Embedding,
        ticket_id: str,
        company_id: str,
        source_type: str,
        text_content: str
    ) -> Optional[str]:
        """
        Sync a single embedding to Qdrant and update vector_id in the embedding object.
        
        Args:
            db: SQLAlchemy session
            embedding_obj: The Embedding object to update
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            source_type: Type of embedding
            text_content: Text content of the embedding
            
        Returns:
            Point ID in Qdrant if successful, None otherwise
        """
        try:
            # Ensure collection exists
            if not EmbeddingManager._ensure_qdrant_collection():
                return None
            
            # Generate vector for text
            vector = EmbeddingManager._api_client.get_embedding_vector(text_content)
            if not vector:
                logger.warning(f"Failed to generate vector for embedding {embedding_obj.id}")
                return None
            
            # Create Qdrant point
            point_id = str(uuid_lib.uuid4())
            client = EmbeddingManager._get_qdrant_client()
            
            client.upsert(
                collection_name=EmbeddingManager.QDRANT_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "embedding_id": str(embedding_obj.id),
                            "ticket_id": ticket_id,
                            "company_id": company_id,
                            "source_type": source_type,
                            "text": text_content[:500],
                        }
                    )
                ]
            )
            
            # Update embedding object with vector_id while still in session
            embedding_obj.vector_id = point_id
            flag_modified(embedding_obj, "vector_id")  # Tell SQLAlchemy this was modified
            
            logger.info(f"✓ Synced {source_type} embedding to Qdrant (id={point_id[:8]}...)")
            return point_id
            
        except Exception as e:
            logger.warning(f"Failed to sync embedding to Qdrant: {e}")
            return None
    
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
        Stores in PostgreSQL and syncs to Qdrant immediately.
        
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
            
            embedding_count = 0
            synced_count = 0
            
            # Create embedding for subject/summary
            subject_text = f"{subject}"
            if category:
                subject_text += f" [{category}]"
            
            try:
                vector = EmbeddingManager._api_client.get_embedding_vector(subject_text)
                if vector:
                    emb = Embedding(
                        company_id=company_uuid,
                        ticket_id=ticket_uuid,
                        source_type="ticket_summary",
                        text_content=subject_text[:2000],
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()  # Get the ID without committing
                    
                    # Sync to Qdrant and set vector_id in the same session
                    point_id = EmbeddingManager._sync_embedding_to_qdrant(
                        db=db,
                        embedding_obj=emb,
                        ticket_id=ticket_id,
                        company_id=company_id,
                        source_type="ticket_summary",
                        text_content=subject_text
                    )
                    if point_id:
                        synced_count += 1
                    
                    embedding_count += 1
                    logger.debug(f"✓ Added subject embedding for ticket {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to embed subject: {e}")
            
            # Embed description
            try:
                vector = EmbeddingManager._api_client.get_embedding_vector(description)
                if vector:
                    emb = Embedding(
                        company_id=company_uuid,
                        ticket_id=ticket_uuid,
                        source_type="ticket_description",
                        text_content=description[:2000],
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()  # Get the ID without committing
                    
                    # Sync to Qdrant and set vector_id in the same session
                    point_id = EmbeddingManager._sync_embedding_to_qdrant(
                        db=db,
                        embedding_obj=emb,
                        ticket_id=ticket_id,
                        company_id=company_id,
                        source_type="ticket_description",
                        text_content=description
                    )
                    if point_id:
                        synced_count += 1
                    
                    embedding_count += 1
                    logger.debug(f"✓ Added description embedding for ticket {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to embed description: {e}")
            
            # Single commit at the end for all embeddings
            db.commit()
            logger.info(f"✓ Created {embedding_count} embeddings, synced {synced_count} to Qdrant")
            
            # Emit event for any async processing
            try:
                EventQueue.emit(
                    EventType.EMBEDDING_CREATED,
                    ticket_id=ticket_id,
                    company_id=company_id,
                    embedding_count=embedding_count
                )
                logger.info(f"Emitted EMBEDDING_CREATED event for {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to emit embedding event: {e}")
            
            # Find and map similar older tickets (synchronous)
            EmbeddingManager._find_and_map_similar_tickets(ticket_id, company_id)
            
            return embedding_count > 0
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create ticket embeddings: {e}")
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
        Stores in PostgreSQL and syncs to Qdrant immediately.
        
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
            
            if deprecated_count > 0:
                logger.info(f"Deprecated {deprecated_count} old RCA embeddings")
            
            # Build RCA text for embedding
            rca_text = root_cause_description
            if contributing_factors:
                rca_text += " Factors: " + ", ".join(contributing_factors)
            if prevention_measures:
                rca_text += " Prevention: " + prevention_measures
            
            vector = EmbeddingManager._api_client.get_embedding_vector(rca_text)
            if not vector:
                logger.warning(f"Failed to generate vector for RCA")
                return False
            
            emb = Embedding(
                company_id=company_uuid,
                ticket_id=ticket_uuid,
                source_type="rca",
                text_content=rca_text[:2000],
                is_active=True
            )
            db.add(emb)
            db.flush()  # Get the ID without committing
            
            # Sync to Qdrant and set vector_id in the same session
            point_id = EmbeddingManager._sync_embedding_to_qdrant(
                db=db,
                embedding_obj=emb,
                ticket_id=ticket_id,
                company_id=company_id,
                source_type="rca",
                text_content=rca_text
            )
            
            # Single commit for RCA embedding
            db.commit()
            logger.info(f"✓ Created RCA embedding for ticket {ticket_id}")
            return True
                    
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add RCA embedding: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def deprecate_ticket_embeddings(
        ticket_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Deprecate all embeddings for a ticket"""
        db = SessionLocal()
        try:
            ticket_uuid = UUID(ticket_id)
            
            deprecated_count = db.query(Embedding).filter(
                Embedding.ticket_id == ticket_uuid,
                Embedding.is_active == True
            ).update({
                Embedding.is_active: False,
                Embedding.deprecated_at: datetime.utcnow(),
                Embedding.deprecation_reason: reason or "ticket_deleted"
            }, synchronize_session=False)
            
            db.commit()
            
            if deprecated_count > 0:
                logger.info(f"✓ Deprecated {deprecated_count} embeddings for ticket {ticket_id}")
            
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to deprecate ticket embeddings: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def _find_and_map_similar_tickets(ticket_id: str, company_id: str) -> bool:
        """Find and map similar tickets based on vector similarity"""
        # This is a placeholder for the similarity mapping logic
        # In production, this would use Qdrant or PostgreSQL pgvector extension
        logger.debug(f"Similarity mapping placeholder for {ticket_id}")
        return True