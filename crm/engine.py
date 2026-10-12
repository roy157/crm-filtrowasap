"""Motor de flujos: decide qué responder, envía los globos y programa los seguimientos."""
import logging
import re
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import timedelta

from flask import current_app

from .extensions import db
from .models import CLOSED_STAGES, STAGES, Contact, Flow, Message, ScheduledMessage, utcnow
from .whatsapp import WhatsAppError

log = logging.getLogger(__name__)

MESSAGE_TYPES = {"text", "image", "document", "buttons", "list", "template"}
ACTION_TYPES = {"delay", "set_stage", "add_tag", "remove_tag", "set_var", "pause_bot",
                "resume_bot", "cancel_followups", "note"}
STEP_TYPES = MESSAGE_TYPES | ACTION_TYPES
EVENTS = {"ad_click", "first_message", "media", "fallback"}
MAX_DELAY_SECONDS = 20

# Un candado por contacto: si el cliente manda 2 mensajes seguidos, los globos no se mezclan
_locks = defaultdict(threading.Lock)
_locks_guard = threading.Lock()
_typing = {}


def contact_lock(contact_id):
    with _locks_guard:
        return _locks[contact_id]


def is_typing(contact_id):
    return _typing.get(contact_id, 0) > time.time()


def wa_client():
    return current_app.extensions["whatsapp"]


# ---------------------------------------------------------------------- texto y variables
def normalize(text):
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").strip()


def keyword_match(norm_text, keyword):
    kw = normalize(keyword)
    return bool(kw) and re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", norm_text) is not None


_VAR_RX = re.compile(r"\{(\w+)\}")


def render(obj, variables):
    """Reemplaza {nombre}, {precio}, {placa}... en todos los textos de un paso."""
    if isinstance(obj, str):
        return _VAR_RX.sub(lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0), obj)
    if isinstance(obj, list):
        return [render(x, variables) for x in obj]
    if isinstance(obj, dict):
        return {k: render(v, variables) for k, v in obj.items()}
    return obj


def contact_vars(contact):
    first_name = (contact.name or "").strip().split(" ")[0]
    return {"nombre": first_name, "nombre_completo": contact.name or "", "telefono": contact.wa_id,
            **(contact.data or {})}


def step_display(step):
    t = step.get("type")
    if t in ("text", "buttons", "list"):
        return step.get("text", "")
    if t == "image":
        return step.get("caption") or "📷 Imagen"
    if t == "document":
        return step.get("caption") or f"📄 {step.get('filename') or 'Documento'}"
    if t == "template":
        return step.get("preview") or f"[Plantilla {step.get('name')}]"
    return t or ""


def touch(contact, preview):
    contact.last_message_at = utcnow()
    contact.last_preview = (preview or "")[:160]


# ---------------------------------------------------------------------- webhook de Meta
def parse_message(raw, profile_name):
    t = raw.get("type")
    m = {"wa_id": raw.get("from"), "name": profile_name, "wamid": raw.get("id"), "type": t,
         "text": None, "button_id": None, "button_title": None, "media_id": None, "caption": None,
         "referral": raw.get("referral")}
    if t == "text":
        m["text"] = (raw.get("text") or {}).get("body")
    elif t == "interactive":  # respuesta a botones o listas
        it = raw.get("interactive") or {}
        reply = it.get("button_reply") or it.get("list_reply") or {}
        m["button_id"], m["button_title"] = reply.get("id"), reply.get("title")
    elif t == "button":  # botón de respuesta rápida de una plantilla
        b = raw.get("button") or {}
        m["button_id"], m["button_title"] = b.get("payload"), b.get("text")
    elif t in ("image", "document", "video", "audio", "sticker"):
        media = raw.get(t) or {}
        m["media_id"], m["caption"] = media.get("id"), media.get("caption")
    elif t == "location":
        loc = raw.get("location") or {}
        m["text"] = f"📍 Ubicación: {loc.get('latitude')}, {loc.get('longitude')}"
    return m


def inbound_display(m):
    if m.get("text"):
        return m["text"]
    if m.get("button_title"):
        return m["button_title"]
    labels = {"image": "📷 Imagen", "document": "📄 Documento", "audio": "🎤 Audio",
              "video": "🎬 Video", "sticker": "Sticker"}
    base = labels.get(m["type"], f"[{m['type']}]")
    return f"{base}: {m['caption']}" if m.get("caption") else base


def parse_webhook(payload):
    messages, statuses = [], []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for raw in value.get("messages") or []:
                messages.append(parse_message(raw, names.get(raw.get("from"))))
            statuses.extend(value.get("statuses") or [])
    return messages, statuses


