# Railway Deployment - Python Base + Node.js
FROM python:3.11-slim

# Set environment variables
ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Node.js 20 and essential tools
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip

# Create app user for security
RUN groupadd --gid 1001 app && \
    useradd --uid 1001 --gid app --shell /bin/bash --create-home app

# Set working directory
WORKDIR /app

# Copy all files
COPY --chown=app:app . .

# Install Node.js dependencies
RUN npm ci --only=production --ignore-scripts

# Install Python dependencies with better error handling
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --timeout=300 -r requirements.txt

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
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo 'echo "🚀 Starting Railway Deployment..."' >> /app/start.sh && \
    echo 'echo "📱 Starting WhatsApp service..."' >> /app/start.sh && \
    echo 'node whatsapp_baileys_multi.js &' >> /app/start.sh && \
    echo 'WHATSAPP_PID=$!' >> /app/start.sh && \
    echo 'sleep 3' >> /app/start.sh && \
    echo 'echo "🤖 Starting Telegram bot..."' >> /app/start.sh && \
    echo 'python3 main.py &' >> /app/start.sh && \
    echo 'BOT_PID=$!' >> /app/start.sh && \
    echo 'cleanup() {' >> /app/start.sh && \
    echo '    echo "🛑 Shutting down..."' >> /app/start.sh && \
    echo '    kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true' >> /app/start.sh && \
    echo '    wait' >> /app/start.sh && \
    echo '    exit 0' >> /app/start.sh && \
    echo '}' >> /app/start.sh && \
    echo 'trap cleanup SIGTERM SIGINT' >> /app/start.sh && \
    echo 'wait $BOT_PID $WHATSAPP_PID' >> /app/start.sh && \
    chmod +x /app/start.sh

# Start services
CMD ["/app/start.sh"]