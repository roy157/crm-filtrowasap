# CRM WhatsApp · Filtra tu Placa

Un bot que responde en WhatsApp con varios globos seguidos (texto, imagen, botones y listas) según lo que escriba el cliente. También programa seguimientos automáticos, como la bajada de precio *S/10 → S/5 → S/3*. Incluye un panel CRM donde un asesor puede tomar el chat.

- **Backend:** Flask, con la WhatsApp Cloud API de Meta.
- **Base de datos:** SQLite en local y Supabase (Postgres) en producción.
- **Despliegue:** Render, con UptimeRobot para que el servidor no se duerma.
- **Simulador:** permite probar todo sin tener la API todavía.

---

## 1. Ejecutarlo en tu PC (sin API)

```powershell
cd D:\FILTRATUPLACA\CRM
..\venv\Scripts\activate          # o crea uno: python -m venv venv
pip install -r requirements.txt
copy .env.example .env            # opcional: sin .env funciona con valores por defecto
python app.py
```

Abre <http://127.0.0.1:5000>. La contraseña por defecto es `admin123`.

| Página | Para qué sirve |
|---|---|
| **📊 Resumen** | Muestra los números clave, el embudo por etapa, los flujos más usados y los **resultados de cada anuncio** (cuántos llegaron, cuántos pagaron y la conversión). |
| **💬 Bandeja** | Es el CRM: chats, etapas, notas, etiquetas, seguimientos, pausar el bot y responder a mano. |
| **🤖 Flujos** | Es el **editor visual** de las respuestas automáticas. Armas tarjetas de texto, imagen, botones, listas y esperas, y ves una vista previa en un teléfono. El JSON queda solo como modo avanzado. |
| **🖼️ Imágenes** | Contiene la biblioteca de fotos y el **diseñador de promociones**, que arma la imagen con el precio tachado y te permite descargarla para tu anuncio o usarla en un flujo. |
| **📱 Simulador** | Aquí tú eres el cliente: un teléfono falso en el que escribes y ves cómo responde el bot. |

### Prueba guiada en el simulador

1. Pulsa **📣 Simular clic en anuncio**. Llegan 4 globos: saludo, imagen, beneficios y botones. A la derecha aparecen 3 seguimientos programados.
2. Toca **💰 Ver precio** o escribe *cuánto cuesta*. El bot responde *S/ 10*.
3. Pulsa **⏩ Adelantar el siguiente**. Llega *"🔥 solo por hoy baja a S/5"* y la variable `precio` pasa a 5.
4. Vuelve a preguntar el precio. Ahora el bot dice *S/ 5*.
5. Escribe una placa, por ejemplo **ABC-123**. El bot la guarda y te pide el pago.
6. Pulsa **📷 Enviar captura de pago**. La etapa pasa a *Pago pendiente*, el bot se pausa y se cancelan los seguimientos.
7. Abre **/panel**. Ahí ves el chat, las notas internas y puedes responder como asesor.
8. Pulsa **🕐 Cerrar ventana 24 h**. Desde ese momento los mensajes normales se marcan como ⛔ y solo salen las plantillas, igual que hace Meta.

Si haces clic en cualquier globo del bot, verás el JSON exacto que se envía a la Cloud API. Al enviar un mensaje como cliente, verás el webhook que mandaría Meta.

### Probar el webhook "real" sin Meta

Con el servidor encendido, en otra terminal:

```powershell
python scripts/probar_webhook.py verificar
python scripts/probar_webhook.py anuncio
python scripts/probar_webhook.py texto "¿cuánto cuesta?"
python scripts/probar_webhook.py boton btn_comprar "Quiero mi reporte"
```

---

## 2. Cómo funciona

```
Cliente ── WhatsApp ── Meta ──POST /webhook──► Flask
                                                 ├─ guarda el mensaje (contacts / messages)
                                                 ├─ elige UN flujo (anuncio > botón > 1er mensaje >
                                                 │   imagen > regex/palabras por prioridad > fallback)
                                                 ├─ envía los globos con pausas (en segundo plano)
                                                 └─ programa seguimientos (scheduled_messages)
Programador (cada 15 s) + /cron/tick (UptimeRobot) ──► envía los seguimientos vencidos
```

