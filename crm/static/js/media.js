// Biblioteca de imágenes + diseñador de promociones (canvas).
const BRAND = document.body.dataset.business || 'Mi negocio';
const SIZES = { square: [1080, 1080], portrait: [1080, 1350], story: [1080, 1920] };
const FONT = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const PRESETS = {
  'Bienvenida': { badge: '🚗 NUEVO', title: 'Reporte vehicular completo', subtitle: 'Papeletas · SOAT · Revisión técnica · Propietarios', old: '', now: 'S/10', cta: 'Escríbenos por WhatsApp 📲', bg: '#0b8457', accent: '#ffd60a', text: '#ffffff' },
  'Promo S/5': { badge: '🔥 SOLO HOY', title: 'Tu reporte vehicular a mitad de precio', subtitle: 'Envía tu placa y recíbelo en minutos', old: 'S/10', now: 'S/5', cta: 'Pídelo ahora por WhatsApp 📲', bg: '#1e3a8a', accent: '#ffd60a', text: '#ffffff' },
  'Última oportunidad S/3': { badge: '⏰ ÚLTIMAS HORAS', title: 'Última oportunidad', subtitle: 'Reporte vehicular completo con solo tu placa', old: 'S/10', now: 'S/3', cta: 'Responde con tu placa 🚗', bg: '#b91c1c', accent: '#ffffff', text: '#ffffff' },
};
const D = { photo: null };
const canvas = $('d-canvas');
const ctx = canvas.getContext('2d');
const val = (id) => $(id).value;

// ---------------------------------------------------------------- dibujo
function wrapLines(text, maxW) {
  const out = [];
  text.split('\n').forEach((para) => {
    let line = '';
    para.split(/\s+/).filter(Boolean).forEach((w) => {
      const test = line ? `${line} ${w}` : w;
      if (ctx.measureText(test).width > maxW && line) { out.push(line); line = w; } else line = test;
    });
    if (line) out.push(line);
  });
  return out;
}

/** Ajusta el tamaño de letra para que el texto quepa en maxLines líneas. */
function fitText(text, weight, size, minSize, maxW, maxLines) {
  let lines;
  do {
    ctx.font = `${weight} ${size}px ${FONT}`;
    lines = wrapLines(text, maxW);
    if (lines.length <= maxLines) break;
    size -= 4;
  } while (size > minSize);
  return { lines, size };
}

function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const c = (s) => Math.max(0, Math.min(255, ((n >> s) & 255) + amt));
  return `rgb(${c(16)},${c(8)},${c(0)})`;
}

