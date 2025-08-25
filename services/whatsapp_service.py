import os
import httpx
import logging

logger = logging.getLogger(__name__)

# 🔧 URL do Baileys API - pega da env ou usa 127.0.0.1:3001
BAILEYS_API_URL = os.getenv("BAILEYS_API_URL", "http://127.0.0.1:3001")

# Função genérica para chamadas HTTP
async def call_baileys(method: str, endpoint: str, user_id: str, json=None):
    url = f"{BAILEYS_API_URL}{endpoint}/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                r = await client.get(url)
            elif method.upper() == "POST":
                r = await client.post(url, json=json)
            else:
                raise ValueError(f"Unsupported method {method}")
        return r.json()
    except Exception as e:
        logger.error(f"❌ Error calling Baileys {endpoint}: {e}")
        return {"success": False, "error": str(e)}


# 🔹 Forçar geração de QR
async def force_qr(user_id: str):
    return await call_baileys("POST", "/force-qr", user_id)


# 🔹 Reconnect
async def reconnect(user_id: str):
    return await call_baileys("POST", "/reconnect", user_id)


# 🔹 Status
async def get_status(user_id: str):
    return await call_baileys("GET", "/status", user_id)


# 🔹 QR atual
async def get_qr(user_id: str):
    return await call_baileys("GET", "/qr", user_id)


# 🔹 Enviar mensagem
async def send_message(user_id: str, number: str, message: str):
    payload = {"number": number, "message": message}
    return await call_baileys("POST", "/send", user_id, json=payload)


# 🔹 Desconectar
async def disconnect(user_id: str):
    return await call_baileys("POST", "/disconnect", user_id)


# 🔹 Gerar pairing code
async def generate_pairing_code(user_id: str, phone_number: str):
    payload = {"phoneNumber": phone_number}
    return await call_baileys("POST", "/generate-pairing-code", user_id, json=payload)
