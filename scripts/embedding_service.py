#!/usr/bin/env python3
"""
Embedding Service for Gatekeeper Support Platform

Responsibilities:
1. Listen to TicketEvent and AttachmentEvent
2. Extract text from tickets, resolutions, and RCA documents
3. Call embedding API (OpenAI or mock)
4. Store Embedding rows in Postgres
5. Insert vectors into Qdrant

Usage:
    from embedding_service import EmbeddingService
    
    # Embed a newly created ticket
    count = EmbeddingService.embed_ticket_created(ticket_id, company_id)
    
    # Embed a resolution
    count = EmbeddingService.embed_resolution(ticket_id, company_id, resolution_text)
    
    # Deprecate embeddings
    count = EmbeddingService.deprecate_embeddings(ticket_id=ticket_id, reason="reopened")
"""

import os
import sys
import logging
import hashlib
from typing import Optional, List
from datetime import datetime
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import get_db_context, Ticket, Embedding, SessionLocal
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Try to import OpenAI client
try:
    from openai import OpenAI
    if OPENAI_API_KEY:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        HAS_OPENAI = True
    else:
        openai_client = None
        HAS_OPENAI = False
        logger.warning("⚠ OPENAI_API_KEY not set, using mock embeddings")
except ImportError:
    openai_client = None
    HAS_OPENAI = False
    logger.warning("⚠ OpenAI library not installed, using mock embeddings")


