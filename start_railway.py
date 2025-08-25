#!/usr/bin/env python3
"""
Railway Start Script - Telegram Bot + WhatsApp Multi-User
Optimized for production deployment
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

# Environment setup
os.environ.setdefault('PYTHONPATH', '/app')
os.environ.setdefault('NODE_ENV', 'production')

def start_whatsapp_service():
    """Start WhatsApp Baileys Multi-User service"""
    try:
        print("🚀 Starting WhatsApp Baileys Multi-User service...")
        
        # Ensure sessions directory exists
        sessions_dir = Path('./sessions')
        sessions_dir.mkdir(exist_ok=True)
        
        # Start WhatsApp service
        process = subprocess.Popen(
            ['node', 'whatsapp_baileys_multi.js'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Forward output
        for line in iter(process.stdout.readline, ''):
            print(f"[WhatsApp] {line.strip()}")
            
        return process
        
    except Exception as e:
        print(f"❌ Error starting WhatsApp service: {e}")
        return None

def start_telegram_bot():
    """Start Telegram Bot service"""
    try:
        print("🤖 Starting Telegram Bot service...")
        
        # Import and run the bot
        import main
        
    except Exception as e:
        print(f"❌ Error starting Telegram Bot: {e}")
        sys.exit(1)

def signal_handler(signum, frame):
    """Handle graceful shutdown"""
    print("🛑 Received shutdown signal, cleaning up...")
    sys.exit(0)

def main():
    """Main entry point for Railway deployment"""
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 Starting Railway Deployment - Telegram Bot + WhatsApp")
    print("=" * 60)
    
    # Check required environment variables
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'DATABASE_URL',
        'MERCADO_PAGO_ACCESS_TOKEN'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    # Start WhatsApp service in background thread
    whatsapp_thread = threading.Thread(target=start_whatsapp_service, daemon=True)
    whatsapp_thread.start()
    
    # Give WhatsApp service time to start
    time.sleep(3)
    
    # Start Telegram bot (main process)
    start_telegram_bot()

if __name__ == "__main__":
    main()
