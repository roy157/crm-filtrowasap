"""Páginas del panel (requieren contraseña)."""
import hmac
from functools import wraps

from flask import (Blueprint, Response, current_app, redirect, render_template, request, session,
                   url_for)

from .whatsapp import WhatsAppError

bp = Blueprint("panel", __name__)

SIM_RECEIPT = "https://placehold.co/400x700/742284/ffffff/png?text=Yape+S/5+-+Pago+exitoso"


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("panel.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), current_app.config["ADMIN_PASSWORD"]):
            session.permanent = True
            session["auth"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("panel.inbox"))
        error = "Contraseña incorrecta"
    default_pw = current_app.config["ADMIN_PASSWORD"] == "admin123"
    return render_template("login.html", error=error, default_pw=default_pw)


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("panel.login"))


@bp.get("/")
@login_required
def index():
    return redirect(url_for("panel.inbox"))


@bp.get("/panel")
@login_required
def inbox():
    return render_template("panel.html", page="panel")


@bp.get("/simulador")
@login_required
def simulator():
    return render_template("simulator.html", page="simulador")


@bp.get("/flujos")
@login_required
def flows():
    return render_template("flows.html", page="flujos")


@bp.get("/imagenes")
@login_required
def images():
    return render_template("media.html", page="imagenes")


@bp.get("/resumen")
@login_required
def summary():
    return render_template("summary.html", page="resumen")


@bp.get("/media/<media_id>")
@login_required
def media(media_id):
    """Muestra en el panel las imágenes que envían los clientes (Meta exige descargarlas con el token)."""
    if media_id.startswith("sim-"):
        return redirect(SIM_RECEIPT)
    try:
        content, mime = current_app.extensions["whatsapp"].get_media(media_id)
    except WhatsAppError as e:
        return f"No se pudo descargar el archivo: {e}", 502
    return Response(content, mimetype=mime, headers={"Cache-Control": "private, max-age=86400"})
