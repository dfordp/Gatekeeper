#!/usr/bin/env python3
"""
Qdrant Vector Database Wrapper

Handles all Qdrant operations:
- Collection initialization and management
- Inserting embedding vectors
- Searching for similar solutions
- Updating and deprecating vectors
- Company isolation via filters

Configuration:
    QDRANT_HOST: localhost (default)
    QDRANT_PORT: 6333 (default)
    QDRANT_API_KEY: from environment
    COLLECTION_NAME: support_solutions
    VECTOR_SIZE: 1536 (OpenAI text-embedding-3-small)
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    Range
)
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "qdrant_secure_key_123")
COLLECTION_NAME = "support_solutions"
VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small dimensions


@dataclass
class SearchResult:
    """Result from a Qdrant search."""
    score: float
    payload: Dict[str, Any]


class QdrantWrapper:
    """Wrapper around Qdrant client for vector operations."""
    
    def __init__(self):
        """Initialize Qdrant client and ensure collection exists."""
        try:
            # Use HTTP URL-based initialization to avoid SSL issues
            url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
            self.client = QdrantClient(url=url, api_key=QDRANT_API_KEY, timeout=30.0)
            logger.info(f"✓ Connected to Qdrant at {url}")
            
            # Initialize collection if needed
            self._ensure_collection_exists()
            
        except Exception as e:
            logger.error(f"✗ Failed to connect to Qdrant: {e}")
            raise
    
    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist."""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if COLLECTION_NAME in collection_names:
                logger.info(f"✓ Collection '{COLLECTION_NAME}' exists")
                return
            
            # Create collection
            logger.info(f"Creating collection '{COLLECTION_NAME}'...")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✓ Collection '{COLLECTION_NAME}' created")
            
        except Exception as e:
            logger.error(f"✗ Failed to ensure collection: {e}")
            raise
    
    def insert_embedding(
        self,
        embedding_id: str,
        vector: List[float],
        ticket_id: str,
        company_id: str,
        source_type: str,
        chunk_index: int = 0,
        attachment_id: Optional[str] = None,
        text_content: str = ""
    ) -> bool:
        """
        Insert an embedding into Qdrant.
        
        Args:
            embedding_id: UUID of embedding record
            vector: 1536-dimensional vector
            ticket_id: UUID of associated ticket
            company_id: UUID of company (for isolation)
            source_type: ticket_summary, ticket_description, resolution, rca, log_snippet
            chunk_index: Which chunk if text was split
            attachment_id: UUID of attachment if from attachment
            text_content: Original text for reference
            
        Returns:
            True if successful
        """
        try:
            if not vector or len(vector) != VECTOR_SIZE:
                logger.error(f"Invalid vector size: {len(vector)}")
                return False
            
            point = PointStruct(
                id=self._uuid_to_int(embedding_id),
                vector=vector,
                payload={
                    "embedding_id": embedding_id,
                    "ticket_id": ticket_id,
                    "company_id": company_id,
                    "source_type": source_type,
                    "chunk_index": chunk_index,
                    "attachment_id": attachment_id,
                    "text_content": text_content[:500],  # Store truncated text for reference
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                }
            )
            
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=[point]
            )
            
            logger.debug(f"✓ Inserted embedding {embedding_id} into Qdrant")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to insert embedding: {e}")
            return False
    
    def search(
        self,
        query_vector: List[float],
        company_id: str,
        limit: int = 5,
        score_threshold: float = 0.75,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar solutions.
        
        Args:
            query_vector: Embedded query (1536 dimensions)
            company_id: Filter to this company
            limit: Max results to return
            score_threshold: Minimum similarity score (0.0-1.0)
            category: Optional category filter (not used in search, only in caller)
            
        Returns:
            List of results with score and payload
        """
        try:
            if not query_vector or len(query_vector) != VECTOR_SIZE:
                logger.error(f"Invalid query vector size: {len(query_vector)}")
                return []
            
            # Build filter for company isolation and active embeddings
            filters = Filter(
                must=[
                    FieldCondition(
                        key="company_id",
                        match=MatchValue(value=company_id)
                    ),
                    FieldCondition(
                        key="is_active",
                        match=MatchValue(value=True)
                    )
                ]
            )
            
            # Search Qdrant
            search_results = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=filters,
                limit=limit,
                score_threshold=score_threshold
            )
            
            logger.debug(f"Found {len(search_results)} results above threshold {score_threshold}")
            
            # Convert to our format
            results = []
            for result in search_results:
                results.append({
                    "score": result.score,
                    "payload": result.payload
                })
            
            return results
            
        except Exception as e:
            logger.error(f"✗ Search failed: {e}")
            return []
    
    def mark_inactive(
        self,
        embedding_id: str,
        reason: str = "deprecated"
    ) -> bool:
        """
        Mark an embedding as inactive (soft delete).
        
        Args:
            embedding_id: UUID of embedding to deprecate
            reason: Reason for deprecation
            
        Returns:
            True if successful
        """
        try:
            point_id = self._uuid_to_int(embedding_id)
            
            # Update payload to mark inactive
            self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={
                    "is_active": False,
                    "deprecated_at": datetime.utcnow().isoformat(),
                    "deprecation_reason": reason
                },
                points=[point_id]
            )
            
            logger.debug(f"✓ Marked embedding {embedding_id} as inactive")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to mark embedding inactive: {e}")
            return False
    
    def get_company_stats(self, company_id: str) -> Dict[str, Any]:
        """
        Get search statistics for a company.
        
        Args:
            company_id: UUID of company
            
        Returns:
            Dictionary with stats
        """
        try:
            # Count total points for company
            collection_info = self.client.get_collection(COLLECTION_NAME)
            
            # We can get basic count from collection info
            total_count = collection_info.points_count
            
            logger.debug(f"Company {company_id}: {total_count} total points in Qdrant")
            
            return {
                "company_id": company_id,
                "total_points": total_count
            }
            
        except Exception as e:
            logger.error(f"✗ Failed to get stats: {e}")
            return {"company_id": company_id, "total_points": 0}
    
    def health_check(self) -> bool:
        """
        Check if Qdrant is healthy.
        
        Returns:
            True if healthy
        """
        try:
            health = self.client.get_collections()
            logger.debug("✓ Qdrant health check passed")
            return True
        except Exception as e:
            logger.error(f"✗ Qdrant health check failed: {e}")
            return False
    
    @staticmethod
    def _uuid_to_int(uuid_str: str) -> int:
        """
        Convert UUID string to integer for Qdrant point ID.
        Qdrant requires integer or string IDs; we'll use integer for efficiency.
        
        Args:
            uuid_str: UUID string
            
        Returns:
            Integer derived from UUID
        """
        # Take first 8 bytes of UUID hex and convert to int
        # This gives us a stable, collision-resistant integer
        hex_str = uuid_str.replace("-", "")[:16]
        return int(hex_str, 16) % (2**63 - 1)  # Stay within signed 64-bit range


# Global instance
try:
    qdrant = QdrantWrapper()
    logger.info("✓ Qdrant wrapper initialized successfully")
except Exception as e:
    logger.error(f"✗ Failed to initialize Qdrant wrapper: {e}")
    qdrant = None