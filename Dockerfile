# Node + Python em Alpine
FROM node:20-alpine

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Python + pip + utilitários (sem compilar nada)
RUN apk add --no-cache python3 py3-pip curl ca-certificates \
 && python3 -m pip install --upgrade pip

# Usuário sem privilégios
RUN addgroup -g 1001 app && adduser -D -u 1001 -G app app
WORKDIR /app

# Instalar deps Node (ajuste se seu package.json estiver em subpasta)
COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts

# Instalar deps Python (sua lista corrigida)
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --timeout=300 -r requirements.txt

# Copiar o resto
COPY . .
RUN mkdir -p /app/logs /app/sessions /app/backups \
 && chown -R app:app /app
USER app

EXPOSE 5000 3001

# healthcheck (ajuste a rota)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget -qO- http://localhost:3001/health >/dev/null || exit 1

# start dos dois processos (ajuste nomes/paths)
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo 'echo "📱 start whatsapp..."' >> /app/start.sh && \
    echo 'node whatsapp_baileys_multi.js & WHATSAPP_PID=$!' >> /app/start.sh && \
    echo 'sleep 2' >> /app/start.sh && \
    echo 'echo "🤖 start bot..."' >> /app/start.sh && \
    echo 'python3 main.py & BOT_PID=$!' >> /app/start.sh && \
    echo 'trap "kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true; wait; exit 0" TERM INT' >> /app/start.sh && \
    echo 'wait $BOT_PID $WHATSAPP_PID' >> /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]
