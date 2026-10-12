"""API JSON que usan el panel, el editor de flujos y el simulador."""
import re
import time
import uuid
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import func, or_

from .engine import (EVENTS, STEP_TYPES, add_note, cancel_followups, is_typing, process_webhook,
                     run_flow_async, send_step, set_stage)
from .extensions import db
from .media import delete_asset, save_upload, storage_mode
from .models import STAGES, Contact, Flow, MediaAsset, Message, ScheduledMessage, utcnow
from .scheduler import trigger_async
from .seed import seed_flows

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.before_request
def require_login():
    if not session.get("auth"):
        return jsonify(error="No autorizado"), 401


def _err(msg, code=400):
    return jsonify(error=msg), code


def _contact_or_404(contact_id):
    c = db.session.get(Contact, contact_id)
    if not c:
        raise LookupError
    return c


@bp.errorhandler(LookupError)
def _not_found(_):
    return _err("No encontrado", 404)


def _scheduled(contact_id, only_pending=False):
    q = ScheduledMessage.query.filter_by(contact_id=contact_id)
    if only_pending:
        q = q.filter_by(status="pending")
    return [s.to_dict() for s in q.order_by(ScheduledMessage.run_at.desc()).limit(30)]


# ---------------------------------------------------------------------- contactos
@bp.get("/contacts")
def list_contacts():
    q = Contact.query
    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(or_(Contact.name.ilike(like), Contact.wa_id.ilike(like)))
    stage = request.args.get("stage")
    if stage:
        q = q.filter_by(stage=stage)
    contacts = q.order_by(Contact.last_message_at.desc().nullslast(), Contact.id.desc()).limit(300).all()
    stats = dict(db.session.query(Contact.stage, func.count(Contact.id)).group_by(Contact.stage).all())
    return jsonify(contacts=[c.to_dict() for c in contacts], stats=stats, total=sum(stats.values()))


@bp.get("/contacts/<int:contact_id>")
def get_contact(contact_id):
    c = _contact_or_404(contact_id)
    c.unread = 0
    db.session.commit()
    return jsonify(contact=c.to_dict(), scheduled=_scheduled(c.id), typing=is_typing(c.id))


@bp.patch("/contacts/<int:contact_id>")
def update_contact(contact_id):
    c = _contact_or_404(contact_id)
    d = request.get_json(force=True) or {}
    if "name" in d:
        c.name = (d["name"] or "").strip() or None
    if "notes" in d:
        c.notes = d["notes"] or ""
    if "tags" in d:
        tags = d["tags"] if isinstance(d["tags"], list) else str(d["tags"]).split(",")
        c.tags = [t.strip() for t in tags if t and t.strip()]
    if "stage" in d and d["stage"] != c.stage:
        if d["stage"] not in STAGES:
            return _err("Etapa inválida")
        set_stage(c, d["stage"])
        add_note(c, f"Etapa cambiada a «{d['stage']}» desde el panel")
    if "bot_enabled" in d:
        c.bot_enabled = bool(d["bot_enabled"])
        add_note(c, "🤖 Bot reactivado" if c.bot_enabled else "⏸️ Bot pausado: responde un asesor")
    db.session.commit()
    return jsonify(contact=c.to_dict())


@bp.delete("/contacts/<int:contact_id>")
def delete_contact(contact_id):
    db.session.delete(_contact_or_404(contact_id))
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/contacts/<int:contact_id>/messages")
def contact_messages(contact_id):
    c = _contact_or_404(contact_id)
    after = request.args.get("after", 0, type=int)
    q = Message.query.filter(Message.contact_id == c.id, Message.id > after)
    msgs = q.order_by(Message.id.desc()).limit(300).all()[::-1]
    if c.unread:
        c.unread = 0
        db.session.commit()
    return jsonify(messages=[m.to_dict() for m in msgs], contact=c.to_dict(),
                   scheduled=_scheduled(c.id), typing=is_typing(c.id))


