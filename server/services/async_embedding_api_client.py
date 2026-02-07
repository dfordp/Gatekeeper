# server/services/async_embedding_api_client.py
"""
Async OpenAI Embedding API Client with semaphore rate limiting

Converts synchronous OpenAI calls to async with:
- AsyncOpenAI client
- Semaphore to limit concurrent requests (max 5)
- Same caching and retry logic as sync version
"""

import hashlib
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from core.config import OPENAI_API_KEY
from core.logger import get_logger

logger = get_logger(__name__)

try:
    from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
except ImportError:
    logger.warning("OpenAI SDK not installed. Install with: pip install openai")
    AsyncOpenAI = None


class AsyncEmbeddingCache:
    """Simple in-memory cache for embeddings (async-safe)"""
    
    def __init__(self, ttl_hours: int = 24):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(hours=ttl_hours)
        self.hits = 0
        self.misses = 0
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache (synchronous operation)"""
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
        """Store embedding in cache (synchronous operation)"""
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


class AsyncEmbeddingAPIClient:
    """Async OpenAI Embedding API client with semaphore rate limiting"""
    
    # Configuration
    MODEL = "text-embedding-3-small"
    MODEL_LARGE = "text-embedding-3-large"
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1  # seconds
    MAX_BACKOFF = 32  # seconds
    BATCH_SIZE = 100
    TIMEOUT = 30
    MAX_CONCURRENT_REQUESTS = 5  # Semaphore limit for OpenAI API
    
    def __init__(self, api_key: Optional[str] = None, use_cache: bool = True):
        """Initialize async embedding client with semaphore"""
        self.api_key = api_key or OPENAI_API_KEY
        self.use_cache = use_cache
        self.cache = AsyncEmbeddingCache() if use_cache else None
        self.total_cost = 0.0
        self.total_tokens = 0
        self.request_count = 0
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
        
        if not self.api_key:
            logger.error("OPENAI_API_KEY not configured")
            self.client = None
        else:
            try:
                self.client = AsyncOpenAI(api_key=self.api_key)
                logger.info("✓ AsyncOpenAI client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncOpenAI client: {e}")
                self.client = None
    
    async def get_embedding_vector(
        self,
        text: str,
        model: str = MODEL
    ) -> Optional[List[float]]:
        """
        Async get embedding vector for a single text
        
        Args:
            text: Text to embed
            model: Embedding model to use
            
        Returns:
            List of floats representing the embedding, or None if failed
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid text for embedding")
            return None
        
        # Check cache first (sync operation)
        if self.cache:
            cached = self.cache.get(text)
            if cached is not None:
                return cached
        
        # Call async API with semaphore and retries
        embedding = await self._call_api_with_retry(text, model)
        
        # Cache the result
        if embedding and self.cache:
            self.cache.set(text, embedding)
        
        return embedding
    
    async def batch_embeddings(
        self,
        texts: List[str],
        model: str = MODEL
    ) -> List[Optional[List[float]]]:
        """
        Async get embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to embed
            model: Embedding model to use
            
        Returns:
            List of embedding vectors (None for failed texts)
        """
        if not texts:
            return []
        
        embeddings = [None] * len(texts)
        uncached_texts = []
        uncached_indices = []
        
        # Check cache for each text
        for idx, text in enumerate(texts):
            if self.cache and text:
                cached = self.cache.get(text)
                if cached:
                    embeddings[idx] = cached
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(idx)
            else:
                uncached_texts.append(text)
                uncached_indices.append(idx)
        
        # If all texts were cached
        if not uncached_texts:
            logger.info(f"✓ All {len(texts)} texts found in cache")
            return embeddings
        
        logger.info(f"Embedding {len(uncached_texts)} uncached texts (cache hit for {len(texts) - len(uncached_texts)})")
        
        # Process uncached texts in batches with asyncio
        batch_tasks = []
        for batch_start in range(0, len(uncached_texts), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(uncached_texts))
            batch_texts = uncached_texts[batch_start:batch_end]
            batch_indices = uncached_indices[batch_start:batch_end]
            
            task = self._process_batch(batch_texts, batch_indices, embeddings, model)
            batch_tasks.append(task)
        
        # Wait for all batches to complete
        if batch_tasks:
            await asyncio.gather(*batch_tasks)
        
        return embeddings
    
    async def _process_batch(
        self,
        batch_texts: List[str],
        batch_indices: List[int],
        embeddings: List,
        model: str
    ) -> None:
        """Process a single batch of texts"""
        try:
            batch_embeddings = await self._call_batch_api(batch_texts, model)
            
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
    
    async def _call_api_with_retry(
        self,
        text: str,
        model: str
    ) -> Optional[List[float]]:
        """Async call OpenAI API with semaphore and exponential backoff"""
        if not self.client:
            logger.warning("AsyncOpenAI client not available")
            return None
        
        backoff = self.INITIAL_BACKOFF
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Acquire semaphore to limit concurrent requests
                async with self.semaphore:
                    response = await self.client.embeddings.create(
                        model=model,
                        input=text,
                        timeout=self.TIMEOUT
                    )
                    
                    embedding = response.data[0].embedding
                    self.request_count += 1
                    
                    # Track usage
                    if hasattr(response, 'usage'):
                        self.total_tokens += response.usage.total_tokens
                        self.total_cost += (response.usage.total_tokens / 1_000_000) * 0.02
                    
                    logger.debug(f"✓ Async embedding created (model={model}, tokens={len(embedding)})")
                    return embedding
            
            except RateLimitError:
                logger.warning(f"Rate limited, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except (APIConnectionError, APIError) as e:
                logger.warning(f"API error: {e}, retrying in {backoff}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except Exception as e:
                logger.error(f"Unexpected error during async embedding: {e}")
                return None
        
        logger.error(f"Failed to embed text after {self.MAX_RETRIES} retries")
        return None
    
    async def _call_batch_api(
        self,
        texts: List[str],
        model: str
    ) -> List[Optional[List[float]]]:
        """Async call OpenAI API for batch embeddings with semaphore"""
        if not self.client:
            logger.warning("AsyncOpenAI client not available")
            return [None] * len(texts)
        
        backoff = self.INITIAL_BACKOFF
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with self.semaphore:
                    response = await self.client.embeddings.create(
                        model=model,
                        input=texts,
                        timeout=self.TIMEOUT
                    )
                    
                    # Sort by index to match input order
                    embeddings_dict = {item.index: item.embedding for item in response.data}
                    embeddings = [embeddings_dict.get(i) for i in range(len(texts))]
                    
                    self.request_count += 1
                    
                    if hasattr(response, 'usage'):
                        self.total_tokens += response.usage.total_tokens
                        self.total_cost += (response.usage.total_tokens / 1_000_000) * 0.02
                    
                    logger.debug(f"✓ Async batch embeddings created (texts={len(texts)}, model={model})")
                    return embeddings
            
            except RateLimitError:
                logger.warning(f"Batch rate limited, retrying in {backoff}s")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
            
            except Exception as e:
                logger.error(f"Batch API error: {e}")
                return [None] * len(texts)
        
        return [None] * len(texts)