# server/services/embedding_api_client.py
"""
OpenAI Embedding API Client with caching and batch operations

Wraps the OpenAI API for creating text embeddings.
Features:
- Automatic retries with exponential backoff
- In-memory caching to reduce API calls
- Batch embedding operations
- Cost tracking and logging
- Fallback to hash-based embeddings if API fails
"""

import hashlib
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from core.config import OPENAI_API_KEY
from core.logger import get_logger

logger = get_logger(__name__)

try:
    from openai import OpenAI, RateLimitError, APIError, APIConnectionError
except ImportError:
    logger.warning("OpenAI SDK not installed. Install with: pip install openai")
    OpenAI = None


class EmbeddingCache:
    """Simple in-memory cache for embeddings"""
    
    def __init__(self, ttl_hours: int = 24):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(hours=ttl_hours)
        self.hits = 0
        self.misses = 0
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache"""
        key = hashlib.md5(text.encode()).hexdigest()
        
        if key in self.cache:
            entry = self.cache[key]
            if datetime.utcnow() < entry["expires_at"]:
                self.hits += 1
                logger.debug(f"✓ Cache hit for text (length={len(text)})")
                return entry["embedding"]
            else:
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, text: str, embedding: List[float]) -> None:
        """Store embedding in cache"""
        key = hashlib.md5(text.encode()).hexdigest()
        self.cache[key] = {
            "embedding": embedding,
            "expires_at": datetime.utcnow() + self.ttl,
            "text_length": len(text)
        }
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total,
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_embeddings": len(self.cache)
        }


class EmbeddingAPIClient:
    """OpenAI Embedding API client with retry logic and caching"""
    
    # Configuration
    MODEL = "text-embedding-3-small"  # Cost-efficient model
    MODEL_LARGE = "text-embedding-3-large"  # Higher quality (if needed)
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1  # seconds
    MAX_BACKOFF = 32  # seconds
    BATCH_SIZE = 100  # Max texts per batch API call
    TIMEOUT = 30  # seconds per request
    
    def __init__(self, api_key: Optional[str] = None, use_cache: bool = True):
        """
        Initialize the embedding client
        
        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            use_cache: Whether to use in-memory caching
        """
        self.api_key = api_key or OPENAI_API_KEY
        self.use_cache = use_cache
        self.cache = EmbeddingCache() if use_cache else None
        self.total_cost = 0.0
        self.total_tokens = 0
        self.request_count = 0
        
        if not self.api_key:
            logger.error("OPENAI_API_KEY not configured")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                logger.info("✓ OpenAI client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None
    
    def get_embedding_vector(
        self,
        text: str,
        model: str = MODEL
    ) -> Optional[List[float]]:
        """
        Get embedding vector for a single text
        
        Args:
            text: Text to embed
            model: Embedding model to use
            
        Returns:
            List of floats representing the embedding, or None if failed
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid text for embedding")
            return None
        
        # Check cache first
        if self.cache:
            cached = self.cache.get(text)
            if cached is not None:
                return cached
        
        # Call API with retries
        embedding = self._call_api_with_retry(text, model)
        
        # Cache the result
        if embedding and self.cache:
            self.cache.set(text, embedding)
        
        return embedding
    
    def batch_embeddings(
        self,
        texts: List[str],
        model: str = MODEL
    ) -> List[Optional[List[float]]]:
        """
        Get embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to embed
            model: Embedding model to use
            
        Returns:
            List of embedding vectors (None for failed texts)
        """
        if not texts:
            return []
        
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        # Check cache for each text
        for idx, text in enumerate(texts):
            if self.cache and text:
                cached = self.cache.get(text)
                if cached:
                    embeddings.append(cached)
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(idx)
            else:
                embeddings.append(None)
                uncached_texts.append(text)
                uncached_indices.append(idx)
        
        # If all texts were cached
        if not uncached_texts:
            logger.info(f"✓ All {len(texts)} texts found in cache")
            return embeddings
        
        logger.info(f"Embedding {len(uncached_texts)} uncached texts (cache hit for {len(texts) - len(uncached_texts)})")
        
        # Process uncached texts in batches
        for batch_start in range(0, len(uncached_texts), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(uncached_texts))
            batch_texts = uncached_texts[batch_start:batch_end]
            batch_indices = uncached_indices[batch_start:batch_end]
            
            try:
                batch_embeddings = self._call_batch_api(batch_texts, model)
                
                for i, emb in enumerate(batch_embeddings):
                    original_idx = batch_indices[i]
                    embeddings[original_idx] = emb
                    
                    # Cache successful embeddings
                    if emb and self.cache:
                        self.cache.set(batch_texts[i], emb)
            
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                for original_idx in batch_indices:
                    embeddings[original_idx] = None
        
        return embeddings
    
    def _call_api_with_retry(
        self,
        text: str,
        model: str
    ) -> Optional[List[float]]:
        """
        Call OpenAI API with exponential backoff retry logic
        
        Args:
            text: Text to embed
            model: Embedding model
            
        Returns:
            Embedding vector or None if all retries failed
        """
        if not self.client:
            logger.warning("OpenAI client not available")
            return self._fallback_embedding(text)
        
        backoff = self.INITIAL_BACKOFF
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.embeddings.create(
                    model=model,
                    input=text,
                    timeout=self.TIMEOUT
                )
                
                embedding = response.data[0].embedding
                self.request_count += 1
                
                # Track usage
                if hasattr(response, 'usage'):
                    self.total_tokens += response.usage.total_tokens
                    # Cost calculation: $0.02 per 1M tokens for text-embedding-3-small
                    self.total_cost += (response.usage.total_tokens / 1_000_000) * 0.02
                
                logger.debug(f"✓ Embedding created (model={model}, tokens={len(embedding)})")
                return embedding
            
            except RateLimitError:
                logger.warning(f"Rate limited, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except (APIConnectionError, APIError) as e:
                logger.warning(f"API error: {e}, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except Exception as e:
                logger.error(f"Unexpected error during embedding: {e}")
                return self._fallback_embedding(text)
        
        logger.error(f"Failed to embed text after {self.MAX_RETRIES} retries")
        return self._fallback_embedding(text)
    
    def _call_batch_api(
        self,
        texts: List[str],
        model: str
    ) -> List[Optional[List[float]]]:
        """
        Call OpenAI API for batch embeddings
        
        Args:
            texts: Texts to embed
            model: Embedding model
            
        Returns:
            List of embedding vectors
        """
        if not self.client:
            logger.warning("OpenAI client not available, using fallback")
            return [self._fallback_embedding(text) for text in texts]
        
        backoff = self.INITIAL_BACKOFF
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.embeddings.create(
                    model=model,
                    input=texts,
                    timeout=self.TIMEOUT
                )
                
                # Sort by index to maintain order
                embeddings_by_index = {item.index: item.embedding for item in response.data}
                embeddings = [embeddings_by_index.get(i) for i in range(len(texts))]
                
                self.request_count += 1
                
                # Track usage
                if hasattr(response, 'usage'):
                    self.total_tokens += response.usage.total_tokens
                    self.total_cost += (response.usage.total_tokens / 1_000_000) * 0.02
                
                logger.info(f"✓ Batch embedding created ({len(texts)} texts, model={model})")
                return embeddings
            
            except RateLimitError:
                logger.warning(f"Rate limited, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except (APIConnectionError, APIError) as e:
                logger.warning(f"API error: {e}, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except Exception as e:
                logger.error(f"Unexpected error during batch embedding: {e}")
                return [self._fallback_embedding(text) for text in texts]
        
        logger.error(f"Failed batch embedding after {self.MAX_RETRIES} retries")
        return [self._fallback_embedding(text) for text in texts]
    
    def _fallback_embedding(self, text: str) -> List[float]:
        """
        Fallback: Generate a deterministic embedding using hash
        This ensures embeddings are always available even if API fails
        
        Args:
            text: Text to create fallback embedding for
            
        Returns:
            Deterministic embedding vector (1536 dims to match text-embedding-3-small)
        """
        logger.warning(f"Using fallback embedding for text (length={len(text)})")
        
        # Create deterministic seed from text
        hash_object = hashlib.sha256(text.encode())
        seed = int(hash_object.hexdigest(), 16)
        
        # Generate pseudo-random vector (1536 dimensions)
        import random
        random.seed(seed)
        embedding = [random.gauss(0, 1) for _ in range(1536)]
        
        # Normalize to unit vector
        norm = sum(x ** 2 for x in embedding) ** 0.5
        embedding = [x / norm if norm > 0 else x for x in embedding]
        
        return embedding
    
    def calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        if len(embedding1) != len(embedding2):
            logger.warning("Embedding dimensions don't match")
            return 0.0
        
        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = sum(a ** 2 for a in embedding1) ** 0.5
        norm2 = sum(b ** 2 for b in embedding2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        stats = {
            "total_requests": self.request_count,
            "total_tokens_used": self.total_tokens,
            "estimated_cost": f"${self.total_cost:.4f}",
            "model": self.MODEL
        }
        
        if self.cache:
            stats["cache"] = self.cache.stats()
        
        return stats


# Global client instance
_client: Optional[EmbeddingAPIClient] = None


def get_embedding_client() -> EmbeddingAPIClient:
    """Get or create the global embedding client"""
    global _client
    if _client is None:
        _client = EmbeddingAPIClient()
    return _client


def get_embedding_vector(text: str) -> Optional[List[float]]:
    """Convenience function to get embedding for text"""
    client = get_embedding_client()
    return client.get_embedding_vector(text)


def batch_get_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """Convenience function for batch embeddings"""
    client = get_embedding_client()
    return client.batch_embeddings(texts)