# Ultra-Simple Dockerfile for Railway Deployment (Node + Python)
FROM node:20

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Instale apenas o necessário (sem compilar C)
# -> se seu requirements.txt usa psycopg2-binary, NÃO precisa de libpq-dev/build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install --upgrade pip

# Usuário sem privilégios
RUN groupadd --gid 1001 app && useradd --uid 1001 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# 1) Instale deps Node (ajuste se seu package.json estiver em subpasta)
# Se o seu package.json está na RAIZ:
COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts

# 2) Instale deps Python primeiro para aproveitar cache
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --timeout=300 -r requirements.txt

# 3) Copie o resto do código
COPY . .

# Pastas úteis e permissões
RUN mkdir -p /app/logs /app/sessions /app/backups \
 && chown -R app:app /app

USER app

# Ports (ajuste se seu WhatsApp expõe 3001 e seu Flask/HTTP expõe 5000)
EXPOSE 5000 3001

# Healthcheck do serviço Node (ajuste a rota/porta)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:3001/health || exit 1

# Script de startup dos dois processos
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo 'echo "🚀 Starting Railway Deployment..."' >> /app/start.sh && \
    echo 'echo "📱 Starting WhatsApp service..."' >> /app/start.sh && \
    echo 'node whatsapp_baileys_multi.js &  # ajuste se seu arquivo for outro ou estiver em subpasta' >> /app/start.sh && \
    echo 'WHATSAPP_PID=$!' >> /app/start.sh && \
    echo 'sleep 2' >> /app/start.sh && \
    echo 'echo "🤖 Starting Telegram bot...""' >> /app/start.sh && \
    echo 'python3 -m gunicorn -b 0.0.0.0:5000 start
