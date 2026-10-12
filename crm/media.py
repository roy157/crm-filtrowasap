"""Biblioteca de imágenes: guarda en Supabase Storage (producción) o en static/uploads (local)."""
import logging
import os
import uuid

import requests
from flask import current_app

from .extensions import db
from .models import MediaAsset

log = logging.getLogger(__name__)

# Formatos que acepta WhatsApp y sus límites
ALLOWED = {
    "image/jpeg": (".jpg", 5 * 1024 * 1024),
    "image/png": (".png", 5 * 1024 * 1024),
    "application/pdf": (".pdf", 16 * 1024 * 1024),
}
_bucket_ready = False


def _supabase():
    cfg = current_app.config
    if cfg["SUPABASE_URL"] and cfg["SUPABASE_SERVICE_KEY"]:
        return cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_KEY"], cfg["SUPABASE_BUCKET"]
    return None


def _headers(key, extra=None):
    h = {"apikey": key}
    if key.startswith("eyJ"):  # llave service_role clásica (JWT)
        h["Authorization"] = f"Bearer {key}"
    return {**h, **(extra or {})}


def _ensure_bucket(base, key, bucket):
    global _bucket_ready
    if _bucket_ready:
        return
    r = requests.post(f"{base}/storage/v1/bucket", headers=_headers(key),
                      json={"id": bucket, "name": bucket, "public": True}, timeout=15)
    if r.status_code >= 400 and "already exists" not in r.text.lower() and r.status_code != 409:
        log.warning("No se pudo crear el bucket %s: %s", bucket, r.text)
    _bucket_ready = True


def storage_mode():
    return "supabase" if _supabase() else "local"


def save_upload(file, name=None):
    data = file.read()
    mime = (file.mimetype or "").lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in ALLOWED:
        raise ValueError("WhatsApp solo acepta imágenes JPG o PNG (y PDF para documentos).")
    ext, limit = ALLOWED[mime]
    if len(data) > limit:
        raise ValueError(f"El archivo pesa {len(data) / 1048576:.1f} MB; el máximo para este tipo es {limit // 1048576} MB.")
    if not data:
        raise ValueError("El archivo está vacío.")

    key = f"{uuid.uuid4().hex}{ext}"
    sb = _supabase()
    if sb:
        base, skey, bucket = sb
        _ensure_bucket(base, skey, bucket)
        r = requests.post(f"{base}/storage/v1/object/{bucket}/{key}", data=data, timeout=60,
                          headers=_headers(skey, {"Content-Type": mime, "x-upsert": "true"}))
        if r.status_code >= 400:
            raise ValueError(f"Supabase Storage rechazó el archivo: {r.text[:200]}")
        url, storage = f"{base}/storage/v1/object/public/{bucket}/{key}", "supabase"
    else:
        folder = os.path.join(current_app.static_folder, "uploads")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, key), "wb") as fh:
            fh.write(data)
        url, storage = f"/static/uploads/{key}", "local"

    asset = MediaAsset(name=(name or file.filename or key)[:200], url=url, storage=storage,
                       path=key, mime=mime, size=len(data))
    db.session.add(asset)
    db.session.commit()
    return asset


def delete_asset(asset):
    if asset.storage == "supabase" and _supabase():
        base, skey, bucket = _supabase()
        try:
            requests.delete(f"{base}/storage/v1/object/{bucket}", headers=_headers(skey),
                            json={"prefixes": [asset.path]}, timeout=15)
        except requests.RequestException:
            log.warning("No se pudo borrar %s de Supabase", asset.path)
    elif asset.storage == "local":
        path = os.path.join(current_app.static_folder, "uploads", asset.path)
        if os.path.isfile(path):
            os.remove(path)
    db.session.delete(asset)
    db.session.commit()
