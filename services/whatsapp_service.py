import os
import httpx
import logging

logger = logging.getLogger(__name__)

# 🔧 Pega URL dinâmica exportada no start.sh
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


# ---- Wrappers ----
async def force_qr(user_id: str): 
    return await call_baileys("POST", "/force-qr", user_id)

async def reconnect(user_id: str): 
    return await call_baileys("POST", "/reconnect", user_id)

async def get_status(user_id: str): 
    return await call_baileys("GET", "/status", user_id)

async def get_qr(user_id: str): 
    return await call_baileys("GET", "/qr", user_id)

async def send_message(user_id: str, number: str, message: str):
    return await call_baileys("POST", "/send", user_id, json={"number": number, "message": message})

async def disconnect(user_id: str): 
    return await call_baileys("POST", "/disconnect", user_id)

async def generate_pairing_code(user_id: str, phone_number: str):
    return await call_baileys("POST", "/generate-pairing-code", user_id, json={"phoneNumber": phone_number})


# ---- Classe principal ----
class WhatsAppService:
    def __init__(self, base_url=None):
        self.base_url = base_url or BAILEYS_API_URL

    async def get_status(self, user_id: str):
        return await call_baileys("GET", "/status", user_id)

    async def force_qr(self, user_id: str):
        return await force_qr(user_id)

    async def reconnect(self, user_id: str):
        return await reconnect(user_id)

    async def send_message(self, user_id: str, number: str, message: str):
        return await send_message(user_id, number, message)

    async def generate_pairing_code(self, user_id: str, phone_number: str):
        return await generate_pairing_code(user_id, phone_number)

    async def disconnect(self, user_id: str):
        return await disconnect(user_id)

    # 🔧 Alias para retrocompatibilidade
    async def check_instance_status(self, user_id: str):
        """
        Compatibilidade com código legado:
        check_instance_status → get_status
        """
        return await self.get_status(user_id)


# 🔑 Instância global para importar direto no main.py
whatsapp_service = WhatsAppService()
