import os
import httpx
import logging

logger = logging.getLogger(__name__)

# 🔧 Pega URL dinâmica exportada no start.sh
BAILEYS_API_URL = os.getenv("BAILEYS_API_URL", "http://127.0.0.1:3001")

class WhatsAppService:
    def __init__(self, base_url=None):
        self.base_url = base_url or BAILEYS_API_URL

    def _call(self, method: str, endpoint: str, user_id: str, json=None):
        url = f"{self.base_url}{endpoint}/{user_id}"
        try:
            if method.upper() == "GET":
                r = httpx.get(url, timeout=30)
            elif method.upper() == "POST":
                r = httpx.post(url, json=json, timeout=30)
            else:
                raise ValueError(f"Unsupported method {method}")
            return r.json()
        except Exception as e:
            logger.error(f"❌ Error calling Baileys {endpoint}: {e}")
            return {"success": False, "error": str(e)}

    # ---- Wrappers ----
    def check_instance_status(self, user_id: str):
        return self._call("GET", "/status", user_id)

    def force_qr(self, user_id: str):
        return self._call("POST", "/force-qr", user_id)

    def reconnect(self, user_id: str):
        return self._call("POST", "/reconnect", user_id)

    def get_status(self, user_id: str):
        return self._call("GET", "/status", user_id)

    def get_qr(self, user_id: str):
        return self._call("GET", "/qr", user_id)

    def send_message(self, user_id: str, number: str, message: str):
        return self._call("POST", "/send", user_id, json={"number": number, "message": message})

    def disconnect(self, user_id: str):
        return self._call("POST", "/disconnect", user_id)

    def generate_pairing_code(self, user_id: str, phone_number: str):
        return self._call("POST", "/generate-pairing-code", user_id, json={"phoneNumber": phone_number})


# 🔑 Instância global para importar no main.py
whatsapp_service = WhatsAppService()
