"""
Tests for core caching system
"""
import pytest
import time
from unittest.mock import patch
from core.cache import (
    LRUCache, CacheManager, cached, query_cache, 
    session_cache, make_cache_key
)

class TestLRUCache:
    """Test LRU cache implementation"""
    
    def test_basic_operations(self):
        cache = LRUCache(max_size=3)
        
        # Test set and get
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        # Test miss
        assert cache.get("nonexistent") is None
        
        # Test size
        assert cache.size() == 1
    
    def test_lru_eviction(self):
        cache = LRUCache(max_size=2)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
    
    def test_ttl_expiration(self):
        cache = LRUCache(default_ttl=0.1)  # 100ms TTL
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        time.sleep(0.15)  # Wait for expiration
        assert cache.get("key1") is None
    
    def test_access_order_update(self):
        cache = LRUCache(max_size=2)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Access key1 to make it more recently used
        cache.get("key1")
        
        # Add key3, should evict key2 (least recently used)
        cache.set("key3", "value3")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
    
    def test_delete_operation(self):
        cache = LRUCache()
        
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False
    
    def test_clear_operation(self):
        cache = LRUCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        
        assert cache.size() == 0
        assert cache.get("key1") is None
    
    def test_stats(self):
        cache = LRUCache()
        
        # Generate some activity
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['size'] == 1
        assert stats['hit_rate'] == 0.5

class TestCacheManager:
    """Test cache manager"""
    
    def test_get_cache(self):
        manager = CacheManager()
        
        cache1 = manager.get_cache("test_cache", max_size=100)
        cache2 = manager.get_cache("test_cache")  # Should return same instance
        
        assert cache1 is cache2
        assert cache1.max_size == 100
    
    def test_delete_cache(self):
        manager = CacheManager()
        
        manager.get_cache("test_cache")
        assert manager.delete_cache("test_cache") is True
        assert manager.delete_cache("nonexistent") is False
    
    def test_clear_all(self):
        manager = CacheManager()
        
        cache1 = manager.get_cache("cache1")
        cache2 = manager.get_cache("cache2")
        
        cache1.set("key", "value")
        cache2.set("key", "value")
        
        manager.clear_all()
        
        assert cache1.size() == 0
        assert cache2.size() == 0
    
    def test_get_all_stats(self):
        manager = CacheManager()
        
        cache1 = manager.get_cache("cache1")
        cache2 = manager.get_cache("cache2")
        
        cache1.set("key", "value")
        cache2.set("key", "value")
        
        stats = manager.get_all_stats()
        
        assert "cache1" in stats
        assert "cache2" in stats
        assert stats["cache1"]["size"] == 1
        assert stats["cache2"]["size"] == 1

class TestCachedDecorator:
    """Test cached decorator"""
    
    def test_function_caching(self):
        call_count = 0
        
        @cached(cache_name="test", ttl=60)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # First call should execute function
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        
        # Second call should use cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment
        
        # Different argument should execute function
        result3 = expensive_function(6)
        assert result3 == 12
        assert call_count == 2
    
    def test_cache_management_methods(self):
        @cached(cache_name="test")
        def test_function(x):
            return x * 2
        
        # Test function execution
        result = test_function(5)
        assert result == 10
        
        # Test cache stats
        stats = test_function.cache_stats()
        assert stats['size'] == 1
        
        # Test cache clear
        test_function.cache_clear()
        stats = test_function.cache_stats()
        assert stats['size'] == 0

class TestMakeCacheKey:
    """Test cache key generation"""
    
    def test_basic_key_generation(self):
        key1 = make_cache_key("arg1", "arg2", kwarg1="value1")
        key2 = make_cache_key("arg1", "arg2", kwarg1="value1")
        assert key1 == key2  # Same arguments should produce same key
    
    def test_different_args_different_keys(self):
        key1 = make_cache_key("arg1")
        key2 = make_cache_key("arg2")
        assert key1 != key2
    
    def test_kwargs_order_independence(self):
        key1 = make_cache_key(a=1, b=2)
        key2 = make_cache_key(b=2, a=1)
        assert key1 == key2  # Order shouldn't matter

class TestQueryCache:
    """Test query cache functionality"""
    
    def test_user_caching(self):
        user_data = {"id": 1, "name": "Test User"}
        
        # Set and get user
        query_cache.set_user(1, user_data)
        result = query_cache.get_user(1)
        
        assert result == user_data
    
    def test_user_invalidation(self):
        user_data = {"id": 1, "name": "Test User"}
        
        query_cache.set_user(1, user_data)
        query_cache.invalidate_user(1)
        
        assert query_cache.get_user(1) is None
    
    def test_client_caching(self):
        client_data = {"id": 1, "name": "Test Client"}
        
        query_cache.set_client(1, client_data)
        result = query_cache.get_client(1)
        
        assert result == client_data
    
    def test_clients_for_user_caching(self):
        clients_data = [{"id": 1}, {"id": 2}]
        
        query_cache.set_clients_for_user(1, clients_data)
        result = query_cache.get_clients_for_user(1)
        
        assert result == clients_data

class TestSessionCache:
    """Test session cache functionality"""
    
    def test_session_operations(self):
        session_data = {"state": "waiting_input", "step": 1}
        
        # Set and get session
        session_cache.set_session(1, session_data)
        result = session_cache.get_session(1)
        
        assert result == session_data
    
    def test_session_update(self):
        initial_data = {"state": "waiting_input", "step": 1}
        session_cache.set_session(1, initial_data)
        
        # Update session
        session_cache.update_session(1, step=2, new_field="value")
        
        result = session_cache.get_session(1)
        assert result["step"] == 2
        assert result["new_field"] == "value"
        assert result["state"] == "waiting_input"  # Original field preserved
    
    def test_session_clear(self):
        session_cache.set_session(1, {"data": "value"})
        session_cache.clear_session(1)
        
        assert session_cache.get_session(1) is None