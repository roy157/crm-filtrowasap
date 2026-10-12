import logging

from flask import Flask
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

from .extensions import db
from .whatsapp import WhatsAppClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TABLES = ("contacts", "messages", "flows", "scheduled_messages", "media_assets")


def _secure_supabase():
    """Supabase expone el esquema public por su API REST. Activar RLS sin políticas
    bloquea ese acceso; nuestra app entra como 'postgres' y no se ve afectada."""
    if db.engine.dialect.name != "postgresql":
        return
    with db.engine.begin() as conn:
        for t in TABLES:
            conn.execute(text(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY'))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Render usa proxy HTTPS

    db.init_app(app)
    app.extensions["whatsapp"] = WhatsAppClient(app.config)

    from .api import bp as api_bp
    from .panel import bp as panel_bp
    from .webhook import bp as webhook_bp
    app.register_blueprint(webhook_bp)
    app.register_blueprint(panel_bp)
    app.register_blueprint(api_bp)

    from .seed import seed_flows
    with app.app_context():
        db.create_all()
        try:
            _secure_supabase()
        except Exception:
            app.logger.exception("No se pudo activar RLS en Supabase")
        seed_flows()

    @app.context_processor
    def inject_globals():
        return {"wa_mode": app.config["WA_MODE"], "business_name": app.config["BUSINESS_NAME"]}

    if app.config["WA_MODE"] == "cloud" and not (app.config["WA_TOKEN"] and app.config["WA_PHONE_NUMBER_ID"]):
        app.logger.warning("WA_MODE=cloud pero faltan WA_TOKEN / WA_PHONE_NUMBER_ID")
    if app.config["WA_MODE"] == "cloud" and not app.config["PUBLIC_BASE_URL"]:
        app.logger.warning("Falta PUBLIC_BASE_URL: Meta no podrá descargar las imágenes de tu biblioteca local")
    if app.config["ADMIN_PASSWORD"] == "admin123":
        app.logger.warning("Usando la contraseña por defecto (admin123). Cámbiala con ADMIN_PASSWORD.")

    if app.config["RUN_SCHEDULER"]:
        from .scheduler import start_scheduler
        start_scheduler(app)
    return app