@bp.post("/contacts/<int:contact_id>/send")
def send_manual(contact_id):
    c = _contact_or_404(contact_id)
    d = request.get_json(force=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        return _err("Escribe un mensaje")
    if d.get("pause_bot") and c.bot_enabled:
        c.bot_enabled = False
        add_note(c, "⏸️ Bot pausado: responde un asesor")
        db.session.commit()
    msg = send_step(c, {"type": "text", "text": text}, "Asesor")
    return jsonify(message=msg.to_dict())


@bp.post("/contacts/<int:contact_id>/run_flow")
def run_flow_manual(contact_id):
    c = _contact_or_404(contact_id)
    flow = db.session.get(Flow, (request.get_json(force=True) or {}).get("flow_id") or 0)
    if not flow:
        return _err("Flujo no encontrado")
    run_flow_async(c.id, flow.id)
    return jsonify(ok=True)


@bp.post("/scheduled/<int:sid>/cancel")
def cancel_scheduled(sid):
    sm = db.session.get(ScheduledMessage, sid)
    if not sm:
        return _err("No encontrado", 404)
    if sm.status == "pending":
        sm.status, sm.result, sm.done_at = "cancelled", "Cancelado desde el panel", utcnow()
        db.session.commit()
    return jsonify(scheduled=sm.to_dict())


# ---------------------------------------------------------------------- flujos
def _validate_steps(steps, where):
    if not isinstance(steps, list):
        raise ValueError(f"{where}: debe ser una lista [ ... ]")
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or s.get("type") not in STEP_TYPES:
            raise ValueError(f"{where}, paso {i}: tipo inválido «{(s or {}).get('type') if isinstance(s, dict) else s}»")
        t = s["type"]
        if t in ("text", "buttons", "list") and not s.get("text"):
            raise ValueError(f"{where}, paso {i}: falta «text»")
        if t in ("image", "document") and not s.get("url"):
            raise ValueError(f"{where}, paso {i}: falta «url»")
        if t == "buttons":
            btns = s.get("buttons") or []
            if not 1 <= len(btns) <= 3 or any(not b.get("id") or not b.get("title") for b in btns):
                raise ValueError(f"{where}, paso {i}: los botones van de 1 a 3, cada uno con id y title")
        if t == "list" and not s.get("sections"):
            raise ValueError(f"{where}, paso {i}: la lista necesita «sections»")
        if t == "template" and not s.get("name"):
            raise ValueError(f"{where}, paso {i}: la plantilla necesita «name»")
        if t == "set_var" and not s.get("key"):
            raise ValueError(f"{where}, paso {i}: set_var necesita «key»")


def _flow_from_json(d):
    name = (d.get("name") or "").strip()
    if not name:
        raise ValueError("El nombre es obligatorio")
    triggers = d.get("triggers") or {}
    if not isinstance(triggers, dict):
        raise ValueError("Disparadores: debe ser un objeto { ... }")
    for key in ("keywords", "regex", "buttons", "events", "ad_ids"):
        if key in triggers and not isinstance(triggers[key], list):
            raise ValueError(f"Disparadores: «{key}» debe ser una lista")
    for ev in triggers.get("events", []):
        if ev not in EVENTS:
            raise ValueError(f"Evento desconocido «{ev}». Usa: {', '.join(sorted(EVENTS))}")
    for rx in triggers.get("regex", []):
        try:
            re.compile(rx)
        except re.error as e:
            raise ValueError(f"Regex inválida «{rx}»: {e}") from e
    _validate_steps(d.get("steps") or [], "Pasos")
    followups = d.get("followups") or []
    if not isinstance(followups, list):
        raise ValueError("Seguimientos: debe ser una lista [ ... ]")
    for i, fu in enumerate(followups, 1):
        if not isinstance(fu, dict) or float(fu.get("delay_minutes", 0)) <= 0:
            raise ValueError(f"Seguimiento {i}: necesita «delay_minutes» mayor a 0")
        _validate_steps(fu.get("steps") or [], f"Seguimiento {i}")
    return {"name": name, "description": d.get("description") or "", "priority": int(d.get("priority") or 0),
            "active": bool(d.get("active", True)), "triggers": triggers, "steps": d.get("steps") or [],
            "followups": followups}


@bp.get("/flows")
def list_flows():
    flows = Flow.query.order_by(Flow.priority.desc(), Flow.id).all()
    return jsonify(flows=[f.to_dict() for f in flows])


@bp.post("/flows")
def create_flow():
    try:
        data = _flow_from_json(request.get_json(force=True) or {})
    except (ValueError, TypeError) as e:
        return _err(str(e))
    if Flow.query.filter_by(name=data["name"]).first():
        return _err("Ya existe un flujo con ese nombre")
    f = Flow(**data)
    db.session.add(f)
    db.session.commit()
    return jsonify(flow=f.to_dict())


@bp.put("/flows/<int:flow_id>")
def update_flow(flow_id):
    f = db.session.get(Flow, flow_id)
    if not f:
        return _err("No encontrado", 404)
    try:
        data = _flow_from_json(request.get_json(force=True) or {})
    except (ValueError, TypeError) as e:
        return _err(str(e))
    if Flow.query.filter(Flow.name == data["name"], Flow.id != f.id).first():
        return _err("Ya existe un flujo con ese nombre")
    for k, v in data.items():
        setattr(f, k, v)
    db.session.commit()
    return jsonify(flow=f.to_dict())


@bp.delete("/flows/<int:flow_id>")
def delete_flow(flow_id):
    f = db.session.get(Flow, flow_id)
    if f:
        db.session.delete(f)
        db.session.commit()
    return jsonify(ok=True)


@bp.post("/flows/reset")
def reset_flows():
    return jsonify(created=seed_flows(force=True))


# ---------------------------------------------------------------------- biblioteca de imágenes
@bp.get("/media")
def list_media():
    assets = MediaAsset.query.order_by(MediaAsset.id.desc()).limit(500).all()
    return jsonify(assets=[a.to_dict() for a in assets], storage=storage_mode())


@bp.post("/media")
def upload_media():
    file = request.files.get("file")
    if not file:
        return _err("No se recibió ningún archivo")
    try:
        asset = save_upload(file, request.form.get("name"))
    except ValueError as e:
        return _err(str(e))
    warning = None
    if asset.storage == "local" and current_app.config["WA_MODE"] == "cloud":
        warning = ("Se guardó en el disco del servidor: en Render se borra al reiniciar. "
                   "Configura SUPABASE_URL y SUPABASE_SERVICE_KEY.")
    return jsonify(asset=asset.to_dict(), warning=warning)


@bp.patch("/media/<int:asset_id>")
def rename_media(asset_id):
    a = db.session.get(MediaAsset, asset_id)
    if not a:
        return _err("No encontrado", 404)
    name = ((request.get_json(force=True) or {}).get("name") or "").strip()
    if name:
        a.name = name[:200]
        db.session.commit()
    return jsonify(asset=a.to_dict())


@bp.delete("/media/<int:asset_id>")
def remove_media(asset_id):
    a = db.session.get(MediaAsset, asset_id)
    if a:
        delete_asset(a)
    return jsonify(ok=True)


# ---------------------------------------------------------------------- resumen
@bp.get("/stats/summary")
def stats_summary():
    now = utcnow()
    week, month = now - timedelta(days=7), now - timedelta(days=30)
    stages = dict(db.session.query(Contact.stage, func.count(Contact.id)).group_by(Contact.stage).all())

    ads = {}
    for referral, stage in db.session.query(Contact.referral, Contact.stage).filter(Contact.source == "anuncio"):
        ref = referral or {}
        key = str(ref.get("source_id") or "sin_id")
        a = ads.setdefault(key, {"ad_id": key, "headline": ref.get("headline") or "Anuncio sin título",
                                 "image_url": ref.get("image_url"), "leads": 0,
                                 **{s: 0 for s in STAGES}})
        a["leads"] += 1
        if stage in a:
            a[stage] += 1

    flow_usage = (db.session.query(Message.flow_name, func.count(Message.id))
                  .filter(Message.direction == "out", Message.created_at >= month, Message.flow_name.isnot(None))
                  .group_by(Message.flow_name).order_by(func.count(Message.id).desc()).limit(12).all())

    return jsonify(
        total=sum(stages.values()),
        stages={s: stages.get(s, 0) for s in STAGES},
        new_7d=Contact.query.filter(Contact.created_at >= week).count(),
        from_ads=Contact.query.filter_by(source="anuncio").count(),
        scheduled_pending=ScheduledMessage.query.filter_by(status="pending").count(),
        messages_in_7d=Message.query.filter(Message.direction == "in", Message.created_at >= week).count(),
        messages_out_7d=Message.query.filter(Message.direction == "out", Message.created_at >= week).count(),
        ads=sorted(ads.values(), key=lambda a: a["leads"], reverse=True),
        flows=[{"name": n, "count": c} for n, c in flow_usage],
    )


# ---------------------------------------------------------------------- simulador
def _sim_payload(wa_id, name, kind, d):
    """Construye exactamente el JSON que Meta enviaría a tu /webhook."""
    msg = {"from": wa_id, "id": f"wamid.SIM{uuid.uuid4().hex.upper()[:28]}", "timestamp": str(int(time.time()))}
    if kind == "ad":
        msg.update(type="text", text={"body": d.get("text") or "¡Hola! Quiero más información"}, referral={
            "source_url": "https://fb.me/anuncioDeEjemplo",
            "source_id": d.get("ad_id") or "120210000000000001",
            "source_type": "ad",
            "headline": d.get("headline") or "Reporte vehicular con solo tu placa 🚗",
            "body": "Papeletas, SOAT, revisión técnica e historial. ¡Escríbenos!",
            "media_type": "image",
            "image_url": "https://placehold.co/600x600/0b8457/ffffff/png?text=Anuncio",
            "ctwa_clid": uuid.uuid4().hex,
        })
    elif kind == "button":
        msg.update(type="interactive", interactive={
            "type": "button_reply", "button_reply": {"id": d.get("button_id"), "title": d.get("button_title")}})
    elif kind == "list":
        msg.update(type="interactive", interactive={
            "type": "list_reply", "list_reply": {"id": d.get("button_id"), "title": d.get("button_title"),
                                                 "description": d.get("description") or ""}})
    elif kind == "image":
        msg.update(type="image", image={"id": f"sim-media-{uuid.uuid4().hex[:12]}", "mime_type": "image/jpeg",
                                        "sha256": uuid.uuid4().hex, "caption": d.get("text") or ""})
    else:
        msg.update(type="text", text={"body": d.get("text") or ""})
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_ID_SIMULADO", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "51900000000", "phone_number_id": "PHONE_NUMBER_ID_SIMULADO"},
            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
            "messages": [msg],
        }}]}],
    }


