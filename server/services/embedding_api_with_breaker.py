# server/services/embedding_api_with_breaker.py
"""
Embedding API Client with Circuit Breaker Protection

Wraps AsyncEmbeddingAPIClient with circuit breaker pattern to prevent
cascade failures when OpenAI API is degraded or unavailable.

Graceful degradation:
- When circuit OPEN: Return zero vectors (128 dims) for fallback search
- When circuit HALF_OPEN: Allow limited requests for recovery testing
- When circuit CLOSED: Normal operation
"""

import asyncio
from typing import List, Optional
from core.circuit_breaker import CircuitBreakerRegistry, CircuitBreakerOpen
from services.async_embedding_api_client import AsyncEmbeddingAPIClient
from core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingAPIWithBreaker:
    """
    Embedding API client protected by circuit breaker
    
    Prevents cascade failures by failing fast when OpenAI API is unavailable.
    """
    
    def __init__(self):
        self.client = AsyncEmbeddingAPIClient()
        self.breaker_name = "embedding_api"
    
    async def get_embedding_vector(self, text: str) -> Optional[List[float]]:
        """
        Get embedding vector for text with circuit breaker protection
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (1536 dims) or None for fallback
            
        Graceful degradation:
        - If circuit OPEN: Returns None (allows graceful fallback in search)
        - If circuit HALF_OPEN: Attempts request (tests recovery)
        - If circuit CLOSED: Normal operation
        """
        try:
            breaker = await CircuitBreakerRegistry.get_breaker(
                name=self.breaker_name,
                failure_threshold=5,      # Open after 5 failures
                success_threshold=2,      # Close after 2 successes
                recovery_timeout=60       # Try recovery after 60s
            )
            
            # Execute through circuit breaker
            vector = await breaker.call(
                self.client.get_embedding_vector,
                text
            )
            return vector
            
        except CircuitBreakerOpen:
            logger.warning(f"Embedding API circuit breaker OPEN - using fallback")
            return None  # Signals caller to use fallback (no embedding search)
        
        except Exception as e:
            logger.error(f"Embedding API error: {e}")
            return None  # Fallback on any other error
    
    async def batch_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Get embeddings for multiple texts with circuit breaker protection
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors or None for fallback
        """
        try:
            breaker = await CircuitBreakerRegistry.get_breaker(
                name=self.breaker_name,
                failure_threshold=5,
                success_threshold=2,
                recovery_timeout=60
            )
            
            # Execute through circuit breaker
            vectors = await breaker.call(
                self.client.batch_embeddings,
                texts
            )
            return vectors
            
        except CircuitBreakerOpen:
            logger.warning(f"Embedding API circuit breaker OPEN - batch request failed")
            return None
        
        except Exception as e:
            logger.error(f"Batch embedding error: {e}")
            return None
    
    async def get_breaker_status(self) -> dict:
        """Get circuit breaker status"""
        breaker = await CircuitBreakerRegistry.get_breaker(self.breaker_name)
        return breaker.get_status()


# Global instance
_embedding_api_with_breaker: Optional[EmbeddingAPIWithBreaker] = None


def get_embedding_api_with_breaker() -> EmbeddingAPIWithBreaker:
    """Get or create global embedding API client with circuit breaker"""
    global _embedding_api_with_breaker
    if _embedding_api_with_breaker is None:
        _embedding_api_with_breaker = EmbeddingAPIWithBreaker()
    return _embedding_api_with_breaker