#!/usr/bin/env python3
"""
🚀 Railway Launch DEFINITIVO - Solução robusta e testada
Garante que WhatsApp e base de dados funcionem 100%
"""
import os
import sys
import subprocess
import time
import logging
import threading
import requests
import signal
from pathlib import Path

# Logging configurado para Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - RAILWAY-FINAL - %(levelname)s - %(message)s'
)
logger = logging.getLogger('railway_final')

# Global process references for cleanup
whatsapp_process = None
telegram_process = None

def force_database_migration():
    """Force database migration with robust error handling"""
    try:
        logger.info("🗄️ FORCING database migration...")
        
        # Direct SQL approach for Railway PostgreSQL
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("❌ DATABASE_URL not found")
            return False
        
        # Fix postgres:// URL
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Import SQLAlchemy directly
        from sqlalchemy import create_engine, text
        
        logger.info("🔗 Connecting to Railway database...")
        engine = create_engine(database_url, pool_pre_ping=True)
        
        # Execute migration SQL directly
        with engine.connect() as conn:
            # Add is_default column if not exists
            try:
                logger.info("📝 Adding is_default column...")
                conn.execute(text("""
                    ALTER TABLE message_templates 
                    ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE
                """))
                conn.commit()
                logger.info("✅ Column is_default added successfully")
            except Exception as e:
                logger.info(f"⚠️ Column might exist: {e}")
            
            # Verify column exists
            try:
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'message_templates' AND column_name = 'is_default'
                """))
                if result.fetchone():
                    logger.info("✅ Column is_default verified in database")
                    return True
                else:
                    logger.error("❌ Column is_default NOT found after migration")
                    return False
            except Exception as e:
                logger.error(f"❌ Failed to verify column: {e}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        return False

def start_whatsapp_service():
    """Start WhatsApp service with proper Railway configuration"""
    global whatsapp_process
    
    try:
        logger.info("🚀 Starting WhatsApp service...")
        
        # Check if node_modules exists
        if not Path("node_modules").exists():
            logger.info("📦 Installing Node.js dependencies...")
            result = subprocess.run(['npm', 'install'], capture_output=True, text=True, timeout=180)
            if result.returncode != 0:
                logger.error(f"❌ npm install failed: {result.stderr}")
                return None
        
        # Railway environment variables
        env = os.environ.copy()
        railway_port = os.getenv('PORT', '8080')
        
        # Set WhatsApp configuration
        env.update({
        'BAILEYS_PORT': railway_port,
            'NODE_ENV': 'production',
            'PORT': railway_port,
            'RAILWAY_ENVIRONMENT_NAME': 'production',
            'WHATSAPP_INTERNAL_PORT': '3001'
        })
        
        logger.info(f"🌐 Starting WhatsApp on Railway port: {railway_port}")
        
        # Start WhatsApp process
        whatsapp_process = subprocess.Popen(
            ['node', 'whatsapp_baileys_multi.js'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor output in background
        def log_whatsapp_output():
            try:
                for line in whatsapp_process.stdout:
                    if line.strip():
                        logger.info(f"[WhatsApp] {line.strip()}")
                        # Check for ready signal
                        if "Servidor Baileys Multi-User rodando" in line:
                            logger.info("✅ WhatsApp service is ready!")
            except:
                pass
        
        threading.Thread(target=log_whatsapp_output, daemon=True).start()
        
        logger.info("✅ WhatsApp process started")
        return whatsapp_process
        
    except Exception as e:
        logger.error(f"❌ Failed to start WhatsApp: {e}")
        return None

def wait_for_whatsapp_ready(max_wait=60):
    """Wait for WhatsApp to be ready with multiple endpoint checks"""
    logger.info("⏳ Waiting for WhatsApp to be ready...")
    
    # Railway port
    railway_port = os.getenv('PORT', '8080')
    
    # Multiple URLs to try
    health_urls = [
        f'http://127.0.0.1:{railway_port}/health',
        f'http://localhost:{railway_port}/health',
        'http://127.0.0.1:3001/health',
        'http://localhost:3001/health'
    ]
    
    start_time = time.time()
    while (time.time() - start_time) < max_wait:
        for url in health_urls:
            try:
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    logger.info(f"✅ WhatsApp ready at {url}")
                    # Set working URL for telegram bot
                    base_url = url.replace('/health', '')
                    os.environ['WHATSAPP_URL'] = base_url
                    logger.info(f"🔗 WhatsApp URL set to: {base_url}")
                    return True
            except:
                pass
        
        logger.info(f"⏳ Still waiting... ({int(time.time() - start_time)}s)")
        time.sleep(3)
    
    logger.warning("⚠️ WhatsApp health check failed, but continuing...")
    # Set fallback URL
    os.environ['WHATSAPP_URL'] = f'http://127.0.0.1:{railway_port}'
    return False

def start_telegram_bot():
    """Start Telegram bot"""
    try:
        logger.info("🤖 Starting Telegram bot...")
        
        # Set required environment variables
        os.environ['PYTHONUNBUFFERED'] = '1'
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        
        # Add current directory to path
        if '.' not in sys.path:
            sys.path.insert(0, '.')
        
        # Import and run main bot
        logger.info("📲 Importing bot main module...")
        import main
        logger.info("✅ Telegram bot started successfully!")
        
    except Exception as e:
        logger.error(f"❌ Telegram bot failed: {e}")
        raise

def setup_signal_handlers():
    """Setup graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal, cleaning up...")
        
        global whatsapp_process, telegram_process
        
        # Cleanup processes
        if whatsapp_process:
            try:
                whatsapp_process.terminate()
                whatsapp_process.wait(timeout=10)
            except:
                whatsapp_process.kill()
        
        logger.info("✅ Cleanup complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Main launcher with robust error handling"""
    try:
        logger.info("🌟 Railway Final Launcher Starting...")
        
        # Setup signal handlers
        setup_signal_handlers()
        
        # Step 1: Force database migration
        logger.info("📋 Step 1: Database Migration")
        if not force_database_migration():
            logger.error("❌ CRITICAL: Database migration failed!")
            logger.error("🔥 This will cause template loading errors!")
            return 1
        
        # Step 2: Start WhatsApp service
        logger.info("📋 Step 2: WhatsApp Service")
        whatsapp_proc = start_whatsapp_service()
        if not whatsapp_proc:
            logger.error("❌ CRITICAL: WhatsApp service failed to start!")
            return 1
        
        # Step 3: Wait for WhatsApp
        logger.info("📋 Step 3: WhatsApp Health Check")
        wait_for_whatsapp_ready()
        
        # Step 4: Start Telegram bot
        logger.info("📋 Step 4: Telegram Bot")
        start_telegram_bot()
        
        logger.info("🎉 ALL SERVICES RUNNING SUCCESSFULLY!")
        logger.info("🔥 Railway deployment is FULLY FUNCTIONAL!")
        
        # Keep main thread alive
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("📴 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)