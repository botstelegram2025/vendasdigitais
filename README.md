# 🤖 Telegram Bot - Client Management & WhatsApp Integration

## 🚀 Railway Deployment Package

Complete Telegram bot system for client management with WhatsApp messaging, subscription system with PIX payments via Mercado Pago, and automated scheduling.

### ✨ Features

- **👥 Client Management**: Complete CRUD operations
- **📱 WhatsApp Integration**: Automated messaging via Baileys API  
- **💰 Payment System**: PIX payments via Mercado Pago
- **📊 Dashboard**: Financial overview and statistics
- **⏰ Automated Reminders**: Scheduled client notifications
- **📝 Template System**: Customizable message templates
- **🔐 User Isolation**: Multi-user system with individual sessions

### 🛠️ Tech Stack

- **Backend**: Python 3.11+ with Flask
- **Bot Framework**: python-telegram-bot
- **Database**: PostgreSQL (Railway managed)
- **WhatsApp**: Node.js + Baileys library
- **Payments**: Mercado Pago API
- **Scheduling**: APScheduler
- **Deployment**: Railway Platform

### 📋 Environment Variables

Required for Railway deployment:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
MERCADO_PAGO_ACCESS_TOKEN=your_mercado_pago_access_token
MERCADO_PAGO_PUBLIC_KEY=your_mercado_pago_public_key
```

DATABASE_URL is automatically provided by Railway.

### 🚀 Quick Deploy

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial Railway deployment"
   git remote add origin your-repo-url
   git push -u origin main
   ```

2. **Connect to Railway**:
   - Link GitHub repository
   - Set environment variables
   - Deploy automatically

3. **Configure Services**:
   - Main service runs both Python bot and Node.js WhatsApp server
   - Railway automatically provisions PostgreSQL database
   - SSL/TLS handled automatically

### 📊 Cost Estimation

- **Starter**: ~$5-10 USD/month
- **Production**: ~$15-30 USD/month
- **High Usage**: ~$30-50 USD/month

### 🔧 Monitoring & Logs

```bash
# View logs
railway logs --tail

# Check service status
railway status
```

### 📖 Documentation

See `deploy-guide.md` for complete deployment instructions and troubleshooting.

### 🆘 Support

- Railway Discord: https://discord.gg/railway
- Documentation: https://docs.railway.app

---

**Ready for production deployment on Railway! 🚂**