"""Flujos de ejemplo. Se cargan solo si la tabla de flujos está vacía.
Edítalos desde el panel (/flujos) o aquí, y usa "Restaurar ejemplos" para recargarlos."""
from .extensions import db
from .models import Flow

IMG = "https://placehold.co"

BTN_COMPRAR = {"id": "btn_comprar", "title": "✅ Quiero mi reporte"}
BTN_EJEMPLO = {"id": "btn_ejemplo", "title": "📄 Ver ejemplo"}
BTN_ASESOR = {"id": "btn_asesor", "title": "🙋 Hablar con asesor"}
BTN_PRECIO = {"id": "btn_precio", "title": "💰 Ver precio"}
BTN_STOP = {"id": "btn_stop", "title": "No, gracias"}

MENU_LIST = {
    "type": "list",
    "text": "¿En qué te ayudo, {nombre}? 👇",
    "button": "Ver opciones",
    "sections": [{
        "title": "Opciones",
        "rows": [
            {"id": "btn_precio", "title": "💰 Precio y promo", "description": "Cuánto cuesta el reporte"},
            {"id": "btn_ejemplo", "title": "📄 Ver un ejemplo", "description": "Mira cómo luce el reporte"},
            {"id": "btn_comprar", "title": "✅ Comprar reporte", "description": "Pide tu reporte ahora"},
            {"id": "btn_asesor", "title": "🙋 Hablar con asesor", "description": "Te atiende una persona"},
        ],
    }],
}

