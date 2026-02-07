# server/routes/search_routes.py
"""Search routes with circuit breaker protection and graceful degradation"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from qdrant_client import AsyncQdrantClient
from services.embedding_api_with_breaker import get_embedding_api_with_breaker
from core.logger import get_logger
from middleware.cache_decorator import cache_endpoint_with_body
from services.cache_key_generator import CacheKeyGenerator

logger = get_logger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

QDRANT_URL = "http://qdrant:6333"
QDRANT_API_KEY = "qdrant_secure_key_123"


class SearchRequest(BaseModel):
    """Search request with query and parameters"""
    query: str
    limit: int = 5
    threshold: float = 0.5
    company_id: Optional[str] = None


@router.post("/tickets/similar")
@cache_endpoint_with_body(
    ttl=120,
    tag="search:similar",
    key_params=["company_id"],
    request_body_fields=["query", "limit", "threshold"],
    endpoint_name="search_similar_tickets"
)
async def search_similar_tickets(request: SearchRequest):
    """
    Search for similar tickets with circuit breaker protection
    
    Graceful degradation:
    - If embedding API available: Search by vector similarity
    - If embedding API unavailable (circuit OPEN): Return empty results
    - User sees "No similar tickets found" rather than API error
    """
    try:
        # Get embedding vector with circuit breaker protection
        embedding_api = get_embedding_api_with_breaker()
        query_vector = await embedding_api.get_embedding_vector(request.query)
        
        # Graceful degradation: if embedding API unavailable
        if query_vector is None:
            logger.warning(f"Embedding API unavailable - returning empty search results")
            return {
                "query": request.query,
                "total_results": 0,
                "results": [],
                "note": "Embedding service temporarily unavailable"
            }
        
        # Search in Qdrant with embedding vector
        qdrant_client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        results = await qdrant_client.search(
            collection_name="tickets",
            query_vector=query_vector,
            limit=request.limit,
            score_threshold=request.threshold
        )
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "similarity_score": result.score,
                "embedding_id": result.payload.get("embedding_id"),
                "ticket_id": result.payload.get("ticket_id"),
                "source_type": result.payload.get("source_type"),
                "text": result.payload.get("text")
            })
        
        logger.info(f"Found {len(formatted_results)} similar tickets for query: {request.query}")
        
        return {
            "query": request.query,
            "total_results": len(formatted_results),
            "results": formatted_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        # Graceful degradation: return empty results instead of error
        return {
            "query": request.query,
            "total_results": 0,
            "results": [],
            "note": "Search temporarily unavailable"
        }


@router.get("/tickets/similar-by-query")
async def search_by_query_string(
    query: str = Query(..., min_length=3, description="Search query"),
    limit: int = Query(5, ge=1, le=20),
    threshold: float = Query(0.5, ge=0, le=1),
    company_id: Optional[str] = Query(None)
):
    """
    Alternative search endpoint using query string parameters
    with circuit breaker protection
    """
    try:
        # Get embedding vector with circuit breaker protection
        embedding_api = get_embedding_api_with_breaker()
        query_vector = await embedding_api.get_embedding_vector(query)
        
        # Graceful degradation
        if query_vector is None:
            logger.warning(f"Embedding API unavailable - returning empty search results")
            return {
                "query": query,
                "total_results": 0,
                "results": [],
                "note": "Embedding service temporarily unavailable"
            }
        
        qdrant_client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        results = await qdrant_client.search(
            collection_name="tickets",
            query_vector=query_vector,
            limit=limit,
            score_threshold=threshold
        )
        
        formatted_results = [
            {
                "similarity_score": r.score,
                "embedding_id": r.payload.get("embedding_id"),
                "ticket_id": r.payload.get("ticket_id"),
                "source_type": r.payload.get("source_type"),
                "text": r.payload.get("text")
            }
            for r in results
        ]
        
        result = {
            "query": query,
            "total_results": len(formatted_results),
            "results": formatted_results
        }
        
        logger.info(f"Found {len(formatted_results)} results for query: {query}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        # Graceful degradation
        return {
            "query": query,
            "total_results": 0,
            "results": [],
            "note": "Search temporarily unavailable"
        }