def process_webhook(payload, test=False):
    messages, statuses = parse_webhook(payload)
    for st in statuses:
        _apply_status(st)
    for m in messages:
        handle_inbound(m, test=test)
    return messages


_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}


def _apply_status(st):
    msg = Message.query.filter_by(wa_message_id=st.get("id")).first()
    if not msg:
        return
    new = st.get("status")
    if _STATUS_RANK.get(new, 0) >= _STATUS_RANK.get(msg.status, 0):
        msg.status = new
    if st.get("errors"):
        e = st["errors"][0]
        details = (e.get("error_data") or {}).get("details", "")
        msg.error = f"{e.get('code')}: {e.get('title', '')} {details}".strip()
    db.session.commit()


def handle_inbound(m, test=False):
    if m["wamid"] and Message.query.filter_by(wa_message_id=m["wamid"]).first():
        return None  # Meta reintenta los webhooks: ignoramos duplicados

    contact = Contact.query.filter_by(wa_id=m["wa_id"]).first()
    if contact is None:
        contact = Contact(wa_id=m["wa_id"], name=m.get("name"), is_test=test, tags=[], data={})
        db.session.add(contact)
        db.session.flush()
    elif m.get("name") and not contact.name:
        contact.name = m["name"]

    is_first = contact.last_inbound_at is None
    if m.get("referral"):
        contact.source = "anuncio"
        contact.referral = m["referral"]

    now = utcnow()
    display = inbound_display(m)
    db.session.add(Message(contact_id=contact.id, direction="in",
                           type="button_reply" if m.get("button_id") else m["type"],
                           text=display, payload=m, wa_message_id=m["wamid"], status="received", created_at=now))
    contact.last_inbound_at = now
    contact.unread = (contact.unread or 0) + 1
    touch(contact, display)
    ScheduledMessage.query.filter_by(contact_id=contact.id, status="pending", cancel_on_reply=True) \
        .update({"status": "cancelled", "result": "El cliente respondió"}, synchronize_session=False)
    db.session.commit()

    if not contact.bot_enabled:
        return contact  # un asesor tomó la conversación
    flow, variables = select_flow(m, is_first)
    if flow:
        run_flow_async(contact.id, flow.id, variables, reply_to=m["wamid"])
    return contact


def select_flow(m, is_first):
    """Orden: anuncio > botón > primer mensaje > archivo > palabras clave/regex (por prioridad) > fallback."""
    flows = Flow.query.filter_by(active=True).order_by(Flow.priority.desc(), Flow.id).all()

    def trig(f):
        return f.triggers or {}

    def by_event(event):
        return next((f for f in flows if event in trig(f).get("events", [])), None)

    if m.get("referral"):
        ad_id = str(m["referral"].get("source_id") or "")
        ad_flows = [f for f in flows if "ad_click" in trig(f).get("events", [])]
        specific = next((f for f in ad_flows if ad_id and ad_id in [str(x) for x in trig(f).get("ad_ids", [])]), None)
        generic = next((f for f in ad_flows if not trig(f).get("ad_ids")), None)
        if specific or generic:
            return specific or generic, {}

    if m.get("button_id"):
        bid = m["button_id"]
        if bid.startswith("flow:"):  # botón creado en el editor visual: abre ese flujo directo
            f = next((f for f in flows if str(f.id) == bid[5:]), None)
        else:
            f = next((f for f in flows if bid in trig(f).get("buttons", [])), None)
        if f:
            return f, {}

    if is_first:
        f = by_event("first_message")
        if f:
            return f, {}

    if m.get("media_id"):
        f = by_event("media")
        if f:
            return f, {}

    text = m.get("text") or m.get("button_title") or ""
    if text:
        norm = normalize(text)
        for f in flows:
            for rx in trig(f).get("regex", []):
                try:
                    found = re.search(rx, text, re.IGNORECASE)
                except re.error:
                    log.warning("Regex inválida en el flujo %s: %s", f.name, rx)
                    continue
                if found:
                    return f, {k: v.strip().upper() for k, v in found.groupdict().items() if v}
            if any(keyword_match(norm, kw) for kw in trig(f).get("keywords", [])):
                return f, {}

    return by_event("fallback"), {}


# ---------------------------------------------------------------------- ejecución de flujos
def run_flow_async(contact_id, flow_id, variables=None, reply_to=None):
    """Responde a Meta al instante y envía los globos en segundo plano (con sus pausas)."""
    app = current_app._get_current_object()
    threading.Thread(target=_run_flow_thread, args=(app, contact_id, flow_id, variables or {}, reply_to),
                     daemon=True).start()


