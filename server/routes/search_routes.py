from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from services.embedding_api_client import EmbeddingAPIClient
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

QDRANT_URL = "http://qdrant:6333"
QDRANT_API_KEY = "qdrant_secure_key_123"

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.5

@router.post("/tickets/similar")
async def search_similar_tickets(request: SearchRequest):
    """Search for similar tickets using semantic similarity"""
    try:
        # Generate embedding for query
        embedding_client = EmbeddingAPIClient()
        query_vector = embedding_client.get_embedding_vector(request.query)
        
        if not query_vector:
            raise HTTPException(status_code=400, detail="Failed to generate query embedding")
        
        # Search in Qdrant
        qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        results = qdrant_client.search(
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
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))