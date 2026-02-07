# server/services/async_embedding_manager.py
"""
Async Embedding Manager Service - AsyncOpenAI + AsyncQdrantClient

This service provides async embedding operations with async Qdrant syncing.

When tickets are created/updated/deleted asynchronously:
1. Creates/updates/deprecates embeddings in PostgreSQL (async)
2. Immediately syncs embeddings to Qdrant (async)
3. Updates vector_id for tracking
4. Maps similar tickets based on vector similarity
"""

import logging
import asyncio
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import uuid as uuid_lib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from core.database import Embedding
from .async_embedding_api_client import AsyncEmbeddingAPIClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

# Setup logging
logger = logging.getLogger(__name__)


class AsyncEmbeddingManager:
    """Service to asynchronously manage embeddings with async Qdrant sync"""
    
    # Initialize API client once
    _api_client = AsyncEmbeddingAPIClient()
    
    # Qdrant configuration
    QDRANT_URL = "http://qdrant:6333"
    QDRANT_API_KEY = "qdrant_secure_key_123"
    QDRANT_COLLECTION = "tickets"
    VECTOR_SIZE = 1536
    
    @staticmethod
    def _get_qdrant_client() -> AsyncQdrantClient:
        """Get async Qdrant client instance"""
        return AsyncQdrantClient(
            url=AsyncEmbeddingManager.QDRANT_URL,
            api_key=AsyncEmbeddingManager.QDRANT_API_KEY,
            timeout=30.0
        )
    
    @staticmethod
    async def _ensure_qdrant_collection() -> bool:
        """Async ensure Qdrant collection exists"""
        try:
            client = AsyncEmbeddingManager._get_qdrant_client()
            try:
                await client.get_collection(AsyncEmbeddingManager.QDRANT_COLLECTION)
                return True
            except Exception as e:
                error_str = str(e).lower()
                
                if "validation error" in error_str and "parsing" in error_str:
                    logger.debug(f"Collection check returned validation error (likely schema mismatch)")
                    return True
                
                if "not found" in error_str:
                    logger.info(f"Creating Qdrant collection '{AsyncEmbeddingManager.QDRANT_COLLECTION}'...")
                    try:
                        await client.create_collection(
                            collection_name=AsyncEmbeddingManager.QDRANT_COLLECTION,
                            vectors_config=VectorParams(
                                size=AsyncEmbeddingManager.VECTOR_SIZE,
                                distance=Distance.COSINE
                            )
                        )
                        logger.info(f"✓ Created Qdrant collection")
                        return True
                    except Exception as create_error:
                        if "already exists" in str(create_error).lower():
                            logger.debug("Collection already exists")
                            return True
                        raise create_error
                else:
                    raise e
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")
            return False
    
    @staticmethod
    async def _sync_embedding_to_qdrant(
        db: AsyncSession,
        embedding_obj: Embedding,
        ticket_id: str,
        company_id: str,
        source_type: str,
        text_content: str
    ) -> Optional[str]:
        """
        Async sync a single embedding to Qdrant and update vector_id.
        
        Args:
            db: SQLAlchemy async session
            embedding_obj: The Embedding object to update
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            source_type: Type of embedding
            text_content: Text content of the embedding
            
        Returns:
            Point ID in Qdrant if successful, None otherwise
        """
        try:
            if not await AsyncEmbeddingManager._ensure_qdrant_collection():
                return None
            
            # Generate vector for text (async)
            vector = await AsyncEmbeddingManager._api_client.get_embedding_vector(text_content)
            if not vector:
                logger.warning(f"Failed to generate vector for embedding {embedding_obj.id}")
                return None
            
            # Create Qdrant point
            point_id = str(uuid_lib.uuid4())
            client = AsyncEmbeddingManager._get_qdrant_client()
            
            await client.upsert(
                collection_name=AsyncEmbeddingManager.QDRANT_COLLECTION,
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
                            "is_active": embedding_obj.is_active,
                            "attachment_id": str(embedding_obj.attachment_id) if embedding_obj.attachment_id else None,
                            "rca_attachment_id": str(embedding_obj.rca_attachment_id) if embedding_obj.rca_attachment_id else None,
                        }
                    )
                ]
            )
            
            # Update embedding object with vector_id
            embedding_obj.vector_id = point_id
            flag_modified(embedding_obj, "vector_id")
            
            logger.info(f"✓ Synced {source_type} embedding to Qdrant async (id={point_id[:8]}...)")
            return point_id
            
        except Exception as e:
            logger.warning(f"Failed to sync embedding to Qdrant async: {e}")
            return None
    
    @staticmethod
    async def _delete_qdrant_embedding_async(
        embedding_id: str,
        vector_id: str
    ) -> bool:
        """
        Async delete an embedding from Qdrant.
        
        Args:
            embedding_id: UUID of the embedding in PostgreSQL
            vector_id: Point ID in Qdrant
            
        Returns:
            True if successful, False otherwise
        """
        try:
            client = AsyncEmbeddingManager._get_qdrant_client()
            await client.delete(
                collection_name=AsyncEmbeddingManager.QDRANT_COLLECTION,
                points_selector=[vector_id]
            )
            logger.info(f"✓ Deleted Qdrant embedding async {embedding_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete Qdrant embedding {embedding_id}: {e}")
            return False
    
    @staticmethod
    async def create_ticket_embeddings_async(
        db: AsyncSession,
        ticket_id: str,
        company_id: str,
        subject: str,
        description: str,
        category: Optional[str] = None,
        summary: Optional[str] = None
    ) -> bool:
        """
        Async create embeddings for a new ticket.
        Stores in PostgreSQL and syncs to Qdrant immediately.
        
        Args:
            db: SQLAlchemy async session
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            subject: Ticket subject
            description: Detailed description
            category: Ticket category
            summary: Optional summary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            ticket_uuid = UUID(ticket_id)
            company_uuid = UUID(company_id)
            
            logger.info(f"Creating embeddings async for ticket {ticket_id}")
            
            embedding_count = 0
            synced_count = 0
            
            # Create embedding for subject/summary
            subject_text = f"{subject}"
            if category:
                subject_text += f" [{category}]"
            
            try:
                vector = await AsyncEmbeddingManager._api_client.get_embedding_vector(subject_text)
                if vector:
                    emb = Embedding(
                        company_id=company_uuid,
                        ticket_id=ticket_uuid,
                        source_type="ticket_summary",
                        text_content=subject_text[:2000],
                        is_active=True
                    )
                    db.add(emb)
                    await db.flush()
                    
                    # Sync to Qdrant
                    point_id = await AsyncEmbeddingManager._sync_embedding_to_qdrant(
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
                    logger.debug(f"✓ Added subject embedding async for ticket {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to embed subject: {e}")
            
            # Embed description
            try:
                vector = await AsyncEmbeddingManager._api_client.get_embedding_vector(description)
                if vector:
                    emb = Embedding(
                        company_id=company_uuid,
                        ticket_id=ticket_uuid,
                        source_type="ticket_description",
                        text_content=description[:2000],
                        is_active=True
                    )
                    db.add(emb)
                    await db.flush()
                    
                    point_id = await AsyncEmbeddingManager._sync_embedding_to_qdrant(
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
                    logger.debug(f"✓ Added description embedding async for ticket {ticket_id}")
            except Exception as e:
                logger.warning(f"Failed to embed description: {e}")
            
            await db.commit()
            logger.info(f"✓ Created {embedding_count} embeddings async, synced {synced_count} to Qdrant")
            return True
        
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to create ticket embeddings async: {e}")
            return False