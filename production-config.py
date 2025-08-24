"""
Production Configuration for Railway Deployment
Optimizations for performance, security and reliability
"""

import os
import logging
from pathlib import Path

# Production Environment Settings
PRODUCTION_CONFIG = {
    # Logging Configuration
    'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
    'LOG_FORMAT': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'LOG_MAX_BYTES': 10 * 1024 * 1024,  # 10MB
    'LOG_BACKUP_COUNT': 5,
    
    # Database Configuration
    'DB_POOL_SIZE': int(os.getenv('DB_POOL_SIZE', '10')),
    'DB_MAX_OVERFLOW': int(os.getenv('DB_MAX_OVERFLOW', '20')),
    'DB_POOL_TIMEOUT': int(os.getenv('DB_POOL_TIMEOUT', '30')),
    'DB_POOL_RECYCLE': int(os.getenv('DB_POOL_RECYCLE', '3600')),
    
    # Telegram Bot Configuration
    'TELEGRAM_TIMEOUT': int(os.getenv('TELEGRAM_TIMEOUT', '30')),
    'TELEGRAM_POOL_TIMEOUT': int(os.getenv('TELEGRAM_POOL_TIMEOUT', '1')),
    'TELEGRAM_READ_TIMEOUT': int(os.getenv('TELEGRAM_READ_TIMEOUT', '30')),
    'TELEGRAM_WRITE_TIMEOUT': int(os.getenv('TELEGRAM_WRITE_TIMEOUT', '30')),
    
    # WhatsApp Configuration
    'WHATSAPP_TIMEOUT': int(os.getenv('WHATSAPP_TIMEOUT', '60')),
    'WHATSAPP_RETRY_ATTEMPTS': int(os.getenv('WHATSAPP_RETRY_ATTEMPTS', '3')),
    'WHATSAPP_RETRY_DELAY': int(os.getenv('WHATSAPP_RETRY_DELAY', '5')),
    
    # Session Management
    'SESSION_CLEANUP_INTERVAL': int(os.getenv('SESSION_CLEANUP_INTERVAL', '3600')),  # 1 hour
    'SESSION_MAX_AGE': int(os.getenv('SESSION_MAX_AGE', '2592000')),  # 30 days
    
    # Performance Settings
    'MAX_CONCURRENT_CONNECTIONS': int(os.getenv('MAX_CONCURRENT_CONNECTIONS', '2')),
    'SCHEDULER_INTERVAL': int(os.getenv('SCHEDULER_INTERVAL', '60')),  # 1 minute
    'PAYMENT_CHECK_INTERVAL': int(os.getenv('PAYMENT_CHECK_INTERVAL', '120')),  # 2 minutes
    
    # Security Settings
    'RATE_LIMIT_PER_MINUTE': int(os.getenv('RATE_LIMIT_PER_MINUTE', '20')),
    'MAX_MESSAGE_LENGTH': int(os.getenv('MAX_MESSAGE_LENGTH', '4096')),
    'ALLOWED_EXTENSIONS': ['jpg', 'jpeg', 'png', 'gif', 'pdf'],
    
    # File Storage
    'UPLOAD_FOLDER': os.getenv('UPLOAD_FOLDER', '/tmp/uploads'),
    'MAX_CONTENT_LENGTH': int(os.getenv('MAX_CONTENT_LENGTH', '16777216')),  # 16MB
}

def setup_production_logging():
    """Configure production logging"""
    log_dir = Path('./logs')
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, PRODUCTION_CONFIG['LOG_LEVEL']),
        format=PRODUCTION_CONFIG['LOG_FORMAT'],
        handlers=[
            logging.FileHandler('./logs/production.log'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce noise from external libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)

def get_database_config():
    """Get optimized database configuration"""
    return {
        'pool_size': PRODUCTION_CONFIG['DB_POOL_SIZE'],
        'max_overflow': PRODUCTION_CONFIG['DB_MAX_OVERFLOW'],
        'pool_timeout': PRODUCTION_CONFIG['DB_POOL_TIMEOUT'],
        'pool_recycle': PRODUCTION_CONFIG['DB_POOL_RECYCLE'],
        'pool_pre_ping': True,
        'echo': False  # Disable SQL logging in production
    }

def get_telegram_config():
    """Get optimized Telegram bot configuration"""
    return {
        'request_kwargs': {
            'read_timeout': PRODUCTION_CONFIG['TELEGRAM_READ_TIMEOUT'],
            'write_timeout': PRODUCTION_CONFIG['TELEGRAM_WRITE_TIMEOUT'],
            'connect_timeout': PRODUCTION_CONFIG['TELEGRAM_TIMEOUT'],
            'pool_timeout': PRODUCTION_CONFIG['TELEGRAM_POOL_TIMEOUT'],
        }
    }

def is_production():
    """Check if running in production environment"""
    return os.getenv('NODE_ENV') == 'production' or os.getenv('RAILWAY_ENVIRONMENT') == 'production'

def ensure_directories():
    """Ensure required directories exist"""
    dirs = ['./logs', './sessions', './tmp', './uploads']
    for dir_path in dirs:
        Path(dir_path).mkdir(exist_ok=True)

# Initialize production settings
if is_production():
    setup_production_logging()
    ensure_directories()
    print("🚀 Production configuration loaded")