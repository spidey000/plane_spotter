"""
Database Cache Manager for Twitter Spotter v4

This module provides a comprehensive caching system for Baserow database queries
to reduce API calls and improve performance.
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger
from datetime import datetime, timedelta

class CacheEntry:
    """Represents a cached database entry with metadata"""
    def __init__(self, data: Any, ttl_seconds: int = 300):
        self.data = data
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired"""
        return (time.time() - self.created_at) > self.ttl_seconds
    
    def access(self) -> Any:
        """Access the data and increment access count"""
        self.access_count += 1
        return self.data
    
    def age(self) -> float:
        """Get the age of the cache entry in seconds"""
        return time.time() - self.created_at

class DatabaseCacheManager:
    """
    Manages caching for database queries with multiple layers:
    1. In-memory cache for fast access
    2. Time-based expiration
    3. Access frequency tracking
    """
    
    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl_seconds = default_ttl_seconds
        self.cache: Dict[str, CacheEntry] = {}
        self.stats = {
            'hits': 0,
            'misses': 0,
            'expired': 0,
            'evicted': 0
        }
        self.max_cache_size = 1000  # Maximum number of entries
    
    def _generate_cache_key(self, table_id: int, filters: Optional[Dict] = None, key_field: Optional[str] = None) -> str:
        """Generate a unique cache key for a query"""
        key_parts = [str(table_id)]
        if filters:
            # Sort filters to ensure consistent keys
            sorted_filters = sorted(filters.items())
            key_parts.append(json.dumps(sorted_filters, sort_keys=True))
        if key_field:
            key_parts.append(key_field)
        return ":".join(key_parts)
    
    def _evict_expired_entries(self):
        """Remove expired entries from cache"""
        expired_keys = []
        for key, entry in self.cache.items():
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            self.stats['expired'] += 1
        
        return len(expired_keys)
    
    def _evict_lru_entries(self, target_size: int):
        """Evict least recently used entries to maintain cache size"""
        if len(self.cache) <= target_size:
            return 0
        
        # Sort entries by access count (ascending) and age (descending)
        sorted_entries = sorted(
            self.cache.items(),
            key=lambda x: (x[1].access_count, -x[1].age)
        )
        
        # Evict entries until we're under the target size
        evict_count = len(self.cache) - target_size
        for i in range(evict_count):
            if i < len(sorted_entries):
                key = sorted_entries[i][0]
                del self.cache[key]
                self.stats['evicted'] += 1
        
        return evict_count
    
    async def get_cached_data(self, table_id: int, filters: Optional[Dict] = None, 
                             key_field: Optional[str] = None) -> Optional[Any]:
        """
        Get data from cache if available and not expired
        
        Args:
            table_id: Baserow table ID
            filters: Query filters
            key_field: Field to use as dictionary key
            
        Returns:
            Cached data or None if not available/expired
        """
        cache_key = self._generate_cache_key(table_id, filters, key_field)
        
        # Check if entry exists
        if cache_key not in self.cache:
            self.stats['misses'] += 1
            return None
        
        entry = self.cache[cache_key]
        
        # Check if expired
        if entry.is_expired():
            del self.cache[cache_key]
            self.stats['expired'] += 1
            self.stats['misses'] += 1
            return None
        
        # Return cached data
        self.stats['hits'] += 1
        return entry.access()
    
    async def set_cached_data(self, table_id: int, data: Any, filters: Optional[Dict] = None,
                             key_field: Optional[str] = None, ttl_seconds: Optional[int] = None) -> bool:
        """
        Store data in cache
        
        Args:
            table_id: Baserow table ID
            data: Data to cache
            filters: Query filters
            key_field: Field to use as dictionary key
            ttl_seconds: Time to live in seconds (uses default if not specified)
            
        Returns:
            True if data was cached, False otherwise
        """
        try:
            # Clean up expired entries
            self._evict_expired_entries()
            
            # Evict LRU entries if cache is too large
            self._evict_lru_entries(self.max_cache_size - 1)
            
            # Create cache entry
            cache_key = self._generate_cache_key(table_id, filters, key_field)
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
            self.cache[cache_key] = CacheEntry(data, ttl)
            
            logger.debug(f"Cached data for table {table_id} with key {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to cache data for table {table_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.stats,
            'total_requests': total_requests,
            'hit_rate': round(hit_rate, 2),
            'current_size': len(self.cache),
            'max_size': self.max_cache_size
        }
    
    def clear_cache(self):
        """Clear all cached data"""
        cleared_entries = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {cleared_entries} entries from cache")
    
    def clear_expired(self):
        """Clear only expired entries"""
        expired_count = self._evict_expired_entries()
        logger.info(f"Cleared {expired_count} expired entries from cache")
        return expired_count

# Global cache manager instance
cache_manager = DatabaseCacheManager(default_ttl_seconds=300)