function draw() {
  const [W, H] = SIZES[val('d-format')];
  canvas.width = W;
  canvas.height = H;
  const bg = val('d-bg');
  const accent = val('d-accent');
  const color = val('d-text');
  const pad = Math.round(W * 0.08);
  const maxW = W - pad * 2;
  $('d-dark-v').textContent = `${val('d-dark')}%`;

  // fondo
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, shade(bg, 25));
  g.addColorStop(1, shade(bg, -45));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  if (D.photo) {
    const s = Math.max(W / D.photo.width, H / D.photo.height);
    const w = D.photo.width * s;
    const hh = D.photo.height * s;
    ctx.drawImage(D.photo, (W - w) / 2, (H - hh) / 2, w, hh);
    ctx.fillStyle = `rgba(0,0,0,${val('d-dark') / 100})`;
    ctx.fillRect(0, 0, W, H);
  } else {
    ctx.fillStyle = 'rgba(255,255,255,.06)'; // círculos decorativos
    ctx.beginPath(); ctx.arc(W * 0.95, H * 0.1, W * 0.35, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(W * 0.05, H * 0.95, W * 0.25, 0, Math.PI * 2); ctx.fill();
  }

  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = color;
  let y = pad;

  // marca
  if (val('d-brand')) {
    ctx.globalAlpha = 0.9;
    ctx.font = `700 40px ${FONT}`;
    ctx.fillText(val('d-brand'), pad, y + 36);
    ctx.globalAlpha = 1;
    y += 90;
  }
  // etiqueta
  if (val('d-badge')) {
    ctx.font = `800 44px ${FONT}`;
    const tw = ctx.measureText(val('d-badge')).width;
    ctx.fillStyle = accent;
    ctx.beginPath(); ctx.roundRect(pad, y, tw + 56, 80, 40); ctx.fill();
    ctx.fillStyle = isLight(accent) ? '#111' : '#fff';
    ctx.fillText(val('d-badge'), pad + 28, y + 56);
    ctx.fillStyle = color;
    y += 130;
  }

  // reserva el espacio de abajo (precio + botón) y ajusta título/subtítulo al hueco que queda
  const big = H > 1100 ? 260 : 210;
  const ctaH = val('d-cta') ? 150 : 0;
  const priceH = val('d-new') ? big + (val('d-old') ? 110 : 0) : 0;
  const limit = H - pad - ctaH - priceH - 30;
  let title = null;
  let sub = null;
  for (let size = H > 1100 ? 110 : 96; size >= 40; size -= 4) {
    title = val('d-title') ? fitText(val('d-title'), 800, size, size, maxW, 99) : { lines: [], size };
    sub = val('d-subtitle') ? fitText(val('d-subtitle'), 500, Math.max(28, Math.round(size * 0.46)), 28, maxW, 99) : { lines: [], size: 0 };
    const hgt = title.lines.length * title.size * 1.05 + (title.lines.length ? 30 : 0) + sub.lines.length * sub.size * 1.3;
    if (y + hgt <= limit) break;
  }
  ctx.font = `800 ${title.size}px ${FONT}`;
  title.lines.forEach((l) => { y += title.size * 1.05; ctx.fillText(l, pad, y); });
  if (title.lines.length) y += 30;
  ctx.font = `500 ${sub.size}px ${FONT}`;
  ctx.globalAlpha = 0.92;
  sub.lines.forEach((l) => { y += sub.size * 1.3; if (y <= limit) ctx.fillText(l, pad, y); });
  ctx.globalAlpha = 1;

  // abajo: llamado a la acción
  let bottom = H - pad;
  if (val('d-cta')) {
    ctx.font = `700 46px ${FONT}`;
    const tw = Math.min(ctx.measureText(val('d-cta')).width, maxW - 60);
    ctx.fillStyle = accent;
    ctx.beginPath(); ctx.roundRect(pad, bottom - 100, tw + 70, 100, 50); ctx.fill();
    ctx.fillStyle = isLight(accent) ? '#111' : '#fff';
    ctx.fillText(val('d-cta'), pad + 35, bottom - 34, maxW - 60);
    ctx.fillStyle = color;
    bottom -= 150;
  }
  // precios
  if (val('d-new')) {
    ctx.font = `900 ${big}px ${FONT}`;
    ctx.fillText(val('d-new'), pad, bottom, maxW);
    if (val('d-old')) {
      ctx.font = `600 84px ${FONT}`;
      const oy = bottom - big - 10;
      const ow = ctx.measureText(val('d-old')).width;
      ctx.globalAlpha = 0.75;
      ctx.fillText(val('d-old'), pad, oy);
      ctx.fillRect(pad - 6, oy - 30, ow + 12, 8);
      ctx.globalAlpha = 1;
      ctx.font = `600 40px ${FONT}`;
      ctx.fillText('antes', pad + ow + 24, oy);
    }
  }
}

function isLight(hex) {
  const n = parseInt(hex.slice(1), 16);
  return (((n >> 16) & 255) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000 > 150;
}

function applyPreset(name) {
  const p = PRESETS[name];
  $('d-badge').value = p.badge; $('d-title').value = p.title; $('d-subtitle').value = p.subtitle;
  $('d-old').value = p.old; $('d-new').value = p.now; $('d-cta').value = p.cta;
  $('d-bg').value = p.bg; $('d-accent').value = p.accent; $('d-text').value = p.text;
  $('d-name').value = name;
  draw();
}

function loadPhoto(src, crossOrigin) {
  const img = new Image();
  if (crossOrigin) img.crossOrigin = 'anonymous';
  img.onload = () => { D.photo = img; draw(); };
  img.onerror = () => toast('No se pudo cargar la foto', 'error');
  img.src = src;
}

function exportBlob() {
  return new Promise((resolve, reject) => {
    try { canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('No se pudo generar la imagen'))), 'image/jpeg', 0.9); }
    catch (e) { reject(new Error('Esa foto de fondo no se puede exportar. Súbela con «Desde mi PC».')); }
  });
}