def _run_flow_thread(app, contact_id, flow_id, variables, reply_to):
    with app.app_context():
        try:
            run_flow(contact_id, flow_id, variables, reply_to)
        except Exception:
            log.exception("Error ejecutando el flujo %s para el contacto %s", flow_id, contact_id)
            db.session.rollback()
        finally:
            db.session.remove()


def run_flow(contact_id, flow_id, variables=None, reply_to=None):
    with contact_lock(contact_id):
        contact = db.session.get(Contact, contact_id)
        flow = db.session.get(Flow, flow_id)
        if not contact or not flow:
            return
        if variables:
            contact.data = {**(contact.data or {}), **variables}
        if flow.followups:
            schedule_followups(contact, flow)
        db.session.commit()
        if reply_to and not contact.is_test:
            wa_client().mark_read(reply_to, typing=True)
        execute_steps(contact, flow.steps or [], flow.name)


def schedule_followups(contact, flow):
    cancel_followups(contact.id, f"Reemplazado por el flujo «{flow.name}»")
    now = utcnow()
    for i, fu in enumerate(flow.followups):
        db.session.add(ScheduledMessage(
            contact_id=contact.id, flow_name=flow.name,
            label=fu.get("label") or f"Seguimiento {i + 1}",
            run_at=now + timedelta(minutes=float(fu.get("delay_minutes", 60))),
            steps=fu.get("steps") or [], cancel_on_reply=bool(fu.get("cancel_on_reply", False)),
        ))


def cancel_followups(contact_id, reason):
    ScheduledMessage.query.filter_by(contact_id=contact_id, status="pending") \
        .update({"status": "cancelled", "result": reason, "done_at": utcnow()}, synchronize_session=False)


def set_stage(contact, stage):
    if stage not in STAGES:
        return
    contact.stage = stage
    if stage in CLOSED_STAGES:
        cancel_followups(contact.id, f"El contacto pasó a la etapa «{stage}»")


def add_note(contact, text):
    db.session.add(Message(contact_id=contact.id, direction="system", type="note", text=text, status="note"))


def _apply_action(contact, step):
    t = step["type"]
    if t == "set_stage":
        set_stage(contact, step.get("stage"))
    elif t == "add_tag":
        tags = list(contact.tags or [])
        if step.get("tag") and step["tag"] not in tags:
            contact.tags = tags + [step["tag"]]
    elif t == "remove_tag":
        contact.tags = [x for x in (contact.tags or []) if x != step.get("tag")]
    elif t == "set_var":
        value = render(str(step.get("value", "")), contact_vars(contact))
        contact.data = {**(contact.data or {}), step["key"]: value}
    elif t == "pause_bot":
        contact.bot_enabled = False
    elif t == "resume_bot":
        contact.bot_enabled = True
    elif t == "cancel_followups":
        cancel_followups(contact.id, "Cancelado por el flujo")
    elif t == "note":
        add_note(contact, render(step.get("text", ""), contact_vars(contact)))


def execute_steps(contact, steps, origin):
    for step in steps:
        t = (step or {}).get("type")
        try:
            if t == "delay":
                seconds = max(0.0, min(float(step.get("seconds", 1)), MAX_DELAY_SECONDS))
                _typing[contact.id] = time.time() + seconds
                time.sleep(seconds)
            elif t in ACTION_TYPES:
                _apply_action(contact, step)
                db.session.commit()
            elif t in MESSAGE_TYPES:
                send_step(contact, step, origin)
            else:
                log.warning("Paso desconocido en %s: %s", origin, step)
        except Exception:
            log.exception("Falló un paso de %s", origin)
            db.session.rollback()
    _typing.pop(contact.id, None)


def send_step(contact, step, origin):
    step = render(step, contact_vars(contact))
    t = step["type"]
    msg = Message(contact_id=contact.id, direction="out", type=t, text=step_display(step), flow_name=origin)

    if t != "template" and not contact.window_open():
        msg.status = "skipped"
        msg.error = "Ventana de 24 h cerrada: fuera de ella Meta solo permite plantillas aprobadas."
        msg.payload = {"step": step}
    else:
        try:
            api_payload = wa_client().build_payload(contact.wa_id, step)
            msg.payload = {"step": step, "api": api_payload}
            wamid = wa_client().send(api_payload, simulate=contact.is_test)
            msg.wa_message_id = wamid
            msg.status = "simulated" if wamid.startswith("sim.") else "sent"
        except (WhatsAppError, ValueError, KeyError) as e:
            msg.payload = msg.payload or {"step": step}
            msg.status = "failed"
            msg.error = str(e)

    touch(contact, msg.text)
    db.session.add(msg)
    db.session.commit()
    return msg