# Decorator for caching database functions
def cached_db_call(ttl_seconds: int = 300, key_field: Optional[str] = None):
    """
    Decorator to cache database function results
    
    Args:
        ttl_seconds: Time to live in seconds
        key_field: Field to use as dictionary key for row dictionaries
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract table_id and config from args/kwargs
            table_id = None
            config = None
            filters = None
            
            # Try to extract parameters from common patterns
            if args:
                # First arg is usually table_id
                if isinstance(args[0], int):
                    table_id = args[0]
                # Look for config in args
                for arg in args:
                    if isinstance(arg, dict) and 'baserow' in arg:
                        config = arg
                        break
            
            # Look for config in kwargs
            if not config:
                for value in kwargs.values():
                    if isinstance(value, dict) and 'baserow' in value:
                        config = value
                        break
            
            # Look for filters in kwargs
            if 'filters' in kwargs:
                filters = kwargs['filters']
            
            # Try to get from cache
            if table_id is not None:
                cached_data = await cache_manager.get_cached_data(
                    table_id, filters, key_field
                )
                if cached_data is not None:
                    return cached_data
            
            # Execute function and cache result
            try:
                result = await func(*args, **kwargs)
                
                # Cache the result
                if table_id is not None:
                    await cache_manager.set_cached_data(
                        table_id, result, filters, key_field, ttl_seconds
                    )
                
                return result
            except Exception as e:
                logger.error(f"Error in cached database call: {e}")
                raise
        
        return wrapper
    return decorator

# Context manager for cache statistics
class CacheStatsContext:
    """Context manager to measure cache performance during operations"""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_stats = None
    
    async def __aenter__(self):
        self.start_stats = cache_manager.get_stats()
        logger.info(f"Starting {self.operation_name} with cache stats: {self.start_stats}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        end_stats = cache_manager.get_stats()
        logger.info(f"Completed {self.operation_name} with cache stats: {end_stats}")
        
        # Calculate differences
        diff_stats = {}
        for key in end_stats:
            if key in self.start_stats:
                diff_stats[key] = end_stats[key] - self.start_stats[key]
        
        logger.info(f"{self.operation_name} cache performance: {diff_stats}")

# Utility functions for common caching patterns
async def get_cached_rows_as_dict(table_id: int, config: Dict, key: str = "registration", 
                                 ttl_seconds: int = 300) -> Dict[str, Any]:
    """
    Get all rows from a table as a dictionary with caching
    
    Args:
        table_id: Baserow table ID
        config: Configuration dictionary
        key: Field to use as dictionary key
        ttl_seconds: Cache TTL in seconds
        
    Returns:
        Dictionary of rows keyed by the specified field
    """
    # Try to get from cache first
    cached_data = await cache_manager.get_cached_data(table_id, None, key)
    if cached_data is not None:
        return cached_data
    
    # Import here to avoid circular imports
    import database.baserow_manager as bm
    
    # Fetch from database
    try:
        data = await bm.get_all_rows_as_dict(table_id, config, key)
        
        # Cache the result
        await cache_manager.set_cached_data(table_id, data, None, key, ttl_seconds)
        
        return data
    except Exception as e:
        logger.error(f"Failed to fetch rows from table {table_id}: {e}")
        raise

async def get_cached_single_row(table_id: int, config: Dict, filters: Dict, 
                               ttl_seconds: int = 300) -> Optional[Dict]:
    """
    Get a single row from a table with caching
    
    Args:
        table_id: Baserow table ID
        config: Configuration dictionary
        filters: Query filters
        ttl_seconds: Cache TTL in seconds
        
    Returns:
        Row data or None if not found
    """
    # Try to get from cache first
    cached_data = await cache_manager.get_cached_data(table_id, filters)
    if cached_data is not None:
        return cached_data
    
    # Import here to avoid circular imports
    import database.baserow_manager as bm
    
    # Fetch from database
    try:
        data = await bm.query_table(table_id, config, filters)
        
        # Cache the result
        if data is not None:
            await cache_manager.set_cached_data(table_id, data, filters, None, ttl_seconds)
        
        return data
    except Exception as e:
        logger.error(f"Failed to fetch row from table {table_id} with filters {filters}: {e}")
        raise

# Function to periodically clean cache
async def cache_cleanup_task(interval_seconds: int = 60):
    """
    Periodic task to clean up expired cache entries
    
    Args:
        interval_seconds: How often to run cleanup in seconds
    """
    while True:
        try:
            expired_count = cache_manager.clear_expired()
            if expired_count > 0:
                logger.debug(f"Cache cleanup removed {expired_count} expired entries")
            
            # Log cache stats periodically
            stats = cache_manager.get_stats()
            if stats['total_requests'] > 0:
                logger.debug(f"Cache stats: {stats}")
            
            await asyncio.sleep(interval_seconds)
        except Exception as e:
            logger.error(f"Error in cache cleanup task: {e}")
            await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    # Example usage
    async def example_usage():
        # Initialize cache manager
        cache_mgr = DatabaseCacheManager(default_ttl_seconds=60)
        
        # Simulate caching data
        test_data = {"registration": "N12345", "times_seen": 5}
        await cache_mgr.set_cached_data(441094, test_data, {"registration": "N12345"})
        
        # Retrieve cached data
        cached = await cache_mgr.get_cached_data(441094, {"registration": "N12345"})
        print(f"Retrieved from cache: {cached}")
        
        # Check stats
        print(f"Cache stats: {cache_mgr.get_stats()}")
    
    # Run example
    asyncio.run(example_usage())