DEFAULT_FLOWS = [
    {
        "name": "Bienvenida (anuncio)",
        "description": "Se activa cuando alguien hace clic en tu anuncio o escribe por primera vez. "
                       "Envía varios globos con imagen e inicia la secuencia de bajada de precio.",
        "priority": 100,
        "triggers": {"events": ["ad_click", "first_message"]},
        "steps": [
            {"type": "set_var", "key": "precio", "value": "10"},
            {"type": "text", "text": "¡Hola {nombre}! 👋 Gracias por escribir a *Filtra tu Placa* 🚗"},
            {"type": "delay", "seconds": 1.5},
            {"type": "image", "url": f"{IMG}/800x450/0b8457/ffffff/png?text=Reporte+vehicular+completo",
             "caption": "Así luce tu reporte 👆"},
            {"type": "delay", "seconds": 2},
            {"type": "text", "text": "Con solo tu *número de placa* te enviamos en minutos:\n\n"
                                     "✅ Papeletas y multas\n✅ SOAT vigente\n✅ Revisión técnica\n"
                                     "✅ Historial de propietarios\n\nPrecio regular: *S/ {precio}*"},
            {"type": "delay", "seconds": 1.5},
            {"type": "buttons", "text": "¿Qué te gustaría hacer?", "buttons": [BTN_COMPRAR, BTN_EJEMPLO, BTN_ASESOR]},
        ],
        "followups": [
            {
                "delay_minutes": 30, "label": "Promo S/5", "cancel_on_reply": False,
                "steps": [
                    {"type": "set_var", "key": "precio", "value": "5"},
                    {"type": "text", "text": "🔥 {nombre}, *solo por hoy* tu reporte baja de ~S/10~ a *S/5*"},
                    {"type": "delay", "seconds": 1},
                    {"type": "buttons", "text": "¿Lo aprovechas? Solo envíame tu placa 🚗",
                     "buttons": [{"id": "btn_comprar", "title": "✅ Sí, lo quiero"}, BTN_STOP]},
                ],
            },
            {
                "delay_minutes": 180, "label": "Última oferta S/3", "cancel_on_reply": False,
                "steps": [
                    {"type": "set_var", "key": "precio", "value": "3"},
                    {"type": "image", "url": f"{IMG}/800x450/d93025/ffffff/png?text=ULTIMA+OPORTUNIDAD+S/3",
                     "caption": "⏰ *Última oportunidad*"},
                    {"type": "delay", "seconds": 1},
                    {"type": "text", "text": "{nombre}, te lo dejo en *S/3* 😱 solo por las próximas horas.\n\n"
                                             "Responde con tu placa (ej: *ABC-123*) y te lo preparo."},
                ],
            },
            {
                "delay_minutes": 1500, "label": "Plantilla (fuera de 24 h)", "cancel_on_reply": False,
                "steps": [
                    {"type": "template", "name": "recordatorio_oferta", "language": "es",
                     "params": ["{nombre}", "S/3"],
                     "preview": "Hola {nombre}, tu descuento de S/3 para el reporte vehicular sigue disponible hoy. "
                                "¿Lo quieres? Responde QUIERO."},
                ],
            },
        ],
    },
    {
        "name": "No interesado",
        "description": "Respeta al cliente que no quiere más mensajes (cuida la calidad de tu número).",
        "priority": 110,
        "triggers": {"keywords": ["no me interesa", "no quiero", "no gracias", "stop", "baja", "ya no"],
                     "buttons": ["btn_stop"]},
        "steps": [
            {"type": "text", "text": "Entendido 👍 No te enviaremos más mensajes.\n"
                                     "Si luego necesitas tu reporte, escríbenos *hola*."},
            {"type": "set_stage", "stage": "perdido"},
        ],
        "followups": [],
    },
    {
        "name": "Comprobante de pago",
        "description": "Cuando el cliente envía una imagen (captura de Yape/Plin).",
        "priority": 90,
        "triggers": {"events": ["media"]},
        "steps": [
            {"type": "text", "text": "📩 ¡Recibimos tu comprobante, {nombre}!\n"
                                     "Un asesor lo valida y te enviamos tu reporte en unos minutos ⏱️"},
            {"type": "set_stage", "stage": "pago_pendiente"},
            {"type": "add_tag", "tag": "pago_por_validar"},
            {"type": "note", "text": "💰 Comprobante recibido. Validar pago de S/ {precio} y enviar reporte de la placa {placa}."},
            {"type": "pause_bot"},
        ],
        "followups": [],
    },
    {
        "name": "Hablar con asesor",
        "description": "Pausa el bot y avisa en el panel para que una persona responda.",
        "priority": 80,
        "triggers": {"keywords": ["asesor", "humano", "persona", "hablar con alguien", "ayuda"],
                     "buttons": ["btn_asesor"]},
        "steps": [
            {"type": "text", "text": "Listo 🙋 Un asesor te escribirá en breve.\nHorario: lun-sáb de 9 a. m. a 7 p. m."},
            {"type": "add_tag", "tag": "requiere_asesor"},
            {"type": "note", "text": "🙋 El cliente pidió hablar con un asesor. El bot quedó pausado."},
            {"type": "pause_bot"},
        ],
        "followups": [],
    },
    {
        "name": "Placa recibida",
        "description": "Detecta una placa peruana (ABC-123 / A1B-234) y pide el pago.",
        "priority": 70,
        "triggers": {"regex": [r"\b(?P<placa>[A-Za-z][A-Za-z0-9]{2}-?\d{3})\b"]},
        "steps": [
            {"type": "set_stage", "stage": "interesado"},
            {"type": "text", "text": "Perfecto 🙌 Registré la placa *{placa}* 🚗"},
            {"type": "delay", "seconds": 1.5},
            {"type": "text", "text": "Para generar tu reporte yapea o plinea *S/ {precio}* al número *999 888 777* "
                                     "(Filtra tu Placa) y envíame la *captura del pago* aquí 📲"},
        ],
        "followups": [],
    },
    {
        "name": "Comprar",
        "description": "El cliente quiere comprar: pedimos la placa.",
        "priority": 60,
        "triggers": {"keywords": ["comprar", "quiero", "lo quiero", "pagar", "yape", "plin", "reporte"],
                     "buttons": ["btn_comprar"]},
        "steps": [
            {"type": "set_stage", "stage": "interesado"},
            {"type": "text", "text": "¡Genial! 🎉 Tu reporte cuesta *S/ {precio}*."},
            {"type": "delay", "seconds": 1},
            {"type": "text", "text": "Envíame tu *número de placa* (ej: *ABC-123*) 🚗"},
        ],
        "followups": [],
    },
    {
        "name": "Precio",
        "description": "Preguntas por precio o promociones.",
        "priority": 40,
        "triggers": {"keywords": ["precio", "costo", "cuanto", "cuesta", "vale", "tarifa", "promo", "oferta"],
                     "buttons": ["btn_precio"]},
        "steps": [
            {"type": "text", "text": "💰 El reporte vehicular completo cuesta *S/ {precio}*.\n\n"
                                     "Incluye papeletas, SOAT, revisión técnica e historial de propietarios."},
            {"type": "delay", "seconds": 1},
            {"type": "buttons", "text": "¿Te lo preparo?", "buttons": [BTN_COMPRAR, BTN_EJEMPLO]},
        ],
        "followups": [],
    },
    {
        "name": "Ver ejemplo",
        "description": "Envía una imagen de un reporte de muestra.",
        "priority": 30,
        "triggers": {"keywords": ["ejemplo", "muestra", "modelo"], "buttons": ["btn_ejemplo"]},
        "steps": [
            {"type": "text", "text": "Te muestro un reporte de ejemplo 👇"},
            {"type": "delay", "seconds": 1},
            {"type": "image", "url": f"{IMG}/700x900/ffffff/0b8457/png?text=Ejemplo+de+reporte",
             "caption": "Placa ABC-123 · Reporte de ejemplo"},
            {"type": "delay", "seconds": 1},
            {"type": "buttons", "text": "¿Quieres el tuyo?", "buttons": [BTN_COMPRAR, BTN_PRECIO]},
        ],
        "followups": [],
    },
    {
        "name": "Menú",
        "description": "Saludo o pedido de información: muestra una lista de opciones.",
        "priority": 20,
        "triggers": {"keywords": ["hola", "buenas", "buenos dias", "buenas tardes", "menu", "info", "informacion", "inicio"]},
        "steps": [MENU_LIST],
        "followups": [],
    },
    {
        "name": "Gracias",
        "description": "Agradecimientos.",
        "priority": 15,
        "triggers": {"keywords": ["gracias", "genial", "excelente", "chevere"]},
        "steps": [{"type": "text", "text": "¡A ti, {nombre}! 😊 Aquí estamos para lo que necesites."}],
        "followups": [],
    },
    {
        "name": "No entendí (fallback)",
        "description": "Cuando ningún otro flujo coincide.",
        "priority": 0,
        "triggers": {"events": ["fallback"]},
        "steps": [
            {"type": "text", "text": "Mmm, no logré entenderte 🤔"},
            {"type": "delay", "seconds": 1},
            MENU_LIST,
        ],
        "followups": [],
    },
]


def seed_flows(force=False):
    if force:
        Flow.query.delete()
        db.session.commit()
    if Flow.query.count():
        return 0
    for f in DEFAULT_FLOWS:
        db.session.add(Flow(**f))
    db.session.commit()
    return len(DEFAULT_FLOWS)