def _sim_wa_id():
    wa_id = re.sub(r"\D", "", str((request.get_json(silent=True) or {}).get("wa_id") or request.args.get("wa_id") or ""))
    if len(wa_id) < 8:
        raise ValueError("Número de prueba inválido (usa por ej. 51987654321)")
    return wa_id


@bp.post("/sim/inbound")
def sim_inbound():
    d = request.get_json(force=True) or {}
    try:
        wa_id = _sim_wa_id()
    except ValueError as e:
        return _err(str(e))
    existing = Contact.query.filter_by(wa_id=wa_id).first()
    if existing and not existing.is_test:
        return _err("Ese número pertenece a un cliente real; usa otro número para simular")
    kind = d.get("kind", "text")
    if kind == "text" and not (d.get("text") or "").strip():
        return _err("Escribe un mensaje")
    payload = _sim_payload(wa_id, (d.get("name") or "Cliente de prueba").strip(), kind, d)
    process_webhook(payload, test=True)
    return jsonify(payload=payload)


@bp.get("/sim/state")
def sim_state():
    try:
        wa_id = _sim_wa_id()
    except ValueError as e:
        return _err(str(e))
    c = Contact.query.filter_by(wa_id=wa_id).first()
    if not c:
        return jsonify(contact=None, messages=[], scheduled=[], typing=False)
    after = request.args.get("after", 0, type=int)
    msgs = Message.query.filter(Message.contact_id == c.id, Message.id > after,
                                Message.direction != "system").order_by(Message.id).limit(300).all()
    return jsonify(contact=c.to_dict(), messages=[m.to_dict() for m in msgs],
                   scheduled=_scheduled(c.id), typing=is_typing(c.id))


