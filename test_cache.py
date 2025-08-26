#!/usr/bin/env python3
"""
Test script for the database caching system
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).parent))

from database.cache_manager import DatabaseCacheManager, CacheEntry
from config import config_manager

async def test_cache_manager():
    """Test the cache manager functionality"""
    print("Testing Database Cache Manager...")
    
    # Create cache manager
    cache_mgr = DatabaseCacheManager(default_ttl_seconds=5)  # Short TTL for testing
    
    # Test data
    test_data = {"registration": "N12345", "times_seen": 5, "last_seen": "2023-01-01"}
    
    # Test setting cache
    print("1. Testing cache set...")
    result = await cache_mgr.set_cached_data(441094, test_data, {"registration": "N12345"})
    print(f"   Set result: {result}")
    
    # Test getting cache
    print("2. Testing cache get...")
    cached_data = await cache_mgr.get_cached_data(441094, {"registration": "N12345"})
    print(f"   Retrieved data: {cached_data}")
    
    # Test cache hit statistics
    print("3. Testing cache statistics...")
    stats = cache_mgr.get_stats()
    print(f"   Stats: {stats}")
    
    # Test cache expiration
    print("4. Testing cache expiration...")
    await asyncio.sleep(6)  # Wait for cache to expire
    expired_data = await cache_mgr.get_cached_data(441094, {"registration": "N12345"})
    print(f"   Expired data: {expired_data}")
    
    # Test stats after expiration
    stats = cache_mgr.get_stats()
    print(f"   Stats after expiration: {stats}")
    
    print("Cache manager test completed!")

async def test_cache_with_config():
    """Test cache with actual configuration"""
    print("\nTesting cache with configuration...")
    
    # Load config
    config = config_manager.load_config()
    print(f"   Loaded config with baserow tables: {config.get('baserow', {}).get('tables', {})}")
    
    print("Configuration test completed!")

if __name__ == "__main__":
    asyncio.run(test_cache_manager())
    asyncio.run(test_cache_with_config())