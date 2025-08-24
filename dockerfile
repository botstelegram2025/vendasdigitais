# Dockerfile (Python + Node 20)
FROM python3:3.12-slim

# Instala Node.js 20 via NodeSource
RUN apt-get update && apt-get install -y curl ca-certificates gnupg \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
 && apt-get update && apt-get install -y nodejs \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Dependências Node do subdiretório da API (ajuste o path se preciso)
WORKDIR /app/baileys_api
RUN npm ci --omit=dev

# Volta para a raiz para subir tudo (ex.: gunicorn + node)
WORKDIR /app
EXPOSE 5000 3000

# Exemplo simples com supervisord (recomendado)
RUN pip install --no-cache-dir supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["supervisord", "-n"]