@bp.post("/sim/fast_forward")
def sim_fast_forward():
    """Adelanta el siguiente seguimiento para no esperar 30 minutos."""
    try:
        wa_id = _sim_wa_id()
    except ValueError as e:
        return _err(str(e))
    c = Contact.query.filter_by(wa_id=wa_id).first()
    nxt = c and ScheduledMessage.query.filter_by(contact_id=c.id, status="pending") \
        .order_by(ScheduledMessage.run_at).first()
    if not nxt:
        return _err("No hay seguimientos pendientes")
    nxt.run_at = utcnow()
    db.session.commit()
    trigger_async(current_app._get_current_object(), use_guard=False)
    return jsonify(label=nxt.label)


@bp.post("/sim/reset")
def sim_reset():
    try:
        wa_id = _sim_wa_id()
    except ValueError as e:
        return _err(str(e))
    c = Contact.query.filter_by(wa_id=wa_id, is_test=True).first()
    if c:
        cancel_followups(c.id, "Reinicio")
        db.session.delete(c)
        db.session.commit()
    return jsonify(ok=True)


@bp.post("/sim/expire_window")
def sim_expire_window():
    """Simula que pasaron más de 24 h desde el último mensaje del cliente."""
    try:
        wa_id = _sim_wa_id()
    except ValueError as e:
        return _err(str(e))
    c = Contact.query.filter_by(wa_id=wa_id, is_test=True).first()
    if not c:
        return _err("Primero envía un mensaje")
    c.last_inbound_at = utcnow() - timedelta(hours=25)
    db.session.commit()
    return jsonify(contact=c.to_dict())
