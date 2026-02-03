# server/services/cache_key_generator.py
"""
Cache key generation utilities for complex endpoint parameters

Provides functions to generate consistent cache keys for endpoints with:
- Request body parameters
- Query parameters
- Nested objects
- File uploads
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheKeyGenerator:
    """Generate consistent, deterministic cache keys for complex parameters"""
    
    @staticmethod
    def hash_value(value: Any) -> str:
        """
        Generate hash for any value (supports primitives, dicts, lists, Pydantic models)
        
        Args:
            value: Value to hash
            
        Returns:
            8-character hex hash string
        """
        try:
            # Handle Pydantic BaseModel
            if isinstance(value, BaseModel):
                json_str = value.json()
            # Handle dict and list
            elif isinstance(value, (dict, list)):
                json_str = json.dumps(value, sort_keys=True, default=str)
            # Handle primitives
            else:
                json_str = str(value)
            
            # Generate hash
            hash_obj = hashlib.md5(json_str.encode())
            return hash_obj.hexdigest()[:8]
        
        except Exception as e:
            logger.warning(f"Failed to hash value: {e}, using string representation")
            # Fallback: use string representation
            return hashlib.md5(str(value).encode()).hexdigest()[:8]
    
    @staticmethod
    def generate_from_request_body(
        request_body: BaseModel,
        include_fields: Optional[List[str]] = None
    ) -> str:
        """
        Generate cache key from Pydantic request body
        
        Args:
            request_body: Pydantic model instance
            include_fields: List of fields to include in hash (None = all fields)
            
        Returns:
            8-character hex hash
            
        Example:
            class SearchRequest(BaseModel):
                query: str
                limit: int
                threshold: float
            
            req = SearchRequest(query="payment error", limit=5, threshold=0.5)
            key = CacheKeyGenerator.generate_from_request_body(req)
            # Returns consistent hash for same request
        """
        try:
            if include_fields:
                # Only include specified fields
                data = {
                    field: getattr(request_body, field)
                    for field in include_fields
                    if hasattr(request_body, field)
                }
                json_str = json.dumps(data, sort_keys=True, default=str)
            else:
                # Include all fields from model
                json_str = request_body.json()
            
            hash_obj = hashlib.md5(json_str.encode())
            return hash_obj.hexdigest()[:8]
        
        except Exception as e:
            logger.error(f"Failed to generate key from request body: {e}")
            return "error"
    
    @staticmethod
    def generate_from_query_string(
        query_string: str,
        normalize: bool = True
    ) -> str:
        """
        Generate cache key from query string
        
        Args:
            query_string: Query text
            normalize: Whether to normalize (lowercase, strip whitespace)
            
        Returns:
            8-character hex hash
            
        Example:
            key1 = CacheKeyGenerator.generate_from_query_string("Payment Error")
            key2 = CacheKeyGenerator.generate_from_query_string("payment error")
            # Both return same hash if normalize=True
        """
        try:
            if normalize:
                query_string = query_string.lower().strip()
            
            hash_obj = hashlib.md5(query_string.encode())
            return hash_obj.hexdigest()[:8]
        
        except Exception as e:
            logger.error(f"Failed to generate key from query string: {e}")
            return "error"
    
    @staticmethod
    def generate_from_params(
        params: Dict[str, Any],
        exclude_keys: Optional[List[str]] = None
    ) -> str:
        """
        Generate cache key from parameter dictionary
        
        Args:
            params: Dictionary of parameters
            exclude_keys: Keys to exclude from hash (e.g., ["page", "offset"])
            
        Returns:
            8-character hex hash
            
        Example:
            params = {"query": "error", "limit": 5, "threshold": 0.5}
            key = CacheKeyGenerator.generate_from_params(params)
        """
        try:
            # Filter out excluded keys
            filtered = {
                k: v for k, v in params.items()
                if not exclude_keys or k not in exclude_keys
            }
            
            json_str = json.dumps(filtered, sort_keys=True, default=str)
            hash_obj = hashlib.md5(json_str.encode())
            return hash_obj.hexdigest()[:8]
        
        except Exception as e:
            logger.error(f"Failed to generate key from params: {e}")
            return "error"
    
    @staticmethod
    def build_cache_key(
        base: str,
        *parts: str,
        hash_value: Optional[str] = None
    ) -> str:
        """
        Build a complete cache key from parts
        
        Args:
            base: Base key name (e.g., "search:similar")
            *parts: Additional key parts (e.g., "company-{id}", "limit-5")
            hash_value: Optional hash to append
            
        Returns:
            Complete cache key string
            
        Example:
            key = CacheKeyGenerator.build_cache_key(
                "search:similar",
                "company-abc123",
                "limit-5",
                hash_value="a1b2c3d4"
            )
            # Returns: "search:similar:company-abc123:limit-5:a1b2c3d4"
        """
        key_parts = [base]
        key_parts.extend(parts)
        
        if hash_value:
            key_parts.append(f"hash-{hash_value}")
        
        return ":".join(key_parts)