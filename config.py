"""Configuración central. Todo se lee de variables de entorno (archivo .env en local)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "si", "sí")


def database_url():
    """Sin DATABASE_URL usamos SQLite local; con la URL de Supabase usamos Postgres."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + os.path.join(BASE_DIR, "crm_local.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def engine_options(url):
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False, "timeout": 15}}
    return {
        "pool_pre_ping": True,  # Supabase cierra conexiones inactivas
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 5,
        # Sin prepared statements: compatible con el pooler de Supabase (puertos 5432 y 6543)
        "connect_args": {"prepare_threshold": None},
    }


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-cambia-esta-clave")
    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_ENGINE_OPTIONS = engine_options(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Acceso al panel
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # WhatsApp Cloud API
    WA_MODE = os.getenv("WA_MODE", "simulator").strip().lower()  # simulator | cloud
    WA_TOKEN = os.getenv("WA_TOKEN", "").strip()
    WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "").strip()
    WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "mi_token_de_verificacion").strip()
    WA_APP_SECRET = os.getenv("WA_APP_SECRET", "").strip()
    WA_API_VERSION = os.getenv("WA_API_VERSION", "v23.0").strip()

    # URL pública (Render) para convertir rutas /static/... en links que Meta pueda descargar
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Filtra tu Placa")

    # Biblioteca de imágenes: con Supabase Storage las imágenes sobreviven a los reinicios de Render.
    # Sin estas variables se guardan en crm/static/uploads (válido solo en local).
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "media").strip()
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024

    # Seguimientos programados
    RUN_SCHEDULER = _bool("RUN_SCHEDULER", True)
    SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "15"))
    CRON_TOKEN = os.getenv("CRON_TOKEN", "").strip()
