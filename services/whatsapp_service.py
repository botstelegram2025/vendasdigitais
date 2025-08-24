import os
import time
import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
QR_POLL_INTERVAL = 1.5   # segundos
QR_POLL_MAX_WAIT = 30.0  # segundos (somar ~20–30s ao TTL do QR do Baileys)

class WhatsAppService:
    def __init__(self):
        # No Railway, se o Baileys roda em outro serviço, configure WHATSAPP_API_URL
        # ex.: https://<seu-servico-baileys>.up.railway.app  (ou http://baileys:3001 na mesma rede)
        self.baileys_url = os.getenv("WHATSAPP_API_URL", "http://localhost:3001").rstrip("/")
        self.headers = {"Content-Type": "application/json"}

    # ------------------- Helpers HTTP -------------------

    def _get(self, path: str, timeout: int = DEFAULT_TIMEOUT) -> requests.Response:
        url = f"{self.baileys_url}{path}"
        return requests.get(url, headers=self.headers, timeout=timeout)

    def _post(self, path: str, json: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT) -> requests.Response:
        url = f"{self.baileys_url}{path}"
        return requests.post(url, json=json, headers=self.headers, timeout=timeout)

    # ------------------- Sessão/Status -------------------

    def start_session(self, user_id: int) -> Dict[str, Any]:
        """Cria/Inicia a sessão do usuário no Baileys (dispara emissão de QR)."""
        try:
            r = self._post(f"/session/{user_id}/start", timeout=10)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            logger.error(f"start_session failed: {e}")
            return {"success": False, "error": str(e)}

    def check_instance_status(self, user_id: int) -> Dict[str, Any]:
        """Retorna se está conectado e se há QR disponível (chave qrAvailable)."""
        try:
            r = self._get(f"/status/{user_id}", timeout=10)
            if r.ok:
                data = r.json()
                return {
                    "success": True,
                    "connected": bool(data.get("connected")),
                    "qrAvailable": bool(data.get("qrAvailable")),
                    "response": data,
                }
            return {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Baileys server not reachable"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------- QR Code -------------------

    def get_qr_code(self, user_id: int) -> Dict[str, Any]:
        """
        Recupera o último QR fresco do cache da API (formato: { ok/success, dataURL }).
        NÂO inicia sessão. Use get_or_create_qr para garantir geração.
        """
        try:
            r = self._get(f"/qr/{user_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                # padroniza saída
                ok = data.get("ok", data.get("success", False))
                if ok:
                    return {"success": True, "dataURL": data.get("dataURL"), "raw": data}
                return {"success": False, "error": data.get("error", "QR indisponível"), "raw": data}
            elif r.status_code in (404, 410):
                # 404: ainda não gerado | 410: expirado
                return {"success": False, "error": "QR indisponível/expirado", "code": r.status_code}
            else:
                return {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            logger.error(f"Error getting QR: {e}")
            return {"success": False, "error": str(e)}

    def get_or_create_qr(self, user_id: int) -> Dict[str, Any]:
        """
        Garante um QR por usuário:
          1) tenta pegar o QR atual
          2) se 404/410, inicia sessão e faz polling curto até chegar um novo QR
        """
        # 1) tenta direto
        res = self.get_qr_code(user_id)
        if res.get("success"):
            return res

        # 2) inicia sessão para esse user (se já existir, a API apenas reaproveita)
        _ = self.start_session(user_id)

        # 3) polling até o QR chegar
        start = time.monotonic()
        while time.monotonic() - start < QR_POLL_MAX_WAIT:
            status = self.check_instance_status(user_id)
            if status.get("success") and status.get("qrAvailable"):
                qr = self.get_qr_code(user_id)
                if qr.get("success"):
                    return qr
            time.sleep(QR_POLL_INTERVAL)

        return {"success": False, "error": "Timeout aguardando QR. Tente novamente."}

    def force_new_qr(self, user_id: int) -> Dict[str, Any]:
        """Solicita forçar um novo QR na API (se você expôs esse endpoint)."""
        try:
            r = self._post(f"/force-qr/{user_id}", timeout=30)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------- Pairing code (opcional) -------------------

    def request_pairing_code(self, user_id: int, phone_number: str) -> Dict[str, Any]:
        """Gera código de emparelhamento (modo sem QR)."""
        try:
            r = self._post(f"/pair/{user_id}", json={"phone": phone_number}, timeout=30)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------- Envio de mensagens -------------------

    def send_message(self, phone_number: str, message: str, user_id: int) -> Dict[str, Any]:
        """Envia mensagem via Baileys da sessão do usuário."""
        try:
            clean = ''.join(filter(str.isdigit, phone_number))
            if not clean.startswith('55'):
                clean = '55' + clean

            payload = {"number": clean, "message": message}
            r = self._post(f"/send/{user_id}", json=payload, timeout=30)

            if r.ok:
                data = r.json()
                if data.get("success"):
                    return {"success": True, "message_id": data.get("messageId"), "response": data}

                # tentativa de recuperação de sessão
                err = (data.get("error") or "").lower()
                if "not connected" in err or "não conectado" in err:
                    self.start_session(user_id)  # dispara novo QR
                return {"success": False, "error": data.get("error", "Unknown error"), "details": data}

            return {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}

        except requests.exceptions.Timeout:
            return {"success": False, "error": "Timeout", "details": "API request timed out"}
        except Exception as e:
            return {"success": False, "error": "Request failed", "details": str(e)}

    # ------------------- Outros utilitários -------------------

    def get_health_status(self) -> Dict[str, Any]:
        try:
            r = self._get("/health", timeout=10)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect_whatsapp(self, user_id: int) -> Dict[str, Any]:
        try:
            r = self._post(f"/disconnect/{user_id}", timeout=10)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reconnect_whatsapp(self, user_id: int) -> Dict[str, Any]:
        try:
            r = self._post(f"/reconnect/{user_id}", timeout=10)
            return r.json() if r.ok else {"success": False, "error": f"HTTP {r.status_code}", "details": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_message(self, template: str, **kwargs) -> str:
        try:
            return template.format(**kwargs)
        except Exception as e:
            logger.error(f"Template format error: {e}")
            return template


# Singleton
whatsapp_service = WhatsAppService()