class EmbeddingService:
    """Service to create and manage embeddings for semantic search."""
    
    # Configuration constants
    CHUNK_SIZE = 1500
    CHUNK_OVERLAP = 100
    MAX_TEXT_LENGTH = 2000
    _dynamic_thresholds = None
    
    @classmethod
    def _load_thresholds(cls, company_id: str = None):
        """Load thresholds once, cache them."""
        if cls._dynamic_thresholds is None:
            try:
                from adaptive_threshold_service import AdaptiveThresholdService
                
                # If company_id not provided, get the first company from database
                if not company_id:
                    from database import SessionLocal, Company
                    db = SessionLocal()
                    company = db.query(Company).first()
                    db.close()
                    if company:
                        company_id = str(company.id)
                
                if company_id:
                    cls._dynamic_thresholds = AdaptiveThresholdService.calculate_optimal_thresholds(
                        company_id
                    )
                else:
                    # No company found, use defaults
                    logger.warning("No company found in database, using default thresholds")
                    cls._dynamic_thresholds = cls._get_default_thresholds()
            except Exception as e:
                logger.warning(f"Could not load adaptive thresholds: {e}, using defaults")
                cls._dynamic_thresholds = cls._get_default_thresholds()
        return cls._dynamic_thresholds

    @classmethod
    def _get_default_thresholds(cls) -> dict:
        """Get default thresholds."""
        return {
            "Login / Access": 0.55,
            "License": 0.55,
            "Performance": 0.50,
            "Installation": 0.55,
            "Upload or Save": 0.55,
            "Workflow": 0.50,
            "Integration": 0.55,
            "Data / Configuration": 0.55,
            "Other": 0.55
        }
        
    # Confidence thresholds per category
    # For cosine similarity: 0.5-0.6 = similar, 0.7+ = very similar
    CONFIDENCE_THRESHOLDS = {
        "Login / Access": 0.55,      # Reduced from 0.80
        "License": 0.55,              # Reduced from 0.82
        "Performance": 0.50,          # Reduced from 0.70
        "Installation": 0.55,         # Reduced from 0.75
        "Upload or Save": 0.55,       # Reduced from 0.75
        "Workflow": 0.50,             # Reduced from 0.70
        "Integration": 0.55,          # Reduced from 0.75
        "Data / Configuration": 0.55, # Reduced from 0.75
        "Other": 0.55                 # Reduced from 0.75
    }
    
    @staticmethod
    def get_embedding_vector(text: str) -> Optional[List[float]]:
        """
        Get embedding vector for text.
        Uses OpenAI API if available, otherwise generates mock vector.
        
        Args:
            text: Text to embed (will be truncated to 2000 chars)
            
        Returns:
            List of 1536 floats representing the embedding, or None if error
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to embedding")
            return None
        
        try:
            if HAS_OPENAI and openai_client:
                # Use OpenAI API
                response = openai_client.embeddings.create(
                    input=text[:EmbeddingService.MAX_TEXT_LENGTH],
                    model=EMBEDDING_MODEL
                )
                vector = response.data[0].embedding
                logger.debug(f"✓ Generated embedding via OpenAI ({len(text)} chars)")
                return vector
            else:
                # Mock embedding for testing
                text_hash = hashlib.md5(text.encode()).hexdigest()
                vector = [float(int(text_hash[i:i+2], 16)) / 256.0 for i in range(0, 32, 2)]
                vector = vector + [0.0] * (1536 - len(vector))
                vector = vector[:1536]
                logger.debug(f"✓ Generated mock embedding ({len(text)} chars)")
                return vector
                
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    @staticmethod
    def chunk_text(text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks (max CHUNK_SIZE chars, with CHUNK_OVERLAP)
        """
        if len(text) <= EmbeddingService.CHUNK_SIZE:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + EmbeddingService.CHUNK_SIZE, len(text))
            chunk = text[start:end]
            chunks.append(chunk)
            # Move start back by overlap amount for next chunk
            start = end - EmbeddingService.CHUNK_OVERLAP
        
        return chunks
    
    @staticmethod
    def embed_ticket_created(ticket_id: str, company_id: str) -> int:
        """
        Embed a newly created ticket.
        Creates embeddings for summary and detailed_description.
        
        Called when:
            TicketEvent.event_type = 'created'
        
        Args:
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            
        Returns:
            Count of embeddings created
        """
        logger.info(f"Embedding ticket {ticket_id}...")
        count = 0
        db = SessionLocal()
        
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                logger.error(f"Ticket not found: {ticket_id}")
                return 0
            
            # Embed summary
            if ticket.summary:
                logger.debug(f"  Embedding summary ({len(ticket.summary)} chars)")
                vector = EmbeddingService.get_embedding_vector(ticket.summary)
                if vector:
                    emb = Embedding(
                        company_id=company_id,
                        ticket_id=ticket_id,
                        source_type="ticket_summary",
                        chunk_index=0,
                        text_content=ticket.summary[:EmbeddingService.MAX_TEXT_LENGTH],
                        vector_id=str(uuid.uuid4()),
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()
                    count += 1
                    logger.debug(f"    ✓ Created embedding {emb.id}")
            
            # Embed detailed description (with chunking)
            if ticket.detailed_description:
                chunks = EmbeddingService.chunk_text(ticket.detailed_description)
                logger.debug(f"  Chunked description into {len(chunks)} pieces")
                
                for idx, chunk in enumerate(chunks):
                    vector = EmbeddingService.get_embedding_vector(chunk)
                    if vector:
                        emb = Embedding(
                            company_id=company_id,
                            ticket_id=ticket_id,
                            source_type="ticket_description",
                            chunk_index=idx,
                            text_content=chunk[:EmbeddingService.MAX_TEXT_LENGTH],
                            vector_id=str(uuid.uuid4()),
                            is_active=True
                        )
                        db.add(emb)
                        db.flush()
                        count += 1
                        logger.debug(f"    ✓ Created embedding {emb.id} (chunk {idx})")
            
            db.commit()
            logger.info(f"✓ Embedded ticket {ticket_id}: {count} vectors created")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to embed ticket: {e}")
            return 0
        finally:
            db.close()
        
        return count
    
    @staticmethod
    def embed_resolution(ticket_id: str, company_id: str, resolution_text: str) -> int:
        """
        Embed resolution text when it's added to a ticket.
        
        Called when:
            TicketEvent.event_type = 'resolution_added'
            payload['resolution_text'] = <text>
        
        Args:
            ticket_id: UUID of the ticket
            company_id: UUID of the company
            resolution_text: The resolution text to embed
            
        Returns:
            Count of embeddings created
        """
        logger.info(f"Embedding resolution for ticket {ticket_id}...")
        count = 0
        db = SessionLocal()
        
        try:
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                logger.error(f"Ticket not found: {ticket_id}")
                return 0
            
            # Chunk resolution text
            chunks = EmbeddingService.chunk_text(resolution_text)
            logger.debug(f"  Chunked resolution into {len(chunks)} pieces")
            
            for idx, chunk in enumerate(chunks):
                vector = EmbeddingService.get_embedding_vector(chunk)
                if vector:
                    emb = Embedding(
                        company_id=company_id,
                        ticket_id=ticket_id,
                        source_type="resolution",
                        chunk_index=idx,
                        text_content=chunk[:EmbeddingService.MAX_TEXT_LENGTH],
                        vector_id=str(uuid.uuid4()),
                        is_active=True
                    )
                    db.add(emb)
                    db.flush()
                    count += 1
                    logger.debug(f"    ✓ Created embedding {emb.id} (chunk {idx})")
            
            db.commit()
            logger.info(f"✓ Embedded resolution for ticket {ticket_id}: {count} vectors created")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to embed resolution: {e}")
            return 0
        finally:
            db.close()
        
        return count
    
    @staticmethod
    def deprecate_embeddings(
        ticket_id: str = None,
        attachment_id: str = None,
        reason: str = None
    ) -> int:
        """
        Mark embeddings as inactive (soft delete).
        Does NOT delete from database, just sets is_active = False.
        
        Called when:
            - Ticket is reopened
            - Attachment is replaced
            - Resolution is marked invalid
        
        Args:
            ticket_id: (Optional) Only deprecate embeddings for this ticket
            attachment_id: (Optional) Only deprecate embeddings for this attachment
            reason: Reason for deprecation (e.g., 'reopened', 'attachment_replaced')
            
        Returns:
            Count of embeddings deprecated
        """
        logger.info(f"Deprecating embeddings (reason: {reason})...")
        count = 0
        db = SessionLocal()
        
        try:
            query = db.query(Embedding)
            
            if ticket_id:
                query = query.filter(Embedding.ticket_id == ticket_id)
            if attachment_id:
                query = query.filter(Embedding.attachment_id == attachment_id)
            
            # Find all active embeddings matching criteria
            embeddings = query.filter(Embedding.is_active == True).all()
            
            for emb in embeddings:
                emb.is_active = False
                emb.deprecated_at = datetime.utcnow()
                emb.deprecation_reason = reason or "manual_deprecation"
                count += 1
            
            db.commit()
            logger.info(f"✓ Deprecated {count} embeddings (reason: {reason})")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to deprecate embeddings: {e}")
            return 0
        finally:
            db.close()
        
        return count
    
    @staticmethod
    def get_confidence_threshold(category: str, company_id: str = None) -> float:
        """
        Get confidence threshold for a category.
        Now dynamically calculated based on actual search performance!
        
        Args:
            category: Ticket category
            company_id: Optional - uses this company's data to calculate
            
        Returns:
            Optimal threshold based on historical performance
        """
        thresholds = EmbeddingService._load_thresholds(company_id)
        return thresholds.get(category, thresholds.get("Other", 0.55))
    
    @staticmethod
    def get_stats() -> dict:
        """
        Get statistics about embeddings in the system.
        
        Returns:
            Dict with counts of active/inactive embeddings
        """
        db = SessionLocal()
        try:
            total = db.query(Embedding).count()
            active = db.query(Embedding).filter(Embedding.is_active == True).count()
            inactive = db.query(Embedding).filter(Embedding.is_active == False).count()
            
            return {
                "total_embeddings": total,
                "active_embeddings": active,
                "inactive_embeddings": inactive
            }
        finally:
            db.close()


# ==================== Test Script ====================

if __name__ == "__main__":
    """Test the embedding service with the seeded test data."""
    
    logger.info("\n" + "="*70)
    logger.info("  EMBEDDING SERVICE TEST")
    logger.info("="*70 + "\n")
    
    # Get test ticket from database
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).first()
        if not ticket:
            logger.error("No tickets found in database. Run migration with --seed first.")
            sys.exit(1)
        
        logger.info(f"Found test ticket: {ticket.ticket_no}")
        logger.info(f"Company ID: {ticket.company_id}")
        
        # Embed the ticket
        count = EmbeddingService.embed_ticket_created(str(ticket.id), str(ticket.company_id))
        
        # Show stats
        stats = EmbeddingService.get_stats()
        logger.info(f"\nEmbedding Statistics:")
        logger.info(f"  Total embeddings: {stats['total_embeddings']}")
        logger.info(f"  Active embeddings: {stats['active_embeddings']}")
        logger.info(f"  Inactive embeddings: {stats['inactive_embeddings']}")
        
        logger.info("\n✓ Embedding service test completed\n")
        
    finally:
        db.close()