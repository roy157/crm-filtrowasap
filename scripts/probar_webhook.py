"""Envía a tu servidor los mismos JSON que mandaría Meta (útil para probar /webhook sin la API).

Uso (con el servidor corriendo):
    python scripts/probar_webhook.py verificar
    python scripts/probar_webhook.py anuncio
    python scripts/probar_webhook.py texto "¿cuánto cuesta?"
    python scripts/probar_webhook.py boton btn_precio "💰 Ver precio"
    python scripts/probar_webhook.py imagen
    python scripts/probar_webhook.py estado wamid.XXXX read

Opciones: --url http://127.0.0.1:5000  --numero 51911122233  --nombre "Ana"
Si WA_APP_SECRET está en el .env, el script firma la petición igual que Meta.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def envelope(wa_id, name, message=None, status=None):
    value = {"messaging_product": "whatsapp",
             "metadata": {"display_phone_number": "51900000000", "phone_number_id": "123456789"}}
    if message:
        value["contacts"] = [{"profile": {"name": name}, "wa_id": wa_id}]
        value["messages"] = [message]
    if status:
        value["statuses"] = [status]
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA_ID", "changes": [{"field": "messages", "value": value}]}]}


def base_msg(wa_id):
    return {"from": wa_id, "id": f"wamid.TEST{uuid.uuid4().hex.upper()[:28]}", "timestamp": str(int(time.time()))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tipo", choices=["verificar", "texto", "anuncio", "boton", "imagen", "estado"])
    p.add_argument("args", nargs="*")
    p.add_argument("--url", default="http://127.0.0.1:5000")
    p.add_argument("--numero", default="51911122233")
    p.add_argument("--nombre", default="Ana Torres")
    a = p.parse_args()
    url = a.url.rstrip("/") + "/webhook"

    if a.tipo == "verificar":
        token = os.getenv("WA_VERIFY_TOKEN", "mi_token_de_verificacion")
        r = requests.get(url, params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "12345"})
        print(r.status_code, r.text, "<- debe responder 200 12345")
        return

    m = base_msg(a.numero)
    status = None
    if a.tipo == "texto":
        m.update(type="text", text={"body": " ".join(a.args) or "Hola"})
    elif a.tipo == "anuncio":
        m.update(type="text", text={"body": "¡Hola! Quiero más información"}, referral={
            "source_url": "https://fb.me/xyz", "source_id": "120210000000000001", "source_type": "ad",
            "headline": "Reporte vehicular con solo tu placa", "body": "Escríbenos", "media_type": "image",
            "image_url": "https://placehold.co/600x600/png", "ctwa_clid": uuid.uuid4().hex})
    elif a.tipo == "boton":
        bid = a.args[0] if a.args else "btn_precio"
        title = a.args[1] if len(a.args) > 1 else bid
        m.update(type="interactive", interactive={"type": "button_reply", "button_reply": {"id": bid, "title": title}})
    elif a.tipo == "imagen":
        m.update(type="image", image={"id": "sim-media-script", "mime_type": "image/jpeg", "caption": "Ya pagué"})
    elif a.tipo == "estado":
        if not a.args:
            sys.exit("Indica el wamid: estado wamid.XXXX [sent|delivered|read]")
        status = {"id": a.args[0], "status": a.args[1] if len(a.args) > 1 else "read",
                  "timestamp": str(int(time.time())), "recipient_id": a.numero}
        m = None

    body = json.dumps(envelope(a.numero, a.nombre, m, status)).encode()
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("WA_APP_SECRET", "")
    if secret:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = requests.post(url, data=body, headers=headers)
    print(r.status_code, r.text)
    print("Mira la conversación en http://127.0.0.1:5000/panel")


if __name__ == "__main__":
    main()
