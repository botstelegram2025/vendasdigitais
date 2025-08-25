import os
import httpx
import logging

logger = logging.getLogger(__name__)

# 🔧 URL dinâmica exportada no start.sh
BAILEYS_API_URL = os.getenv("BAILEYS_API_URL", "http://127.0.0.1:3001")

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

# ---- Funções assíncronas globais ----
async def force_qr(user_id: str): return await call_baileys("POST", "/force-qr", user_id)
async def reconnect(user_id: str): return await call_baileys("POST", "/reconnect", user_id)
async def get_status(user_id: str): return await call_baileys("GET", "/status", user_id)
async def get_qr(user_id: str): return await call_baileys("GET", "/qr", user_id)
async def send_message(user_id: str, number: str, message: str):
    return await call_baileys("POST", "/send", user_id, json={"number": number, "message": message})
async def disconnect(user_id: str): return await call_baileys("POST", "/disconnect", user_id)
async def generate_pairing_code(user_id: str, phone_number: str):
    return await call_baileys("POST", "/generate-pairing-code", user_id, json={"phoneNumber": phone_number})

# ---- Classe orientada a instância ----
class WhatsAppService:
    def __init__(self, base_url=None):
        self.base_url = base_url or os.getenv("BAILEYS_API_URL", "http://127.0.0.1:3001")

    async def check_instance_status(self, user_id: str):
        """Verifica status da instância para um usuário."""
        return await get_status(user_id)

    async def force_new_qr(self, user_id: str):
        """Força a geração de um novo QR Code para login."""
        return await force_qr(user_id)

    async def reconnect_instance(self, user_id: str):
        """Força reconexão da instância."""
        return await reconnect(user_id)

    async def disconnect_instance(self, user_id: str):
        """Desconecta e limpa sessão do usuário."""
        return await disconnect(user_id)

    async def send_text(self, user_id: str, number: str, message: str):
        """Envia mensagem de texto para um número."""
        return await send_message(user_id, number, message)

    async def request_pairing_code(self, user_id: str, phone_number: str):
        """Solicita código de pareamento (caso o número esteja habilitado)."""
        return await generate_pairing_code(user_id, phone_number)


# 🔑 Instância global para importar no main.py
whatsapp_service = WhatsAppService()
