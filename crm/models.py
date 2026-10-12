from datetime import datetime, timedelta, timezone

from .extensions import db

STAGES = ["nuevo", "interesado", "pago_pendiente", "cliente", "perdido"]
# En estas etapas ya no se envían seguimientos automáticos
CLOSED_STAGES = {"pago_pendiente", "cliente", "perdido"}
WINDOW = timedelta(hours=24)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)
    wa_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120))
    stage = db.Column(db.String(32), nullable=False, default="nuevo")
    tags = db.Column(db.JSON, nullable=False, default=list)
    data = db.Column(db.JSON, nullable=False, default=dict)  # variables: precio, placa...
    notes = db.Column(db.Text, nullable=False, default="")
    bot_enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_test = db.Column(db.Boolean, nullable=False, default=False)  # creado por el simulador
    source = db.Column(db.String(32), nullable=False, default="organico")
    referral = db.Column(db.JSON)  # datos del anuncio de clic a WhatsApp
    unread = db.Column(db.Integer, nullable=False, default=0)
    last_preview = db.Column(db.String(160), nullable=False, default="")
    last_inbound_at = db.Column(db.DateTime)
    last_message_at = db.Column(db.DateTime, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    messages = db.relationship("Message", backref="contact", cascade="all, delete-orphan", passive_deletes=True)
    scheduled = db.relationship("ScheduledMessage", backref="contact", cascade="all, delete-orphan", passive_deletes=True)

    def window_open(self):
        """Ventana de atención de 24 h: solo dentro de ella se permiten mensajes libres."""
        return bool(self.last_inbound_at) and utcnow() - self.last_inbound_at < WINDOW

    def to_dict(self):
        return {
            "id": self.id,
            "wa_id": self.wa_id,
            "name": self.name,
            "display_name": self.name or f"+{self.wa_id}",
            "stage": self.stage,
            "tags": self.tags or [],
            "data": self.data or {},
            "notes": self.notes or "",
            "bot_enabled": self.bot_enabled,
            "is_test": self.is_test,
            "source": self.source,
            "referral": self.referral,
            "unread": self.unread or 0,
            "last_preview": self.last_preview,
            "last_inbound_at": iso(self.last_inbound_at),
            "last_message_at": iso(self.last_message_at),
            "created_at": iso(self.created_at),
            "window_open": self.window_open(),
            "window_expires_at": iso(self.last_inbound_at + WINDOW) if self.last_inbound_at else None,
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = db.Column(db.String(8), nullable=False)  # in | out | system
    type = db.Column(db.String(32), nullable=False, default="text")
    text = db.Column(db.Text, nullable=False, default="")
    payload = db.Column(db.JSON)
    wa_message_id = db.Column(db.String(128), unique=True)
    status = db.Column(db.String(16), nullable=False, default="received")
    error = db.Column(db.Text)
    flow_name = db.Column(db.String(160))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self):
        p = self.payload or {}
        step = p.get("step") or {}
        media_url = None
        if self.direction == "in":
            if p.get("media_id"):
                media_url = f"/media/{p['media_id']}"
            body = p.get("text") or p.get("button_title") or p.get("caption") or ""
            if not body and not media_url:
                body = self.text
        else:
            if self.type in ("image", "document"):
                media_url = step.get("url")
            if self.type == "template":
                body = step.get("preview") or ""
            elif self.type in ("image", "document"):
                body = step.get("caption") or ""
            else:
                body = step.get("text") or self.text
        return {
            "id": self.id,
            "direction": self.direction,
            "type": self.type,
            "text": self.text,
            "body": body,
            "step": step,
            "api": p.get("api"),
            "media_url": media_url,
            "status": self.status,
            "error": self.error,
            "flow_name": self.flow_name,
            "created_at": iso(self.created_at),
        }


class Flow(db.Model):
    __tablename__ = "flows"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    priority = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)
    triggers = db.Column(db.JSON, nullable=False, default=dict)
    steps = db.Column(db.JSON, nullable=False, default=list)
    followups = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "active": self.active,
            "triggers": self.triggers or {},
            "steps": self.steps or [],
            "followups": self.followups or [],
            "updated_at": iso(self.updated_at),
        }


class MediaAsset(db.Model):
    __tablename__ = "media_assets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(600), nullable=False)
    storage = db.Column(db.String(16), nullable=False, default="local")  # local | supabase
    path = db.Column(db.String(300), nullable=False)
    mime = db.Column(db.String(80), nullable=False)
    size = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "url": self.url, "storage": self.storage,
                "mime": self.mime, "size": self.size, "created_at": iso(self.created_at)}


class ScheduledMessage(db.Model):
    __tablename__ = "scheduled_messages"

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_name = db.Column(db.String(120), nullable=False, default="")
    label = db.Column(db.String(120), nullable=False, default="")
    run_at = db.Column(db.DateTime, nullable=False, index=True)
    steps = db.Column(db.JSON, nullable=False, default=list)
    cancel_on_reply = db.Column(db.Boolean, nullable=False, default=False)
    # pending | processing | sent | cancelled | skipped | error
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    result = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    done_at = db.Column(db.DateTime)

    def to_dict(self):
        preview = next((s.get("text") or s.get("preview") or s.get("caption")
                        for s in (self.steps or []) if s.get("text") or s.get("preview") or s.get("caption")), "")
        return {
            "id": self.id,
            "flow_name": self.flow_name,
            "label": self.label,
            "run_at": iso(self.run_at),
            "status": self.status,
            "result": self.result,
            "cancel_on_reply": self.cancel_on_reply,
            "preview": preview,
        }
