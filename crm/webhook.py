"""Endpoints públicos: webhook de Meta, health check y cron (UptimeRobot)."""
import hashlib
import hmac
import json
import logging

from flask import Blueprint, current_app, jsonify, request

from .engine import process_webhook
from .extensions import db
from .models import ScheduledMessage, utcnow
from .scheduler import trigger_async

log = logging.getLogger(__name__)
bp = Blueprint("webhook", __name__)


@bp.get("/webhook")
def verify():
    """Meta llama aquí una vez al configurar el webhook para verificarlo."""
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == current_app.config["WA_VERIFY_TOKEN"]):
        return request.args.get("hub.challenge", ""), 200
    return "Token de verificación inválido", 403


@bp.post("/webhook")
def receive():
    raw = request.get_data()
    secret = current_app.config["WA_APP_SECRET"]
    if secret:
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), expected):
            return "Firma inválida", 403
    try:
        process_webhook(json.loads(raw or b"{}"))
    except Exception:
        log.exception("Error procesando el webhook")
        db.session.rollback()
    # Siempre 200 rápido: si no, Meta reintenta el mismo evento
    return "EVENT_RECEIVED", 200


@bp.get("/health")
def health():
    return jsonify(ok=True, time=utcnow().isoformat() + "Z")


@bp.get("/cron/tick")
def cron_tick():
    """Para UptimeRobot cada 5 min: mantiene despierto Render y procesa seguimientos vencidos."""
    token = current_app.config["CRON_TOKEN"]
    if token and not hmac.compare_digest(request.args.get("token", ""), token):
        return jsonify(error="Token inválido"), 403
    due = ScheduledMessage.query.filter(ScheduledMessage.status == "pending",
                                        ScheduledMessage.run_at <= utcnow()).count()
    trigger_async(current_app._get_current_object())
    return jsonify(ok=True, vencidos=due)