**Flujo.** Un flujo tiene tres partes:

- **Disparadores:** `keywords`, `regex`, `buttons`, `events` o `ad_ids`.
- **Pasos:** los globos y acciones que se ejecutan en orden.
- **Seguimientos:** pasos que se envían X minutos después.

En **/flujos**, la columna derecha tiene la referencia completa. Estos son los flujos de ejemplo:

| Flujo | Se activa con |
|---|---|
| Bienvenida (anuncio) | clic en un anuncio o primer mensaje, y luego la secuencia S/5 → S/3 → plantilla |
| Precio, Ver ejemplo, Comprar, Menú, Gracias | palabras clave o botones |
| Placa recibida | una regex que detecta `ABC-123` y la guarda en `{placa}` |
| Comprobante de pago | cualquier imagen: etapa *pago_pendiente* y bot pausado |
| Hablar con asesor | pausa el bot y deja una nota en el panel |
| No interesado | etapa *perdido*; se cancelan todos los seguimientos |
| No entendí | fallback con lista de opciones |

> Las imágenes de ejemplo son de placehold.co. Cámbialas por las tuyas: pon el archivo en `crm/static/img/` y usa `"url": "/static/img/promo.jpg"`. En producción también define `PUBLIC_BASE_URL`, porque Meta descarga las imágenes desde una URL pública.

---

## 3. Reglas de Meta que debes conocer

- **Ventana de 24 h.** Después del último mensaje del cliente, durante 24 h puedes enviar lo que quieras: texto, imágenes y botones. Pasado ese tiempo, **solo plantillas aprobadas**. El sistema ya respeta esta regla.
- **Anuncios de clic a WhatsApp.** Si el cliente llegó por un anuncio y respondes dentro de 24 h, los mensajes de las siguientes **72 h son gratis**, incluidas las plantillas. Aun así, el texto libre sigue limitado por la ventana de 24 h.
- **Por eso la secuencia de ejemplo** manda los seguimientos de S/5 y S/3 dentro de las 24 h y el de 25 h como **plantilla** (`recordatorio_oferta`). Debes crear esa plantilla en el Administrador de WhatsApp, categoría *Marketing*, con dos variables: `{{1}}` = nombre y `{{2}}` = precio.
- **Calidad del número.** Si muchos clientes te bloquean o reportan, Meta limita tu número. Envía pocos seguimientos y respeta el *"No me interesa"* (ya incluido).
- **Límites de mensajes interactivos.** Máximo 3 botones de hasta 20 caracteres cada uno. En las listas, máximo 10 filas de hasta 24 caracteres.

---

## 4. Conectar la API de Meta (cuando la tengas)

**No necesitas una fanpage nueva.** La API funciona con tu Business Manager y un número. La fanpage solo se usa para publicar los anuncios y puede ser la que ya tienes, siempre que esté en el mismo portafolio comercial.

1. **Business Manager** (business.facebook.com): crea o usa tu portafolio comercial.
2. **developers.facebook.com → Mis apps → Crear app → tipo "Empresa"**, y agrega el producto **WhatsApp**.
3. En **WhatsApp → Configuración de la API**:
   - Agrega tu número. Debe ser un número que **no** esté activo en la app de WhatsApp; usa un chip nuevo.
   - Copia el **Phone number ID** a `WA_PHONE_NUMBER_ID`.
4. **Token permanente:** Business Manager → Usuarios → **Usuarios del sistema** → crear (rol admin) → asignarle la app y la cuenta de WhatsApp → **Generar token** con los permisos `whatsapp_business_messaging` y `whatsapp_business_management`. Ese valor va en `WA_TOKEN`.
   - El token temporal del panel de Meta caduca en 24 h.
