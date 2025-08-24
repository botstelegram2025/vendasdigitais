# Multi-stage Dockerfile for Professional Client Management Bot
FROM node:18-alpine AS whatsapp-service

# Install Node.js dependencies for WhatsApp service
WORKDIR /app/whatsapp
COPY package*.json ./
RUN npm ci --only=production

# Copy WhatsApp service files
COPY whatsapp_baileys_multi.js ./
COPY sessions/ ./sessions/

# Main Python application stage
FROM python:3.11-slim AS main

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN groupadd --gid 1001 app && \
    useradd --uid 1001 --gid app --shell /bin/bash --create-home app

# Set working directory
WORKDIR /app

# Copy Python requirements and install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY --chown=app:app . .

# Copy WhatsApp service from previous stage
COPY --from=whatsapp-service --chown=app:app /app/whatsapp ./whatsapp/

# Install Node.js for WhatsApp service
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# Create necessary directories
RUN mkdir -p /app/logs /app/sessions /app/backups && \
    chown -R app:app /app

# Switch to app user
USER app

# Expose ports
EXPOSE 5000 3001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

# Create startup script
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 Starting Client Management Bot..."

# Start WhatsApp service in background
echo "📱 Starting WhatsApp service..."
cd /app/whatsapp && node whatsapp_baileys_multi.js &
WHATSAPP_PID=$!

# Wait for WhatsApp service to be ready
echo "⏳ Waiting for WhatsApp service..."
for i in {1..30}; do
    if curl -s http://localhost:3001/health > /dev/null; then
        echo "✅ WhatsApp service is ready"
        break
    fi
    echo "Waiting for WhatsApp service... ($i/30)"
    sleep 2
done

# Start main bot application
echo "🤖 Starting Telegram bot..."
cd /app && python3 main.py &
BOT_PID=$!

# Function to handle shutdown
cleanup() {
    echo "🛑 Shutting down services..."
    kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true
    wait
    echo "✅ Shutdown complete"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Wait for either process to exit
wait $BOT_PID $WHATSAPP_PID
EOF

RUN chmod +x /app/start.sh

# Start services
CMD ["/app/start.sh"]

# Labels for metadata
LABEL maintainer="Development Team <dev@example.com>" \
      version="1.0.0" \
      description="Professional Telegram bot for client management with WhatsApp integration" \
      org.opencontainers.image.title="Client Management Bot" \
      org.opencontainers.image.description="Professional client management solution with Telegram and WhatsApp integration" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="Your Company" \
      org.opencontainers.image.licenses="MIT"
