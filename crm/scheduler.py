"""Envía los seguimientos programados (ej. "bajó a S/5", "última oferta S/3").

Corre en un hilo dentro del servidor. En Render plan free, UptimeRobot llama a /cron/tick
cada 5 minutos: eso evita que el servidor se duerma y además procesa los pendientes.
"""
import logging
import threading
import time

from .engine import contact_lock, execute_steps
from .extensions import db
from .models import CLOSED_STAGES, ScheduledMessage, utcnow

log = logging.getLogger(__name__)
_guard = threading.Lock()


def process_due(limit=25):
    ids = [row.id for row in ScheduledMessage.query
           .filter(ScheduledMessage.status == "pending", ScheduledMessage.run_at <= utcnow())
           .order_by(ScheduledMessage.run_at).limit(limit)]
    done = 0
    for sid in ids:
        # Reclamo atómico: si hay dos procesos, solo uno envía cada seguimiento
        claimed = ScheduledMessage.query.filter_by(id=sid, status="pending") \
            .update({"status": "processing"}, synchronize_session=False)
        db.session.commit()
        if not claimed:
            continue

        sm = db.session.get(ScheduledMessage, sid)
        contact = sm.contact
        reason = None
        if not contact.bot_enabled:
            reason = "Bot pausado para este contacto"
        elif contact.stage in CLOSED_STAGES:
            reason = f"El contacto está en la etapa «{contact.stage}»"
        if reason:
            sm.status, sm.result, sm.done_at = "skipped", reason, utcnow()
            db.session.commit()
            continue

        try:
            with contact_lock(contact.id):
                execute_steps(contact, sm.steps or [], f"{sm.flow_name} · {sm.label}")
            sm.status, sm.result = "sent", "Enviado"
        except Exception as e:  # noqa: BLE001
            log.exception("Error en el seguimiento %s", sid)
            db.session.rollback()
            sm = db.session.get(ScheduledMessage, sid)
            sm.status, sm.result = "error", str(e)[:500]
        sm.done_at = utcnow()
        db.session.commit()
        done += 1
    return done


def run_once(app, use_guard=True):
    if use_guard and not _guard.acquire(blocking=False):
        return 0
    try:
        with app.app_context():
            try:
                return process_due()
            except Exception:
                log.exception("Error procesando seguimientos")
                db.session.rollback()
                return 0
            finally:
                db.session.remove()
    finally:
        if use_guard:
            _guard.release()


def trigger_async(app, use_guard=True):
    threading.Thread(target=run_once, args=(app, use_guard), daemon=True).start()


def start_scheduler(app):
    interval = app.config["SCHEDULER_INTERVAL"]

    def loop():
        while True:
            run_once(app)
            time.sleep(interval)

    threading.Thread(target=loop, name="seguimientos", daemon=True).start()
    log.info("Programador de seguimientos activo (cada %ss)", interval)