// ---------------------------------------------------------------- biblioteca
async function loadLibrary() {
  const d = await api('/api/media');
  $('storage-mode').textContent = d.storage === 'supabase' ? '☁️ Guardando en Supabase Storage' : '💻 Guardando en tu PC (solo pruebas)';
  $('storage-mode').className = 'badge ' + (d.storage === 'supabase' ? 'ok' : 'warn');
  $('library').innerHTML = d.assets.length ? d.assets.map((a) => `
    <div class="media-item" data-id="${a.id}">
      ${a.mime.startsWith('image/') ? `<img src="${esc(a.url)}" alt="" loading="lazy">` : '<div class="pdf">📄 PDF</div>'}
      <span title="${esc(a.name)}">${esc(a.name)}</span>
      <small class="muted">${fmtSize(a.size)} · ${fmtShort(a.created_at)}</small>
      <div class="row">
        <button class="btn small" data-act="copy" data-url="${esc(a.url)}">📋 Enlace</button>
        <button class="btn small" data-act="rename">✏️</button>
        <button class="btn small danger ghost" data-act="del">🗑</button>
      </div>
    </div>`).join('') : '<p class="muted">Aún no hay imágenes. Sube tus fotos o guarda una promo del diseñador.</p>';
}

async function uploadMany(files) {
  for (const f of files) {
    try { await uploadFile(f); toast(`Subido: ${f.name}`); } catch (e) { toast(`${f.name}: ${e.message}`, 'error'); }
  }
  loadLibrary();
}

// ---------------------------------------------------------------- eventos
$('presets').innerHTML = Object.keys(PRESETS).map((n) => `<button class="chip" data-p="${esc(n)}">${esc(n)}</button>`).join('');
$('presets').addEventListener('click', (e) => { if (e.target.dataset.p) applyPreset(e.target.dataset.p); });
document.querySelectorAll('.designer-form input, .designer-form textarea, .designer-form select').forEach((el) => el.addEventListener('input', draw));

$('d-photo').addEventListener('change', (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => loadPhoto(r.result, false);
  r.readAsDataURL(f);
});
$('d-photo-lib').addEventListener('click', () => openMediaPicker((a) => loadPhoto(a.url, true)));
$('d-photo-clear').addEventListener('click', () => { D.photo = null; $('d-photo').value = ''; draw(); });

$('d-save').addEventListener('click', async () => {
  try {
    const blob = await exportBlob();
    const name = (val('d-name') || val('d-title') || 'Promo').trim();
    await uploadFile(blob, `${name}.jpg`);
    toast('✅ Guardada en la biblioteca. Ya puedes usarla en tus flujos.');
    loadLibrary();
  } catch (e) { toast(e.message, 'error'); }
});

$('d-download').addEventListener('click', async () => {
  try {
    const blob = await exportBlob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(val('d-name') || 'promo').replace(/[^\w\- ]+/g, '').trim() || 'promo'}.jpg`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) { toast(e.message, 'error'); }
});

const dz = $('dropzone');
$('files').addEventListener('change', (e) => { uploadMany([...e.target.files]); e.target.value = ''; });
['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('over'); }));
['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('over'); }));
dz.addEventListener('drop', (e) => uploadMany([...e.dataTransfer.files]));

$('library').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const id = btn.closest('[data-id]').dataset.id;
  if (btn.dataset.act === 'copy') {
    const url = new URL(btn.dataset.url, location.origin).href;
    try { await navigator.clipboard.writeText(url); toast('Enlace copiado'); } catch (_) { prompt('Copia el enlace:', url); }
  } else if (btn.dataset.act === 'rename') {
    const name = prompt('Nuevo nombre:');
    if (name) { await api(`/api/media/${id}`, { method: 'PATCH', body: { name } }); loadLibrary(); }
  } else if (btn.dataset.act === 'del') {
    if (!confirm('¿Eliminar este archivo? Si un flujo lo usa, ese mensaje fallará.')) return;
    await api(`/api/media/${id}`, { method: 'DELETE' });
    loadLibrary();
  }
});

$('d-brand').value = BRAND;
applyPreset('Promo S/5');
if (document.fonts?.ready) document.fonts.ready.then(draw);
loadLibrary();
