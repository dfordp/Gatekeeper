"""
Fully async embedding service with circuit breaker and timeout protection
"""

import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from services.async_embedding_api_client import AsyncEmbeddingAPIClient
from core.logger import get_logger

logger = get_logger(__name__)


class AsyncEmbeddingService:
    """Async embedding service with circuit breaker and timeout"""
    
    # Circuit breaker for OpenAI API
    _breaker = CircuitBreaker(
        name="openai_embedding_api",
        failure_threshold=5,
        recovery_timeout=60
    )
    
    # API client
    _api_client = AsyncEmbeddingAPIClient()
    
    # Timeout for embedding requests
    EMBEDDING_TIMEOUT = 15.0  # seconds
    
    @staticmethod
    async def get_embedding_with_fallback(
        text: str,
        fallback_enabled: bool = True
    ) -> Optional[List[float]]:
        """
        Get embedding vector with circuit breaker and timeout.
        
        Args:
            text: Text to embed
            fallback_enabled: Use hash-based fallback if API fails
            
        Returns:
            Embedding vector or None if failed
        """
        try:
            # Protect with circuit breaker
            vector = await asyncio.wait_for(
                AsyncEmbeddingService._breaker.call(
                    AsyncEmbeddingService._api_client.get_embedding_vector,
                    text
                ),
                timeout=AsyncEmbeddingService.EMBEDDING_TIMEOUT
            )
            return vector
        
        except CircuitBreakerOpen:
            logger.warning("OpenAI API circuit breaker OPEN - using fallback embedding")
            if fallback_enabled:
                return AsyncEmbeddingService._fallback_embedding(text)
            return None
        
        except asyncio.TimeoutError:
            logger.error(f"Embedding request timeout after {AsyncEmbeddingService.EMBEDDING_TIMEOUT}s")
            if fallback_enabled:
                return AsyncEmbeddingService._fallback_embedding(text)
            return None
        
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            if fallback_enabled:
                return AsyncEmbeddingService._fallback_embedding(text)
            return None
    
    @staticmethod
    def _fallback_embedding(text: str) -> List[float]:
        """Generate hash-based fallback embedding"""
        import hashlib
        import random
        
        hash_obj = hashlib.sha256(text.encode())
        seed = int(hash_obj.hexdigest(), 16)
        
        random.seed(seed)
        embedding = [random.gauss(0, 1) for _ in range(1536)]
        
        # Normalize
        norm = sum(x ** 2 for x in embedding) ** 0.5
        embedding = [x / norm if norm > 0 else x for x in embedding]
        
        return embedding
    
    @staticmethod
    async def batch_embeddings_with_fallback(
        texts: List[str],
        fallback_enabled: bool = True
    ) -> List[Optional[List[float]]]:
        """Batch get embeddings with fallback"""
        try:
            vectors = await asyncio.wait_for(
                AsyncEmbeddingService._breaker.call(
                    AsyncEmbeddingService._api_client.batch_embeddings,
                    texts
                ),
                timeout=30.0
            )
            return vectors
        
        except (CircuitBreakerOpen, asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Batch embedding failed: {e}, using fallback")
            if fallback_enabled:
                return [
                    AsyncEmbeddingService._fallback_embedding(text)
                    for text in texts
                ]
            return [None] * len(texts)