#!/bin/bash
set -euo pipefail

echo "🚀 Starting Railway Deployment (monolito)..."

# Configuração Baileys
export BAILEYS_PORT=3001
export RAILWAY_ENVIRONMENT_NAME=${RAILWAY_ENVIRONMENT_NAME:-production}

echo "📱 Starting WhatsApp (Baileys) on :$BAILEYS_PORT..."
node whatsapp_baileys_multi.js > /app/logs/baileys.out 2>&1 &
WHATSAPP_PID=$!

# Aguarda Baileys responder
for i in {1..40}; do
  if curl -fsS http://127.0.0.1:$BAILEYS_PORT/status >/dev/null 2>&1; then
    echo "✅ Baileys is up"
    break
  fi
  sleep 1
  if ! kill -0 "$WHATSAPP_PID" 2>/dev/null; then
    echo "❌ Baileys crashed at startup"
    tail -n +1 /app/logs/baileys.out || true
    exit 1
  fi
done

# URL fixa do Baileys para o serviço Python
export WHATSAPP_URL="http://127.0.0.1:$BAILEYS_PORT"
export BAILEYS_API_URL="$WHATSAPP_URL"
echo "[BOOT] WHATSAPP_URL=$WHATSAPP_URL"

# Inicia o bot Telegram
echo "🤖 Starting Telegram bot..."
if [ -z "${PORT:-}" ]; then export PORT=5000; fi
python3 main.py > /app/logs/bot.out 2>&1 &
BOT_PID=$!

cleanup() {
  echo "🛑 Shutting down..."
  kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true
  wait || true
  exit 0
}
trap cleanup SIGTERM SIGINT

# Se um dos dois morrer → encerra o container
while true; do
  if ! kill -0 "$BOT_PID" 2>/dev/null; then
    echo "❌ Bot died"
    exit 1
  fi
  if ! kill -0 "$WHATSAPP_PID" 2>/dev/null; then
    echo "❌ Baileys died"
    exit 1
  fi
  sleep 3
done
