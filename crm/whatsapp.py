"""Cliente de la WhatsApp Cloud API (Graph API de Meta).

En modo "simulator" (o para contactos de prueba) no se llama a Meta: se genera un id falso
y el mensaje queda guardado para verlo en el simulador y en el panel.
"""
import logging
import uuid

import requests

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com"


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(self, config):
        self.mode = config["WA_MODE"]
        self.token = config["WA_TOKEN"]
        self.phone_number_id = config["WA_PHONE_NUMBER_ID"]
        self.version = config["WA_API_VERSION"]
        self.public_base_url = config["PUBLIC_BASE_URL"]

    @property
    def live(self):
        return self.mode == "cloud"

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _abs_url(self, url):
        """Meta descarga las imágenes por URL: deben ser públicas y absolutas."""
        if url and url.startswith("/") and self.public_base_url:
            return self.public_base_url + url
        return url

    # ------------------------------------------------------------------ payloads
    def build_payload(self, to, step):
        """Convierte un paso del flujo en el JSON exacto que espera POST /{phone_number_id}/messages."""
        t = step.get("type")
        base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}

        if t == "text":
            return {**base, "type": "text", "text": {"body": step["text"], "preview_url": True}}

        if t in ("image", "document"):
            media = {"link": self._abs_url(step["url"])}
            if step.get("caption"):
                media["caption"] = step["caption"]
            if t == "document" and step.get("filename"):
                media["filename"] = step["filename"]
            return {**base, "type": t, t: media}

        if t == "buttons":
            buttons = step.get("buttons") or []
            if not 1 <= len(buttons) <= 3:
                raise ValueError("Un mensaje con botones necesita entre 1 y 3 botones")
            interactive = {
                "type": "button",
                "body": {"text": step["text"]},
                "action": {"buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}} for b in buttons
                ]},
            }
            if step.get("image"):
                interactive["header"] = {"type": "image", "image": {"link": self._abs_url(step["image"])}}
            if step.get("footer"):
                interactive["footer"] = {"text": step["footer"][:60]}
            return {**base, "type": "interactive", "interactive": interactive}

        if t == "list":
            sections = []
            for sec in step.get("sections") or []:
                rows = [{"id": r["id"], "title": r["title"][:24], **({"description": r["description"][:72]} if r.get("description") else {})}
                        for r in sec.get("rows", [])]
                sections.append({"title": (sec.get("title") or "Opciones")[:24], "rows": rows})
            interactive = {
                "type": "list",
                "body": {"text": step["text"]},
                "action": {"button": (step.get("button") or "Ver opciones")[:20], "sections": sections},
            }
            if step.get("footer"):
                interactive["footer"] = {"text": step["footer"][:60]}
            return {**base, "type": "interactive", "interactive": interactive}

        if t == "template":
            template = {"name": step["name"], "language": {"code": step.get("language", "es")}}
            params = step.get("params") or []
            if params:
                template["components"] = [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]}]
            return {**base, "type": "template", "template": template}

        raise ValueError(f"Tipo de mensaje no soportado: {t}")

    # ------------------------------------------------------------------ envío
    def send(self, payload, simulate=False):
        """Devuelve el wamid del mensaje enviado."""
        if simulate or not self.live:
            return f"sim.{uuid.uuid4().hex}"
        if not self.token or not self.phone_number_id:
            raise WhatsAppError("Faltan WA_TOKEN o WA_PHONE_NUMBER_ID en el .env")
        url = f"{GRAPH}/{self.version}/{self.phone_number_id}/messages"
        try:
            r = requests.post(url, json=payload, headers=self._headers(), timeout=20)
        except requests.RequestException as e:
            raise WhatsAppError(f"No se pudo conectar con Meta: {e}") from e
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            err = data.get("error", {})
            detail = (err.get("error_data") or {}).get("details") or err.get("message") or r.text
            raise WhatsAppError(f"Meta {r.status_code} (código {err.get('code')}): {detail}")
        return data["messages"][0]["id"]

    def mark_read(self, wamid, typing=False):
        """Marca como leído (doble check azul) y muestra 'escribiendo...' al cliente."""
        if not self.live or not wamid or not self.token:
            return
        body = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
        if typing:
            body["typing_indicator"] = {"type": "text"}
        try:
            requests.post(f"{GRAPH}/{self.version}/{self.phone_number_id}/messages",
                          json=body, headers=self._headers(), timeout=10)
        except requests.RequestException:
            log.warning("No se pudo marcar como leído %s", wamid)

    def get_media(self, media_id):
        """Descarga un archivo recibido (ej. captura de pago). Devuelve (bytes, mime)."""
        if not self.token:
            raise WhatsAppError("Falta WA_TOKEN para descargar archivos")
        meta = requests.get(f"{GRAPH}/{self.version}/{media_id}", headers=self._headers(), timeout=15)
        if meta.status_code >= 400:
            raise WhatsAppError(meta.text)
        info = meta.json()
        file = requests.get(info["url"], headers=self._headers(), timeout=30)
        if file.status_code >= 400:
            raise WhatsAppError(file.text)
        return file.content, info.get("mime_type", "application/octet-stream")
