"""
Test Configuration and Fixtures
Provides shared test configuration and fixtures
"""
import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test configuration
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def temp_file():
    """Create temporary file for testing"""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        yield tf.name
    os.unlink(tf.name)

@pytest.fixture
def mock_telegram_update():
    """Mock Telegram update object"""
    update = Mock()
    update.effective_user = Mock()
    update.effective_user.id = 12345
    update.effective_user.first_name = "Test User"
    update.effective_chat = Mock()
    update.effective_chat.id = 12345
    update.message = Mock()
    update.message.text = "Test message"
    return update

@pytest.fixture
def mock_telegram_context():
    """Mock Telegram context object"""
    context = Mock()
    context.user_data = {}
    context.chat_data = {}
    context.bot_data = {}
    return context

@pytest.fixture
def test_database():
    """Create test database"""
    engine = create_engine(TEST_DATABASE_URL)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Import and create tables
    from models import Base
    Base.metadata.create_all(bind=engine)
    
    yield TestingSessionLocal
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        'telegram_id': 12345,
        'phone_number': '5511999999999',
        'first_name': 'Test User',
        'is_active': True,
        'trial_start': None,
        'subscription_end': None
    }

@pytest.fixture
def sample_client_data():
    """Sample client data for testing"""
    return {
        'name': 'Test Client',
        'phone_number': '5511888888888',
        'plan_name': 'Premium',
        'plan_price': 50.0,
        'server_info': 'Test Server',
        'due_date': '2025-01-01',
        'other_info': 'Test info',
        'auto_reminders_enabled': True
    }

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
def reset_caches():
    """Reset all caches before each test"""
    from core.cache import cache_manager, query_cache, session_cache
    cache_manager.clear_all()
    query_cache.cache.clear()
    session_cache.cache.clear()

@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset monitoring metrics before each test"""
    from core.monitoring import monitoring
    monitoring.metrics._metrics.clear()
    monitoring.metrics._counters.clear()
    monitoring.metrics._gauges.clear()
    monitoring.metrics._histograms.clear()

@pytest.fixture
def mock_whatsapp_service():
    """Mock WhatsApp service"""
    service = Mock()
    service.send_message = AsyncMock(return_value=True)
    service.connect_user = AsyncMock(return_value=True)
    service.disconnect_user = AsyncMock(return_value=True)
    service.get_connection_status = Mock(return_value={'connected': True})
    return service