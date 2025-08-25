# Railway Deployment - Python Base + Node.js (monolito)
FROM python:3.11-slim

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Node 20 + deps de build (inclui git para deps npm via Git)
RUN apt-get update && apt-get install -y \
    curl git build-essential libpq-dev \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip

# Usuário não-root
RUN groupadd --gid 1001 app && useradd --uid 1001 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copia tudo (inclui package.json / requirements.txt se estiverem na raiz)
COPY --chown=app:app . .

# Instala deps Node (só se existir package.json)
# - evita falha quando não há manifest
# - desliga audit/fund/progress e scripts para builds mais previsíveis
RUN set -e; \
  npm config set fund false; \
  npm config set audit false; \
  npm config set progress false; \
  npm config set prefer-online false; \
  if [ -f package.json ]; then \
    if [ -f package-lock.json ]; then \
      npm ci --omit=dev --no-audit --no-fund --ignore-scripts; \
    else \
      npm install --omit=dev --no-audit --no-fund --ignore-scripts; \
    fi; \
  else \
    echo "⚠️  package.json não encontrado; pulando instalação de pacotes Node"; \
  fi

# Instala deps Python (se requirements.txt existir)
RUN if [ -f requirements.txt ]; then \
      pip3 install --no-cache-dir --timeout=300 -r requirements.txt; \
    else \
      echo "⚠️  requirements.txt não encontrado; pulando pip install"; \
    fi

# Pastas úteis
RUN mkdir -p /app/logs /app/sessions /app/backups && chown -R app:app /app

USER app

# Expose (Baileys interno 3001; bot opcional 5000)
EXPOSE 3001 5000

# Health check do Baileys
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:3001/status || exit 1

# Script de startup: sobe Baileys em 3001, espera /status, depois o bot
RUN printf '%s\n' '#!/bin/bash' \
  'set -euo pipefail' \
  'echo "🚀 Starting Railway Deployment (monolito)..."' \
  '' \
  '# Config Baileys interno' \
  'export BAILEYS_PORT=3001' \
  'export RAILWAY_ENVIRONMENT_NAME=${RAILWAY_ENVIRONMENT_NAME:-production}' \
  '' \
  'echo "📱 Starting WhatsApp (Baileys) on :3001..."' \
  'node whatsapp_baileys_multi.js > /app/logs/baileys.out 2>&1 &' \
  'WHATSAPP_PID=$!' \
  '' \
  '# Aguarda Baileys responder' \
  'for i in {1..40}; do' \
  '  if curl -fsS http://127.0.0.1:3001/status >/dev/null 2>&1; then' \
  '    echo "✅ Baileys is up"; break; fi' \
  '  sleep 1' \
  '  if ! kill -0 "$WHATSAPP_PID" 2>/dev/null; then' \
  '    echo "❌ Baileys crashed at startup"; tail -n +1 /app/logs/baileys.out || true; exit 1; fi' \
  'done' \
  '' \
  '# URL interna para o bot Python' \
  'WHATSAPP_URL="http://127.0.0.1:$PORT"' \
  'BAILEYS_API_URL="$WHATSAPP_URL"' \
  'echo "[BOOT] WHATSAPP_URL=$WHATSAPP_URL"' \
  '' \
  'echo "🤖 Starting Telegram bot..."' \
  'if [ -z "${PORT:-}" ]; then export PORT=5000; fi' \
  'python3 main.py > /app/logs/bot.out 2>&1 &' \
  'BOT_PID=$!' \
  '' \
  'cleanup() {' \
  '  echo "🛑 Shutting down...";' \
  '  kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true;' \
  '  wait || true; exit 0;' \
  '}' \
  'trap cleanup SIGTERM SIGINT' \
  '' \
  '# Se um dos dois morrer, encerra o container (para reiniciar limpo)' \
  'while true; do' \
  '  if ! kill -0 "$BOT_PID" 2>/dev/null; then echo "❌ Bot died"; exit 1; fi' \
  '  if ! kill -0 "$WHATSAPP_PID" 2>/dev/null; then echo "❌ Baileys died"; exit 1; fi' \
  '  sleep 3;' \
  'done' > /app/start.sh \
 && chmod +x /app/start.sh

CMD ["/app/start.sh"]