5. **Clave secreta:** App → Configuración → Básica → **Clave secreta**. Ese valor va en `WA_APP_SECRET`.
6. **Webhook:** WhatsApp → Configuración → Webhook.
   - URL: `https://TU-APP.onrender.com/webhook`.
   - Token de verificación: el mismo valor que `WA_VERIFY_TOKEN`.
   - Después suscríbete al campo **messages**.
   - Para probar en local antes de Render usa `ngrok http 5000` y pega la URL https que te da.
7. En el `.env` (o en Render) pon `WA_MODE=cloud`.
8. **Anuncio:** en el Administrador de anuncios, elige el objetivo *Interacción* o *Ventas* → ubicación de la conversión **WhatsApp** → selecciona tu fanpage y tu número. Al hacer clic, el webhook llega con `referral` y se dispara el flujo `ad_click`.
   - Con `ad_ids` puedes tener una bienvenida distinta para cada anuncio. El ID del anuncio aparece en el panel del contacto.

---

## 5. Base de datos en Supabase

1. Crea un proyecto en supabase.com y guarda la contraseña de la base.
2. Ve a **Project Settings → Database → Connection string**, elige **Session pooler** y copia la URI:
   `postgresql://postgres.xxxx:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres`
   - Usa el *pooler* porque Render no se conecta por IPv6 a la conexión directa.
3. Pega la URI en `DATABASE_URL`. Las tablas se crean solas al arrancar.
4. Al arrancar, el sistema activa **RLS** en las tablas, para que nadie pueda leerlas con la *anon key* pública de Supabase.
5. **Imágenes:** en **Project Settings → API** copia la *Project URL* a `SUPABASE_URL` y la clave **secreta** (*service_role* o `sb_secret_…`) a `SUPABASE_SERVICE_KEY`.
   - El bucket público `media` se crea solo.
   - Sin esto, las imágenes se guardan en el disco del servidor, y Render lo borra en cada reinicio.

> Para probar localmente contra Supabase, pon la misma `DATABASE_URL` en tu `.env`.

---

## 6. Desplegar en Render (gratis)

1. Sube esta carpeta a un repositorio de GitHub (el `.gitignore` excluye `.env` y la base local).
2. En Render, ve a **New → Blueprint**, elige el repo y Render leerá `render.yaml`. Si prefieres configurarlo a mano con **New → Web Service**:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 1 --threads 8 --timeout 120`
3. Completa las variables de entorno:
   - `ADMIN_PASSWORD`: una contraseña segura.
   - `DATABASE_URL`: la URI de Supabase.
   - `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`, `WA_APP_SECRET`: los datos de Meta.
   - `PUBLIC_BASE_URL`: `https://TU-APP.onrender.com`.
4. Copia la URL de Render en el webhook de Meta (paso 4.6).

### Mantenerlo despierto con UptimeRobot

El plan gratis de Render **apaga el servidor tras 15 min sin tráfico**. Mientras está dormido, los seguimientos programados no salen y el primer mensaje tarda unos 50 s en responderse. Para evitarlo:

1. Entra en uptimerobot.com y crea un monitor: **New monitor → HTTP(s)**.
2. URL: `https://TU-APP.onrender.com/cron/tick?token=TU_CRON_TOKEN`. El `CRON_TOKEN` lo ves en las variables de Render.
3. Intervalo: **5 minutos**.

Cada visita mantiene el servidor encendido y además envía los seguimientos que estén vencidos. Un solo servicio encendido todo el mes usa unas 744 h de las 750 h gratis de Render. Si el negocio crece, el plan *Starter* de Render (unos 7 USD al mes) nunca se duerme.

---

## 7. Estructura

```
app.py                 punto de entrada (python app.py / gunicorn app:app)
config.py              variables de entorno
crm/
  whatsapp.py          cliente de la Cloud API (texto, imagen, botones, lista, plantilla)
  engine.py            motor: webhook → elegir flujo → enviar globos → seguimientos
  scheduler.py         envío de seguimientos programados
  seed.py              flujos de ejemplo
  webhook.py           /webhook, /health, /cron/tick
  api.py               API del panel y del simulador
  panel.py             login y páginas
  templates/, static/  interfaz
scripts/probar_webhook.py   emula los webhooks de Meta
render.yaml            despliegue en Render
```
