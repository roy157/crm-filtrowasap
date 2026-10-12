// Simulador: te pones en el lugar del cliente. Cada acción genera el mismo JSON
// que Meta enviaría a /webhook, y el bot responde igual que en producción.
const S = { lastId: 0, waId: '', busy: false };
const QUICK = ['Hola', '¿Cuánto cuesta?', 'Quiero ver un ejemplo', 'ABC-123', 'Quiero hablar con un asesor', 'Gracias', 'No me interesa', 'asdfgh'];

function store(key, val) { try { localStorage.setItem(key, val); } catch (_) { /* sin almacenamiento */ } }
function load(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }

function waId() { return $('sim-phone').value.replace(/\D/g, ''); }

function showJson(title, obj) {
  $('json-title').textContent = title;
  $('json-view').textContent = JSON.stringify(obj, null, 2);
}

async function send(body) {
  try {
    const d = await api('/api/sim/inbound', { method: 'POST', body: { wa_id: waId(), name: $('sim-name').value, ...body } });
    showJson('Webhook que Meta enviaría a /webhook', d.payload);
    poll();
  } catch (e) { toast(e.message, 'error'); }
}

function onReply(r) {
  send({ kind: r.kind, button_id: r.id, button_title: r.title, description: r.description });
}

function onInspect(m) {
  if (m.direction === 'out') showJson(m.api ? 'JSON enviado a POST /{phone_number_id}/messages' : 'Paso (no enviado)', m.api || m.step);
}

async function poll() {
  const id = waId();
  if (S.busy || id.length < 8) return;
  S.busy = true;
  try {
    if (id !== S.waId) { S.waId = id; S.lastId = 0; $('sim-messages').innerHTML = ''; }
    const d = await api(`/api/sim/state?wa_id=${id}&after=${S.lastId}`);
    if (id !== S.waId) return;
    const box = $('sim-messages');
    if (!d.contact && !box.children.length) {
      box.innerHTML = '<div class="sim-hint">Pulsa <b>📣 Simular clic en anuncio</b> o escribe un mensaje como si fueras el cliente.</div>';
    }
    if (d.messages.length) box.querySelector('.sim-hint')?.remove();
    d.messages.forEach((m) => {
      box.appendChild(renderMessage(m, { mine: m.direction === 'in', onReply, onInspect }));
      S.lastId = Math.max(S.lastId, m.id);
    });
    if (d.messages.length) box.scrollTop = box.scrollHeight;
    $('typing').innerHTML = d.typing ? 'escribiendo<span class="typing-dots"><i></i><i></i><i></i></span>' : 'en línea';
    $('sim-sched').innerHTML = renderScheduled(d.scheduled);
    renderContact(d.contact);
  } catch (e) {
    console.error(e);
  } finally {
    S.busy = false;
  }
}

function renderContact(c) {
  if (!c) { $('sim-contact').innerHTML = '<p class="muted small">El contacto se crea con el primer mensaje.</p>'; return; }
  const vars = Object.entries(c.data || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  $('sim-contact').innerHTML = `<dl class="kv">
    <dt>Etapa</dt><dd>${stageChip(c.stage)}</dd>
    <dt>Bot</dt><dd>${c.bot_enabled ? '🤖 activo' : '⏸ pausado (asesor)'}</dd>
    <dt>Ventana</dt><dd>${c.window_open ? `abierta · cierra ${fmtRelative(c.window_expires_at)}` : '<span class="err">cerrada: solo plantillas</span>'}</dd>
    <dt>Origen</dt><dd>${c.source === 'anuncio' ? '📣 anuncio' : 'orgánico'}</dd>
    <dt>Etiquetas</dt><dd>${esc((c.tags || []).join(', ') || '—')}</dd>
    ${vars}</dl>`;
}

// ---------------------------------------------------------------- eventos
$('sim-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = $('sim-text').value.trim();
  if (!text) return;
  $('sim-text').value = '';
  send({ kind: 'text', text });
});

$('quick').innerHTML = QUICK.map((q) => `<button type="button">${esc(q)}</button>`).join('');
$('quick').addEventListener('click', (e) => {
  if (e.target.tagName === 'BUTTON') send({ kind: 'text', text: e.target.textContent });
});

$('sim-ad').addEventListener('click', () => send({ kind: 'ad', text: '¡Hola! Quiero más información' }));
$('sim-image').addEventListener('click', () => send({ kind: 'image', text: 'Ya pagué' }));

$('sim-ff').addEventListener('click', async () => {
  try {
    const d = await api('/api/sim/fast_forward', { method: 'POST', body: { wa_id: waId() } });
    toast(`Enviando «${d.label}» ahora…`);
  } catch (e) { toast(e.message, 'error'); }
});

$('sim-expire').addEventListener('click', async () => {
  try {
    await api('/api/sim/expire_window', { method: 'POST', body: { wa_id: waId() } });
    toast('Ahora es como si hubieran pasado 25 h: solo saldrán plantillas');
    poll();
  } catch (e) { toast(e.message, 'error'); }
});

$('sim-reset').addEventListener('click', async () => {
  if (!confirm('¿Borrar este chat de prueba y empezar de cero?')) return;
  await api('/api/sim/reset', { method: 'POST', body: { wa_id: waId() } });
  S.waId = '';
  $('json-view').textContent = 'Chat reiniciado.';
  poll();
});

['sim-phone', 'sim-name'].forEach((id) => {
  const saved = load(id);
  if (saved) $(id).value = saved;
  $(id).addEventListener('change', () => { store(id, $(id).value); poll(); });
});

poll();
setInterval(poll, 1200);
