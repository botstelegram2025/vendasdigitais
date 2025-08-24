# 🚂 Railway Deployment Guide

## 📋 Pre-Deployment Checklist

### 1. Environment Variables Required
Set these in Railway dashboard under Variables:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
MERCADO_PAGO_ACCESS_TOKEN=your_mercado_pago_access_token  
MERCADO_PAGO_PUBLIC_KEY=your_mercado_pago_public_key
```

### 2. Database Setup
Railway will automatically provision PostgreSQL and set `DATABASE_URL`

## 🚀 Deployment Steps

### Option 1: GitHub Integration (Recommended)
1. Push code to GitHub repository
2. Connect repository to Railway
3. Set environment variables
4. Deploy automatically

### Option 2: CLI Deployment
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project
railway init

# Set environment variables
railway variables set TELEGRAM_BOT_TOKEN=your_token

# Deploy
railway up
```

## 🔧 Railway Configuration

### Services Configuration
The project runs two services:
- **Bot Service**: `python main.py` (Primary)
- **WhatsApp Service**: `node whatsapp_baileys_multi.js`

### Resource Requirements
- **Memory**: 512MB minimum (1GB recommended)
- **CPU**: 0.25 vCPU minimum
- **Storage**: 1GB for sessions and logs

## 📊 Monitoring

### Health Checks
- Bot status: Monitor Telegram API calls
- WhatsApp: Check `/health` endpoint on port 3001
- Database: Monitor connection pool

### Logs Access
```bash
railway logs --tail
```

## 🔒 Security Notes

1. **Never commit secrets** - Use Railway environment variables
2. **Sessions storage** - Automatically handled in `./sessions/`
3. **Database security** - Railway provides secure PostgreSQL
4. **SSL/TLS** - Automatically provided by Railway

## 💰 Cost Estimation

### Monthly Costs (Approximate)
- **Starter Usage**: $5-10 USD
- **Medium Usage**: $15-25 USD  
- **Heavy Usage**: $30-50 USD

### Optimization Tips
- Monitor usage in Railway dashboard
- Use sleep settings if applicable
- Optimize database queries
- Clean up old session files

## 🛠️ Troubleshooting

### Common Issues
1. **Bot not responding**: Check TELEGRAM_BOT_TOKEN
2. **Database errors**: Verify DATABASE_URL
3. **WhatsApp connection**: Check sessions persistence
4. **Memory issues**: Increase service resources

### Support Resources
- Railway Discord: https://discord.gg/railway
- Documentation: https://docs.railway.app
- Status Page: https://status.railway.app

## 📝 Post-Deployment

### Verification Steps
1. Test bot commands in Telegram
2. Check WhatsApp connectivity  
3. Verify payment processing
4. Monitor logs for errors
5. Test scheduled reminders

### Maintenance
- Monitor resource usage monthly
- Update dependencies quarterly
- Backup important sessions
- Check log files regularly