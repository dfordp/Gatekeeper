# server/services/async_embedding_safe.py
"""
Safe async embedding service with circuit breaker and timeout protection
Prevents OpenAI API failures from blocking the event loop
"""

import asyncio
from typing import Optional, List
from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from services.async_embedding_api_client import AsyncEmbeddingAPIClient
from core.logger import get_logger

logger = get_logger(__name__)


class SafeAsyncEmbeddingService:
    """
    Async embedding service with:
    - Circuit breaker protection
    - Timeout protection
    - Fallback embeddings
    - Graceful degradation
    """
    
    # Circuit breaker with 5-failure threshold
    _breaker = CircuitBreaker(
        name="openai_embedding_api",
        failure_threshold=5,
        success_threshold=2,
        recovery_timeout=60
    )
    
    # API client with semaphore (max 5 concurrent)
    _api_client = AsyncEmbeddingAPIClient()
    
    # Timeout for embedding requests
    EMBEDDING_TIMEOUT = 15.0  # seconds
    BATCH_TIMEOUT = 30.0  # seconds
    
    @staticmethod
    async def get_embedding_with_fallback(
        text: str,
        fallback_enabled: bool = True,
        timeout: Optional[float] = None
    ) -> Optional[List[float]]:
        """
        Get embedding vector with full protection.
        
        Args:
            text: Text to embed
            fallback_enabled: Use hash-based fallback if API fails
            timeout: Custom timeout (default: 15s)
            
        Returns:
            Embedding vector or None if failed
        """
        timeout = timeout or SafeAsyncEmbeddingService.EMBEDDING_TIMEOUT
        
        try:
            # Protect with circuit breaker + timeout
            vector = await asyncio.wait_for(
                SafeAsyncEmbeddingService._breaker.call(
                    SafeAsyncEmbeddingService._api_client.get_embedding_vector,
                    text
                ),
                timeout=timeout
            )
            
            if vector:
                return vector
            
            # API returned None
            if fallback_enabled:
                logger.warning("Embedding API returned None, using fallback")
                return SafeAsyncEmbeddingService._fallback_embedding(text)
            return None
        
        except CircuitBreakerOpen:
            logger.warning("OpenAI API circuit breaker OPEN - using fallback")
            if fallback_enabled:
                return SafeAsyncEmbeddingService._fallback_embedding(text)
            return None
        
        except asyncio.TimeoutError:
            logger.error(f"Embedding timeout after {timeout}s - using fallback")
            if fallback_enabled:
                return SafeAsyncEmbeddingService._fallback_embedding(text)
            return None
        
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            if fallback_enabled:
                return SafeAsyncEmbeddingService._fallback_embedding(text)
            return None
    
    @staticmethod
    async def batch_embeddings_with_fallback(
        texts: List[str],
        fallback_enabled: bool = True,
        timeout: Optional[float] = None
    ) -> List[Optional[List[float]]]:
        """
        Get batch embeddings with full protection.
        
        Args:
            texts: List of texts to embed
            fallback_enabled: Use fallback for failures
            timeout: Custom timeout (default: 30s)
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        timeout = timeout or SafeAsyncEmbeddingService.BATCH_TIMEOUT
        
        try:
            vectors = await asyncio.wait_for(
                SafeAsyncEmbeddingService._breaker.call(
                    SafeAsyncEmbeddingService._api_client.batch_embeddings,
                    texts
                ),
                timeout=timeout
            )
            
            # Fill None entries with fallback if enabled
            if fallback_enabled and any(v is None for v in vectors):
                logger.warning(f"Some embeddings failed, using fallback for {sum(1 for v in vectors if v is None)} items")
                vectors = [
                    v or SafeAsyncEmbeddingService._fallback_embedding(text)
                    for v, text in zip(vectors, texts)
                ]
            
            return vectors
        
        except (CircuitBreakerOpen, asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Batch embedding failed: {e}, using fallback")
            if fallback_enabled:
                return [
                    SafeAsyncEmbeddingService._fallback_embedding(text)
                    for text in texts
                ]
            return [None] * len(texts)
    
    @staticmethod
    def _fallback_embedding(text: str) -> List[float]:
        """
        Generate hash-based fallback embedding (deterministic and fast).
        
        Args:
            text: Text to embed
            
        Returns:
            1536-dimensional embedding vector
        """
        import hashlib
        import random
        
        # Use SHA256 hash as seed for reproducibility
        hash_obj = hashlib.sha256(text.encode())
        seed = int(hash_obj.hexdigest(), 16)
        
        # Generate pseudo-random vector with seed
        random.seed(seed)
        embedding = [random.gauss(0, 1) for _ in range(1536)]  # text-embedding-3-small dims
        
        # L2 normalize
        norm = sum(x ** 2 for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding