// Utilidades compartidas por el panel, el simulador y el editor de flujos.
const STAGE_LABELS = { nuevo: 'Nuevo', interesado: 'Interesado', pago_pendiente: 'Pago pendiente', cliente: 'Cliente', perdido: 'Perdido' };
const SCHED_LABELS = { pending: 'Programado', processing: 'Enviando…', sent: 'Enviado', cancelled: 'Cancelado', skipped: 'Omitido', error: 'Error' };
const TZ = 'America/Lima';
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Formato de WhatsApp: *negrita* _cursiva_ ~tachado~
function waFormat(s) {
  return esc(s)
    .replace(/\*([^*\n]+)\*/g, '<b>$1</b>')
    .replace(/(^|[\s(])_([^_\n]+)_/g, '$1<i>$2</i>')
    .replace(/~([^~\n]+)~/g, '<s>$1</s>')
    .replace(/\n/g, '<br>');
}

function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', timeZone: TZ }) : '';
}
function fmtDateTime(iso) {
  return iso ? new Date(iso).toLocaleString('es-PE', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: TZ }) : '';
}
function fmtShort(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return (Date.now() - d) < 86400000 ? fmtTime(iso) : d.toLocaleDateString('es-PE', { day: '2-digit', month: 'short', timeZone: TZ });
}
function fmtRelative(iso) {
  const s = Math.round((new Date(iso) - Date.now()) / 1000);
  const a = Math.abs(s);
  const txt = a < 60 ? `${a} s` : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${(a / 3600).toFixed(1)} h` : `${(a / 86400).toFixed(1)} d`;
  return s >= 0 ? `en ${txt}` : `hace ${txt}`;
}

async function api(url, { method = 'GET', body } = {}) {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname); throw new Error('No autorizado'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
  return data;
}

let toastTimer;
function toast(msg, kind = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show ' + (kind === 'error' ? 'error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = 'toast'), 2800);
}

function statusMark(m) {
  return ({ sent: '✓', delivered: '✓✓', read: '<span class="read">✓✓</span>', simulated: '✓', failed: '⚠️', skipped: '⛔' })[m.status] || '';
}

function stageChip(stage) {
  return `<span class="stage stage-${esc(stage)}">${esc(STAGE_LABELS[stage] || stage)}</span>`;
}

/**
 * Dibuja un globo de WhatsApp.
 * mine: si va a la derecha (verde). onReply: hace clicables botones/listas (simulador).
 * showMeta: muestra flujo y estado (panel). onInspect: clic para ver el JSON enviado a Meta.
 */
function renderMessage(m, { mine = false, onReply = null, showMeta = false, onInspect = null } = {}) {
  const row = document.createElement('div');
  if (m.direction === 'system') {
    row.className = 'sys-note';
    row.innerHTML = `${waFormat(m.text)} · ${fmtTime(m.created_at)}`;
    return row;
  }
  row.className = 'msg-row ' + (mine ? 'mine' : 'theirs');
  const b = document.createElement('div');
  b.className = 'bubble' + (m.status === 'skipped' ? ' skipped' : '') + (m.status === 'failed' ? ' failed' : '');
  const step = m.step || {};
  let html = '';
  if (m.type === 'button_reply') html += '<div class="reply-tag">↩ Respondió con un botón</div>';
  if (m.type === 'template') html += `<div class="tpl-badge">📋 Plantilla: <b>${esc(step.name)}</b></div>`;
  if (step.image && m.type === 'buttons') html += `<img class="media" src="${esc(step.image)}" alt="">`;
  if (m.media_url && m.type === 'image') html += `<img class="media" src="${esc(m.media_url)}" alt="imagen" loading="lazy">`;
  if (m.type === 'document') html += `<div class="doc">📄 ${esc(step.filename || 'Documento')}</div>`;
  if (m.body) html += `<div class="body">${waFormat(m.body)}</div>`;
  if (step.footer) html += `<div class="footer-txt">${esc(step.footer)}</div>`;
  const flow = showMeta && m.flow_name ? `<span class="flow">${esc(m.flow_name)}</span>` : '';
  const ticks = showMeta && m.direction === 'out' ? statusMark(m) : '';
  html += `<div class="meta">${flow}<span>${fmtTime(m.created_at)}</span>${ticks}</div>`;
  if (m.error) html += `<div class="err">${esc(m.error)}</div>`;
  b.innerHTML = html;

  if (m.type === 'buttons' && Array.isArray(step.buttons)) {
    const box = document.createElement('div');
    box.className = 'wa-buttons';
    step.buttons.forEach((btn) => {
      const el = document.createElement('button');
      el.className = 'wa-btn';
      el.textContent = btn.title;
      el.disabled = !onReply;
      if (onReply) el.onclick = (e) => { e.stopPropagation(); onReply({ kind: 'button', id: btn.id, title: btn.title }); };
      box.appendChild(el);
    });
    b.appendChild(box);
  }

  if (m.type === 'list' && Array.isArray(step.sections)) {
    const box = document.createElement('div');
    box.className = 'wa-buttons';
    const toggle = document.createElement('button');
    toggle.className = 'wa-btn';
    toggle.textContent = '☰ ' + (step.button || 'Ver opciones');
    const list = document.createElement('div');
    list.className = 'wa-list hidden';
    step.sections.forEach((sec) => {
      list.insertAdjacentHTML('beforeend', `<div class="sec">${esc(sec.title || '')}</div>`);
      (sec.rows || []).forEach((r) => {
        const el = document.createElement('div');
        el.className = 'rowi';
        el.innerHTML = `<div>${esc(r.title)}</div>${r.description ? `<div class="d">${esc(r.description)}</div>` : ''}`;
        if (onReply) el.onclick = (e) => { e.stopPropagation(); list.classList.add('hidden'); onReply({ kind: 'list', id: r.id, title: r.title, description: r.description }); };
        list.appendChild(el);
      });
    });
    toggle.onclick = (e) => { e.stopPropagation(); list.classList.toggle('hidden'); };
    box.appendChild(toggle);
    b.appendChild(box);
    b.appendChild(list);
  }

  if (onInspect && (m.api || m.step)) {
    b.classList.add('inspectable');
    b.title = 'Ver JSON enviado a la Cloud API';
    b.addEventListener('click', () => onInspect(m));
  }
  row.appendChild(b);
  return row;
}

async function uploadFile(fileOrBlob, name) {
  const fd = new FormData();
  fd.append('file', fileOrBlob, name || fileOrBlob.name || 'imagen.jpg');
  if (name) fd.append('name', name);
  const res = await fetch('/api/media', { method: 'POST', body: fd, credentials: 'same-origin' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
  if (data.warning) toast(data.warning, 'error');
  return data.asset;
}

function fmtSize(bytes) {
  return bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

// Ventana para elegir una imagen de la biblioteca (o subir una nueva). onPick(asset)
async function openMediaPicker(onPick, { accept = 'image' } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal">
      <div class="modal-head"><h3>Biblioteca de imágenes</h3><button class="btn ghost" data-close>✕</button></div>
      <div class="modal-tools">
        <label class="btn primary upload-btn">⬆ Subir desde mi PC<input type="file" accept="${accept === 'image' ? 'image/jpeg,image/png' : 'application/pdf'}" hidden></label>
        <a href="/imagenes" target="_blank" class="small">Diseñar una promo →</a>
      </div>
      <div class="media-grid picker" data-grid><p class="muted">Cargando…</p></div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay || e.target.closest('[data-close]')) close(); });

  const grid = overlay.querySelector('[data-grid]');
  async function load() {
    const d = await api('/api/media');
    const items = d.assets.filter((a) => (accept === 'image' ? a.mime.startsWith('image/') : a.mime === 'application/pdf'));
    grid.innerHTML = items.length
      ? items.map((a) => `<button class="media-item" data-id="${a.id}">
          ${a.mime.startsWith('image/') ? `<img src="${esc(a.url)}" alt="" loading="lazy">` : '<div class="pdf">📄 PDF</div>'}
          <span>${esc(a.name)}</span></button>`).join('')
      : '<p class="muted">Aún no tienes archivos. Sube uno o diseña una promo en la pestaña Imágenes.</p>';
    grid.querySelectorAll('[data-id]').forEach((el) => el.addEventListener('click', () => {
      onPick(items.find((a) => a.id === Number(el.dataset.id)));
      close();
    }));
  }
  overlay.querySelector('input[type=file]').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try { const a = await uploadFile(file); toast('Archivo subido'); onPick(a); close(); } catch (err) { toast(err.message, 'error'); }
  });
  load().catch((err) => { grid.innerHTML = `<p class="err">${esc(err.message)}</p>`; });
}

function renderScheduled(list, { onCancel = null } = {}) {
  if (!list.length) return '<p class="muted small">Sin seguimientos.</p>';
  return list.map((s) => {
    const pending = s.status === 'pending';
    const when = pending ? `${fmtDateTime(s.run_at)} · ${fmtRelative(s.run_at)}` : (s.result || '');
    const cls = { pending: 'warn', sent: 'ok', error: 'bad', cancelled: '', skipped: '' }[s.status] || '';
    return `<div class="sched ${pending ? '' : 'done'}">
      <div class="top"><b>${esc(s.label)}</b><span class="badge ${cls}">${SCHED_LABELS[s.status] || s.status}</span></div>
      <div class="small muted">${esc(when)}</div>
      ${s.preview ? `<div class="pv">${esc(s.preview)}</div>` : ''}
      ${pending && onCancel ? `<button class="btn small danger ghost" data-cancel="${s.id}">Cancelar</button>` : ''}
    </div>`;
  }).join('');
}
