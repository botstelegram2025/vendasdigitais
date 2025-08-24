# Base com Python pronto
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_ENV=production

WORKDIR /app

# 1) Instala Node 20 via NodeSource (estável no Railway)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
 && apt-get update && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --upgrade pip

# 2) Dependências Python (sem compilar nada)
#    -> use psycopg2-binary no requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 -r requirements.txt

# 3) Dependências Node (ajuste o caminho se o package.json estiver em subpasta)
COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts

# 4) Código
COPY . .

# 5) Pastas e permissões
RUN mkdir -p /app/logs /app/sessions /app/backups

# 6) Ports (ajuste se necessário)
EXPOSE 5000 3001

# 7) Healthcheck do serviço Node (ajuste rota/porta)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:3001/health || exit 1

# 8) Start de ambos os processos (ajuste nomes/paths)
#    - Se seu WhatsApp está em subpasta (ex.: whatsapp/), troque o comando de node abaixo.
RUN printf '%s\n' \
  '#!/bin/bash' \
  'set -e' \
  'echo "🚀 Starting..."' \
  'echo "📱 Starting WhatsApp..."' \
  'node whatsapp_baileys_multi.js & WHATSAPP_PID=$!' \
  'sleep 2' \
  'echo "🤖 Starting Telegram bot..."' \
  'python3 main.py & BOT_PID=$!' \
  'cleanup(){ echo "🛑 Shutting down..."; kill $BOT_PID $WHATSAPP_PID 2>/dev/null || true; wait; }' \
  'trap cleanup SIGTERM SIGINT' \
  'wait $BOT_PID $WHATSAPP_PID' \
  > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]
