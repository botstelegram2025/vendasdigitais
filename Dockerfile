# Railway Deployment - Python Base + Node.js (monolito)
FROM python:3.11-slim

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Node 20 + deps de build
RUN apt-get update && apt-get install -y curl build-essential libpq-dev \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip

# Usuário não-root
RUN groupadd --gid 1001 app && useradd --uid 1001 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copia tudo (inclui package.json / requirements.txt se estiverem na raiz)
COPY --chown=app:app . .

# Instala deps Node (tenta ci; se não tiver lock usa install)
RUN set -e; \
    if [ -f package-lock.json ]; then \
      npm ci --omit=dev; \
    else \
      npm install --omit=dev; \
    fi

# Instala deps Python
# (se já copiou requirements.txt acima, não precisa copiar de novo)
RUN pip3 install --no-cache-dir --timeout=300 -r requirements.txt

# Pastas úteis
RUN mkdir -p /app/logs /app/sessions /app/backups && chown -R app:app /app

USER app

# Exponha a porta web PRINCIPAL (Railway roteia só $PORT externamente)
# O Baileys fica interno em 3001, acessado por 127.0.0.1
EXPOSE 5000

# Healthcheck usa a porta do Baileys (interna) só para validar serviço local
# Se seu Baileys expõe /status, use /status; se expuser /health, mantenha /health
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:3001/status || exit 1

# Inicia ambos os serviços
# (script cria variável BAILEYS_API_URL para o bot)
RUN printf '%s\n' \
'#!/bin/bash' \
'set -euo pipefail' \
'echo "🚀 Starting Railway Deployment..."' \
'export BAILEYS_API_URL="http://127.0.0.1:3001"' \
'echo "📱 Starting WhatsApp (Baileys)..."' \
'node whatsapp_baileys_multi.js > /app/logs/baileys.out 2>&1 &' \
'WHATSAPP_PID=$!' \
'' \
'# Aguarda Baileys responder' \
'for i in {1..30}; do' \
'  if curl -fsS http://127.0.0.1:3001/status >/dev/null 2>&1; then' \
'    echo "✅ Baileys is up"; break; fi' \
'  sleep 1' \
'  if ! kill -0 "$WHATSAPP_PID" 2>/dev/null; then' \
'    echo "❌ Baileys crashed at startup"; exit 1; fi' \
'done' \
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
'done' \
> /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]
