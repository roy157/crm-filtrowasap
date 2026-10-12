// Editor visual de flujos: tarjetas en lugar de JSON, con vista previa en vivo.
const S = { flows: [], current: null, jsonMode: false, dirty: false };
const units = new WeakMap(); // seguimiento -> unidad elegida (min / h / d)
const UNIT = { min: 1, h: 60, d: 1440 };
const UNIT_LABELS = { min: 'minutos', h: 'horas', d: 'días' };
const SAMPLE_VARS = { nombre: 'Carlos', nombre_completo: 'Carlos Pérez', telefono: '51987654321', precio: '10', placa: 'ABC-123' };

const EVENTS = [
  ['ad_click', '📣', 'Clic en un anuncio', 'Llega desde tu anuncio de Facebook o Instagram'],
  ['first_message', '👋', 'Primer mensaje', 'Un cliente nuevo te escribe por primera vez'],
  ['media', '📷', 'Envía una imagen', 'Por ejemplo, la captura de su pago'],
  ['fallback', '🤷', 'El bot no entiende', 'Ningún otro flujo coincide'],
];

const STEP_DEFS = {
  text: { icon: '💬', label: 'Texto', make: () => ({ type: 'text', text: '' }) },
  image: { icon: '🖼️', label: 'Imagen', make: () => ({ type: 'image', url: '', caption: '' }) },
  buttons: { icon: '🔘', label: 'Botones', make: () => ({ type: 'buttons', text: '', buttons: [{ id: '', title: '' }] }) },
  list: { icon: '☰', label: 'Lista de opciones', make: () => ({ type: 'list', text: '', button: 'Ver opciones', sections: [{ title: 'Opciones', rows: [{ id: '', title: '', description: '' }] }] }) },
  delay: { icon: '⏱️', label: 'Espera', make: () => ({ type: 'delay', seconds: 2 }) },
  document: { icon: '📄', label: 'Documento PDF', make: () => ({ type: 'document', url: '', filename: '', caption: '' }) },
  template: { icon: '📋', label: 'Plantilla de Meta (fuera de 24 h)', make: () => ({ type: 'template', name: '', language: 'es', params: [], preview: '' }) },
  set_stage: { icon: '🏷️', label: 'Cambiar etapa', make: () => ({ type: 'set_stage', stage: 'interesado' }) },
  add_tag: { icon: '🔖', label: 'Agregar etiqueta', make: () => ({ type: 'add_tag', tag: '' }) },
  remove_tag: { icon: '✂️', label: 'Quitar etiqueta', make: () => ({ type: 'remove_tag', tag: '' }) },
  set_var: { icon: '🧮', label: 'Guardar un dato', make: () => ({ type: 'set_var', key: 'precio', value: '' }) },
  note: { icon: '📝', label: 'Nota interna para el asesor', make: () => ({ type: 'note', text: '' }) },
  pause_bot: { icon: '⏸️', label: 'Pausar bot (pasa a un asesor)', make: () => ({ type: 'pause_bot' }) },
  resume_bot: { icon: '▶️', label: 'Reactivar bot', make: () => ({ type: 'resume_bot' }) },
  cancel_followups: { icon: '🚫', label: 'Cancelar seguimientos', make: () => ({ type: 'cancel_followups' }) },
};
const MESSAGE_KINDS = ['text', 'image', 'buttons', 'list', 'document', 'template'];
const CHIP_KINDS = ['text', 'image', 'buttons', 'list', 'delay'];
const MORE_KINDS = ['document', 'template', 'set_stage', 'add_tag', 'remove_tag', 'set_var', 'note', 'pause_bot', 'resume_bot', 'cancel_followups'];

// ---------------------------------------------------------------- utilidades DOM
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') el.className = v;
    else if (k === 'value') value = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? '' : v);
  }
  children.flat().forEach((c) => { if (c != null && c !== false) el.append(typeof c === 'string' ? document.createTextNode(c) : c); });
  if (value !== undefined) el.value = value;
  return el;
}

function iconBtn(icon, title, onclick, disabled = false) {
  return h('button', { type: 'button', class: 'icon-btn', title, onclick, disabled }, icon);
}

function changed() { S.dirty = true; preview(); }

function fillVars(obj, vars) {
  if (typeof obj === 'string') return obj.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  if (Array.isArray(obj)) return obj.map((x) => fillVars(x, vars));
  if (obj && typeof obj === 'object') return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, fillVars(v, vars)]));
  return obj;
}

/** Campo de texto enlazado a obj[key]. */
function field(label, obj, key, { placeholder = '', max, type = 'text', rows = 0, vars = false, hint } = {}) {
  const ctl = rows ? h('textarea', { rows, placeholder, maxlength: max }) : h('input', { type, placeholder, maxlength: max });
  ctl.value = obj[key] ?? '';
  const counter = max ? h('span', { class: 'counter' }) : null;
  const upd = () => { if (counter) counter.textContent = `${ctl.value.length}/${max}`; };
  ctl.addEventListener('input', () => { obj[key] = type === 'number' ? Number(ctl.value) : ctl.value; upd(); changed(); });
  upd();
  const lab = h('label', { class: 'f' }, h('span', { class: 'f-label' }, label, counter), ctl);
  if (vars) lab.append(varChips(ctl));
  if (hint) lab.append(h('span', { class: 'hint' }, hint));
  return lab;
}

function varChips(ctl) {
  const box = h('div', { class: 'var-chips' }, h('span', { class: 'small muted' }, 'Insertar:'));
  ['{nombre}', '{precio}', '{placa}', '*negrita*'].forEach((v) => box.append(h('button', {
    type: 'button', class: 'var-chip', onclick: () => {
      const s = ctl.selectionStart ?? ctl.value.length;
      const e = ctl.selectionEnd ?? s;
      const sel = ctl.value.slice(s, e);
      const ins = v === '*negrita*' ? `*${sel || 'texto'}*` : v;
      ctl.value = ctl.value.slice(0, s) + ins + ctl.value.slice(e);
      ctl.focus();
      ctl.selectionStart = ctl.selectionEnd = s + ins.length;
      ctl.dispatchEvent(new Event('input'));
    },
  }, v)));
  return box;
}

// ---------------------------------------------------------------- botones → flujo destino
function flowForButton(id) {
  if (!id) return '';
  if (id.startsWith('flow:')) return id.slice(5);
  const f = S.flows.find((x) => (x.triggers.buttons || []).includes(id));
  return f ? String(f.id) : 'custom';
}

function targetPicker(item) {
  const sel = h('select', { class: 'target' },
    h('option', { value: '' }, '— ¿Qué flujo abre? —'),
    S.flows.map((f) => h('option', { value: String(f.id) }, `→ ${f.name}`)),
    h('option', { value: 'custom' }, 'ID personalizado…'));
  const custom = h('input', { class: 'custom-id', placeholder: 'id_del_boton', value: item.id || '' });
  const cur = flowForButton(item.id);
  sel.value = cur;
  custom.classList.toggle('hidden', cur !== 'custom');
  sel.addEventListener('change', () => {
    if (sel.value === 'custom') { custom.classList.remove('hidden'); item.id = custom.value.trim(); }
    else if (sel.value) {
      const f = S.flows.find((x) => String(x.id) === sel.value);
      item.id = (f.triggers.buttons || [])[0] || `flow:${f.id}`;
      custom.classList.add('hidden');
    } else item.id = '';
    S.dirty = true;
  });
  custom.addEventListener('input', () => { item.id = custom.value.trim(); S.dirty = true; });
  return h('div', { class: 'target-wrap' }, sel, custom);
}

// ---------------------------------------------------------------- tarjetas de pasos
function stepFields(step, body) {
  switch (step.type) {
    case 'text':
      body.append(field('Mensaje', step, 'text', { rows: 3, max: 4096, vars: true, placeholder: 'Escribe el mensaje… usa {nombre} para personalizar' }));
      break;
    case 'image':
    case 'document': {
      const isImg = step.type === 'image';
      const thumb = isImg ? h('img', { class: 'thumb', alt: '' }) : h('div', { class: 'thumb pdf' }, '📄');
      if (isImg && step.url) thumb.src = step.url;
      const url = h('input', { placeholder: 'Elige de la biblioteca o pega un enlace https://…', value: step.url || '' });
      url.addEventListener('input', () => { step.url = url.value.trim(); if (isImg) thumb.src = step.url; changed(); });
      const pick = h('button', {
        type: 'button', class: 'btn small primary',
        onclick: () => openMediaPicker((a) => {
          step.url = a.url;
          if (!isImg && !step.filename) step.filename = a.name;
          rerender();
        }, { accept: isImg ? 'image' : 'pdf' }),
      }, isImg ? '🖼️ Elegir imagen' : '📄 Elegir PDF');
      body.append(h('div', { class: 'media-row' }, thumb, h('div', { class: 'grow' }, pick, url)));
      if (!isImg) body.append(field('Nombre del archivo que verá el cliente', step, 'filename', { placeholder: 'reporte.pdf' }));
      body.append(field(isImg ? 'Texto debajo de la imagen (opcional)' : 'Texto (opcional)', step, 'caption', { rows: 2, max: 1024, vars: true }));
      break;
    }
    case 'buttons': {
      body.append(field('Mensaje', step, 'text', { rows: 2, max: 1024, vars: true, placeholder: '¿Qué te gustaría hacer?' }));
      const list = h('div', { class: 'opt-list' });
      step.buttons.forEach((b, i) => {
        list.append(h('div', { class: 'opt-row' },
          h('span', { class: 'opt-num' }, String(i + 1)),
          field('Texto del botón', b, 'title', { max: 20, placeholder: 'Ej. 💰 Ver precio' }),
          targetPicker(b),
          iconBtn('🗑', 'Quitar botón', () => { step.buttons.splice(i, 1); rerender(); }, step.buttons.length === 1)));
      });
      body.append(list);
      if (step.buttons.length < 3) body.append(h('button', { type: 'button', class: 'btn small', onclick: () => { step.buttons.push({ id: '', title: '' }); rerender(); } }, '+ Agregar botón'));
      body.append(h('p', { class: 'hint' }, 'WhatsApp permite hasta 3 botones de 20 caracteres. Cuando el cliente toque uno, se envía el flujo elegido.'));
      break;
    }
    case 'list': {
      const sec = step.sections[0] || (step.sections[0] = { title: 'Opciones', rows: [] });
      body.append(field('Mensaje', step, 'text', { rows: 2, max: 1024, vars: true }));
      body.append(h('div', { class: 'row' }, field('Texto del botón que abre la lista', step, 'button', { max: 20 }), field('Título de la sección', sec, 'title', { max: 24 })));
      const list = h('div', { class: 'opt-list' });
      sec.rows.forEach((r, i) => {
        list.append(h('div', { class: 'opt-row' },
          h('span', { class: 'opt-num' }, String(i + 1)),
          h('div', { class: 'grow' }, field('Opción', r, 'title', { max: 24 }), field('Descripción (opcional)', r, 'description', { max: 72 })),
          targetPicker(r),
          iconBtn('🗑', 'Quitar opción', () => { sec.rows.splice(i, 1); rerender(); }, sec.rows.length === 1)));
      });
      body.append(list);
      if (sec.rows.length < 10) body.append(h('button', { type: 'button', class: 'btn small', onclick: () => { sec.rows.push({ id: '', title: '', description: '' }); rerender(); } }, '+ Agregar opción'));
      break;
    }
    case 'delay':
      body.append(h('div', { class: 'row center-row' }, 'Esperar',
        field('', step, 'seconds', { type: 'number' }), 'segundos mostrando «escribiendo…» (máx. 20)'));
      break;
    case 'template': {
      body.append(h('div', { class: 'row' },
        field('Nombre exacto de la plantilla en Meta', step, 'name', { placeholder: 'recordatorio_oferta' }),
        field('Idioma', step, 'language', { placeholder: 'es' })));
      const params = h('input', { placeholder: '{nombre}, S/3', value: (step.params || []).join(', ') });
      params.addEventListener('input', () => { step.params = params.value.split(',').map((x) => x.trim()).filter(Boolean); changed(); });
      body.append(h('label', { class: 'f' }, h('span', { class: 'f-label' }, 'Valores de las variables {{1}}, {{2}}… (separados por coma)'), params));
      body.append(field('Texto de la plantilla (solo para la vista previa y el panel)', step, 'preview', { rows: 2 }));
      body.append(h('p', { class: 'hint' }, 'Las plantillas se crean y aprueban en el Administrador de WhatsApp de Meta. Son las únicas que se pueden enviar pasadas 24 h desde el último mensaje del cliente.'));
      break;
    }
    case 'set_stage': {
      const sel = h('select', {}, Object.entries(STAGE_LABELS).map(([k, l]) => h('option', { value: k }, l)));
      sel.value = step.stage;
      sel.addEventListener('change', () => { step.stage = sel.value; changed(); });
      body.append(h('label', { class: 'f' }, h('span', { class: 'f-label' }, 'Mover al cliente a la etapa'), sel));
      break;
    }
    case 'add_tag':
    case 'remove_tag':
      body.append(field('Etiqueta', step, 'tag', { placeholder: 'vip, requiere_asesor…' }));
      break;
    case 'set_var':
      body.append(h('div', { class: 'row' }, field('Nombre del dato', step, 'key', { placeholder: 'precio' }), field('Valor', step, 'value', { placeholder: '5' })));
      body.append(h('p', { class: 'hint' }, 'Luego úsalo en tus mensajes como {precio}. Útil para bajar el precio en cada seguimiento.'));
      break;
    case 'note':
      body.append(field('Texto (solo lo ve tu equipo en la bandeja)', step, 'text', { rows: 2, vars: true }));
      break;
    case 'pause_bot':
      body.append(h('p', { class: 'hint' }, 'El bot deja de responder a este cliente para que lo atienda una persona. Se reactiva desde la bandeja.'));
      break;
    case 'resume_bot':
      body.append(h('p', { class: 'hint' }, 'El bot vuelve a responder automáticamente.'));
      break;
    case 'cancel_followups':
      body.append(h('p', { class: 'hint' }, 'Cancela los seguimientos pendientes de este cliente.'));
      break;
    default:
      body.append(h('pre', { class: 'json' }, JSON.stringify(step, null, 2)));
  }
}

function move(list, i, d) {
  const [x] = list.splice(i, 1);
  list.splice(i + d, 0, x);
  rerender();
}

function stepCard(list, i) {
  const step = list[i];
  const def = STEP_DEFS[step.type] || { icon: '❓', label: step.type };
  const isMsg = MESSAGE_KINDS.includes(step.type);
  const card = h('div', { class: `step-card ${isMsg ? 'msg' : step.type === 'delay' ? 'delay' : 'action'}` },
    h('div', { class: 'step-head' },
      h('span', { class: 'step-icon' }, def.icon), h('b', {}, def.label), h('span', { class: 'grow' }),
      iconBtn('↑', 'Subir', () => move(list, i, -1), i === 0),
      iconBtn('↓', 'Bajar', () => move(list, i, 1), i === list.length - 1),
      iconBtn('⧉', 'Duplicar', () => { list.splice(i + 1, 0, structuredClone(step)); rerender(); }),
      iconBtn('🗑', 'Eliminar', () => { list.splice(i, 1); rerender(); })));
  const body = h('div', { class: 'step-body' });
  stepFields(step, body);
  card.append(body);
  return card;
}

function addBar(list) {
  const add = (kind) => { list.push(STEP_DEFS[kind].make()); rerender(); };
  const more = h('select', { class: 'add-more' },
    h('option', { value: '' }, '⚙️ Más…'),
    MORE_KINDS.map((k) => h('option', { value: k }, `${STEP_DEFS[k].icon} ${STEP_DEFS[k].label}`)));
  more.addEventListener('change', () => { if (more.value) add(more.value); });
  return h('div', { class: 'add-bar' },
    h('span', { class: 'small muted' }, '+ Agregar'),
    CHIP_KINDS.map((k) => h('button', { type: 'button', class: 'add-chip', onclick: () => add(k) }, `${STEP_DEFS[k].icon} ${STEP_DEFS[k].label}`)),
    more);
}

function renderSteps(box, list) {
  box.innerHTML = '';
  const wrap = h('div', { class: 'steps' });
  list.forEach((_, i) => wrap.append(stepCard(list, i)));
  if (!list.length) wrap.append(h('p', { class: 'muted small' }, 'Aún no hay mensajes. Agrega el primero 👇'));
  box.append(wrap, addBar(list));
}

// ---------------------------------------------------------------- seguimientos
const guessUnit = (m) => (m && m % 1440 === 0 ? 'd' : m && m % 60 === 0 ? 'h' : 'min');
function fmtDelay(min) {
  const u = guessUnit(min);
  return `${+(min / UNIT[u]).toFixed(2)} ${UNIT_LABELS[u]}`;
}

function renderFollowups() {
  const box = $('fu-box');
  box.innerHTML = '';
  S.current.followups.forEach((fu, i) => {
    if (!units.has(fu)) units.set(fu, guessUnit(fu.delay_minutes));
    const amount = h('input', { type: 'number', min: '1', step: 'any', class: 'num-in', value: +(fu.delay_minutes / UNIT[units.get(fu)]).toFixed(2) });
    const unitSel = h('select', { class: 'unit-sel' }, Object.entries(UNIT_LABELS).map(([k, l]) => h('option', { value: k }, l)));
    unitSel.value = units.get(fu);
    const warnEl = h('div', { class: 'warn-box hidden' }, '⚠️ Pasadas 24 h, WhatsApp solo deja enviar plantillas aprobadas: los mensajes normales de este seguimiento no saldrán. Usa un paso «Plantilla de Meta».');
    const warn = () => {
      const nonTpl = fu.steps.some((s) => MESSAGE_KINDS.includes(s.type) && s.type !== 'template');
      warnEl.classList.toggle('hidden', !(fu.delay_minutes >= 1440 && nonTpl));
    };
    const sync = () => { units.set(fu, unitSel.value); fu.delay_minutes = Number(amount.value || 0) * UNIT[unitSel.value]; warn(); changed(); };
    amount.addEventListener('input', sync);
    unitSel.addEventListener('change', sync);
    const cancel = h('input', { type: 'checkbox' });
    cancel.checked = !!fu.cancel_on_reply;
    cancel.addEventListener('change', () => { fu.cancel_on_reply = cancel.checked; S.dirty = true; });
    warn();
    const stepsBox = h('div');
    renderSteps(stepsBox, fu.steps);
    box.append(h('div', { class: 'fu-card' },
      h('div', { class: 'fu-head' },
        h('span', { class: 'fu-badge' }, `Seguimiento ${i + 1}`), '⏰ Enviar', amount, unitSel, 'después',
        h('span', { class: 'grow' }),
        iconBtn('🗑', 'Eliminar seguimiento', () => { S.current.followups.splice(i, 1); rerender(); })),
      h('div', { class: 'row' },
        h('div', { class: 'grow' }, field('Nombre (para identificarlo)', fu, 'label', { placeholder: 'Ej. Promo S/5' })),
        h('label', { class: 'check' }, cancel, ' Cancelar si el cliente responde')),
      warnEl, stepsBox));
  });
}

// ---------------------------------------------------------------- disparadores
function renderEvents() {
  const t = S.current.triggers;
  $('ev-box').innerHTML = '';
  EVENTS.forEach(([key, icon, title, desc]) => {
    const cb = h('input', { type: 'checkbox' });
    cb.checked = t.events.includes(key);
    const card = h('label', { class: 'ev-card' + (cb.checked ? ' on' : '') }, cb,
      h('span', { class: 'ev-icon' }, icon), h('span', {}, h('b', {}, title), h('br'), h('small', { class: 'muted' }, desc)));
    cb.addEventListener('change', () => {
      t.events = cb.checked ? [...t.events, key] : t.events.filter((e) => e !== key);
      card.classList.toggle('on', cb.checked);
      changed();
    });
    $('ev-box').append(card);
  });
}

function tagInput(box, arr, placeholder) {
  box.innerHTML = '';
  const input = h('input', { placeholder });
  const draw = () => {
    box.querySelectorAll('.tag').forEach((t) => t.remove());
    arr.forEach((v, i) => box.insertBefore(h('span', { class: 'tag' }, v,
      h('button', { type: 'button', title: 'Quitar', onclick: (e) => { e.stopPropagation(); arr.splice(i, 1); draw(); changed(); } }, '×')), input));
  };
  const commit = () => {
    const v = input.value.trim().replace(/,$/, '');
    if (v && !arr.includes(v)) { arr.push(v); changed(); }
    input.value = '';
    draw();
  };
  input.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ',') && input.value.trim()) { e.preventDefault(); commit(); }
    else if (e.key === 'Backspace' && !input.value && arr.length) { arr.pop(); draw(); changed(); }
  });
  input.addEventListener('blur', commit);
  box.append(input);
  box.onclick = () => input.focus();
  draw();
}

// ---------------------------------------------------------------- vista previa
function actionText(st) {
  switch (st.type) {
    case 'set_stage': return `🏷️ Etapa → ${STAGE_LABELS[st.stage] || st.stage}`;
    case 'add_tag': return `🔖 Etiqueta + ${st.tag || '…'}`;
    case 'remove_tag': return `✂️ Etiqueta − ${st.tag || '…'}`;
    case 'set_var': return `🧮 ${st.key} = ${st.value}`;
    case 'note': return `📝 Nota interna: ${st.text || ''}`;
    case 'pause_bot': return '⏸️ Bot pausado: atiende un asesor';
    case 'resume_bot': return '▶️ Bot reactivado';
    case 'cancel_followups': return '🚫 Seguimientos cancelados';
    default: return st.type;
  }
}

function preview() {
  const box = $('preview');
  box.innerHTML = '';
  if (!S.current) return;
  const vars = { ...SAMPLE_VARS };
  const now = new Date().toISOString();
  const draw = (steps) => steps.forEach((st) => {
    if (st.type === 'delay') { box.append(h('div', { class: 'pv-delay' }, `escribiendo… ${st.seconds || 0} s`)); return; }
    if (st.type === 'set_var') vars[st.key] = fillVars(String(st.value ?? ''), vars);
    if (!MESSAGE_KINDS.includes(st.type)) { box.append(h('div', { class: 'pv-action' }, fillVars(actionText(st), vars))); return; }
    const s = fillVars(st, vars);
    const body = ['image', 'document'].includes(s.type) ? s.caption : s.type === 'template' ? s.preview : s.text;
    box.append(renderMessage({ direction: 'out', type: s.type, step: s, body, media_url: s.type === 'image' ? s.url : null, created_at: now }));
  });
  draw(S.current.steps);
  S.current.followups.forEach((fu) => {
    box.append(h('div', { class: 'pv-sep' }, `⏰ ${fmtDelay(fu.delay_minutes)} después · ${fu.label || 'Seguimiento'}`));
    draw(fu.steps);
  });
  if (!box.children.length) box.append(h('div', { class: 'sim-hint' }, 'Agrega mensajes para ver la vista previa'));
}

// ---------------------------------------------------------------- carga / guardado
function rerender() {
  renderSteps($('steps-box'), S.current.steps);
  renderFollowups();
  S.dirty = true;
  preview();
}

function normalize(f) {
  const t = f.triggers = f.triggers || {};
  ['keywords', 'buttons', 'regex', 'ad_ids', 'events'].forEach((k) => { if (!Array.isArray(t[k])) t[k] = []; });
  f.steps = f.steps || [];
  f.followups = f.followups || [];
  f.followups.forEach((fu) => { fu.steps = fu.steps || []; });
  return f;
}

function edit(f) {
  S.current = normalize(structuredClone(f));
  const t = S.current.triggers;
  $('fl-name').value = S.current.name || '';
  $('fl-description').value = S.current.description || '';
  $('fl-priority').value = S.current.priority ?? 10;
  $('fl-active').checked = S.current.active !== false;
  renderEvents();
  tagInput($('kw-box'), t.keywords, 'Ej. precio, cuánto, promo…');
  tagInput($('ad-box'), t.ad_ids, 'ID del anuncio');
  tagInput($('btn-box'), t.buttons, 'btn_precio');
  tagInput($('rx-box'), t.regex, 'Patrón regex');
  if (S.jsonMode) fillJson();
  $('del-flow').disabled = !S.current.id;
  rerender();
  renderList();
  S.dirty = false;
}

function triggerSummary(t) {
  const ev = { ad_click: '📣 anuncio', first_message: '👋 1er mensaje', media: '📷 imagen', fallback: '🤷 no entiende' };
  const parts = (t.events || []).map((e) => ev[e] || e);
  if (t.keywords?.length) parts.push('«' + t.keywords.slice(0, 3).join('», «') + '»');
  if (t.regex?.length) parts.push('patrón');
  return parts.join(' · ') || 'solo por botón';
}

function renderList() {
  $('flow-list').innerHTML = '';
  S.flows.forEach((f) => $('flow-list').append(h('div', {
    class: `flow-item ${S.current?.id === f.id ? 'on' : ''} ${f.active ? '' : 'off'}`,
    onclick: () => { if (S.dirty && !confirm('Tienes cambios sin guardar. ¿Descartarlos?')) return; edit(f); },
  },
  h('div', { class: 'n' }, h('span', {}, f.name), f.followups.length ? h('span', { class: 'badge', title: 'Tiene seguimientos' }, `⏰ ${f.followups.length}`) : null),
  h('div', { class: 't' }, triggerSummary(f.triggers)),
  h('div', { class: 't' }, `${f.steps.filter((s) => MESSAGE_KINDS.includes(s.type)).length} mensajes`))));
}

async function loadFlows(selectId) {
  const d = await api('/api/flows');
  S.flows = d.flows;
  const target = S.flows.find((f) => f.id === selectId) || S.flows[0];
  if (target) edit(target); else newFlow();
}

function newFlow() {
  edit({ id: null, name: '', description: '', priority: 50, active: true, triggers: { keywords: [] }, steps: [{ type: 'text', text: '¡Hola {nombre}! 👋' }], followups: [] });
  $('fl-name').focus();
}

const pretty = (v) => JSON.stringify(v, null, 2);
function fillJson() {
  $('js-triggers').value = pretty(S.current.triggers);
  $('js-steps').value = pretty(S.current.steps);
  $('js-followups').value = pretty(S.current.followups);
}
function readJson() {
  const parse = (id, label) => { try { return JSON.parse($(id).value || 'null'); } catch (e) { throw new Error(`${label}: JSON inválido (${e.message})`); } };
  S.current.triggers = parse('js-triggers', 'Disparadores') || {};
  S.current.steps = parse('js-steps', 'Pasos') || [];
  S.current.followups = parse('js-followups', 'Seguimientos') || [];
  normalize(S.current);
}

function checkSteps(steps, where) {
  steps.forEach((s) => {
    if (s.type === 'buttons') s.buttons.forEach((b) => {
      if (!b.title) throw new Error(`${where}: hay un botón sin texto`);
      if (!b.id) throw new Error(`${where}: elige qué flujo abre el botón «${b.title}»`);
    });
    if (s.type === 'list') (s.sections || []).forEach((sec) => (sec.rows || []).forEach((r) => {
      if (!r.title) throw new Error(`${where}: hay una opción de lista sin texto`);
      if (!r.id) throw new Error(`${where}: elige qué flujo abre la opción «${r.title}»`);
    }));
    if (['image', 'document'].includes(s.type) && !s.url) throw new Error(`${where}: falta elegir la ${s.type === 'image' ? 'imagen' : 'el PDF'}`);
    if (['text', 'buttons', 'list'].includes(s.type) && !(s.text || '').trim()) throw new Error(`${where}: hay un mensaje vacío`);
  });
}

function buildPayload() {
  if (S.jsonMode) readJson();
  const f = S.current;
  const triggers = Object.fromEntries(Object.entries(f.triggers).filter(([, v]) => (Array.isArray(v) ? v.length : v)));
  if (!f.name?.trim()) throw new Error('Ponle un nombre al flujo');
  checkSteps(f.steps, 'Mensajes');
  f.followups.forEach((fu, i) => checkSteps(fu.steps, `Seguimiento ${i + 1}`));
  return { name: f.name.trim(), description: f.description || '', priority: Number(f.priority || 0), active: f.active !== false, triggers, steps: f.steps, followups: f.followups };
}

// ---------------------------------------------------------------- eventos
$('fl-name').addEventListener('input', (e) => { S.current.name = e.target.value; S.dirty = true; });
$('fl-description').addEventListener('input', (e) => { S.current.description = e.target.value; S.dirty = true; });
$('fl-priority').addEventListener('input', (e) => { S.current.priority = Number(e.target.value); S.dirty = true; });
$('fl-active').addEventListener('change', (e) => { S.current.active = e.target.checked; S.dirty = true; });
$('add-fu').addEventListener('click', () => {
  const last = S.current.followups.at(-1);
  S.current.followups.push({ delay_minutes: last ? last.delay_minutes * 2 : 30, label: '', cancel_on_reply: false, steps: [{ type: 'text', text: '' }] });
  rerender();
});

$('save-flow').addEventListener('click', async () => {
  try {
    const body = buildPayload();
    const d = S.current.id
      ? await api(`/api/flows/${S.current.id}`, { method: 'PUT', body })
      : await api('/api/flows', { method: 'POST', body });
    S.dirty = false;
    toast('✅ Flujo guardado');
    loadFlows(d.flow.id);
  } catch (err) { toast(err.message, 'error'); }
});

$('new-flow').addEventListener('click', () => {
  if (S.dirty && !confirm('Tienes cambios sin guardar. ¿Descartarlos?')) return;
  newFlow();
});

$('dup-flow').addEventListener('click', () => {
  try {
    if (S.jsonMode) readJson();
    edit({ ...structuredClone(S.current), id: null, name: `${S.current.name} (copia)` });
    S.dirty = true;
    toast('Copia lista: cámbiale el nombre y guarda');
  } catch (err) { toast(err.message, 'error'); }
});

$('del-flow').addEventListener('click', async () => {
  if (!S.current?.id || !confirm(`¿Eliminar el flujo «${S.current.name}»?`)) return;
  await api(`/api/flows/${S.current.id}`, { method: 'DELETE' });
  S.dirty = false;
  toast('Flujo eliminado');
  loadFlows();
});

$('json-toggle').addEventListener('click', () => {
  try {
    if (S.jsonMode) { readJson(); S.jsonMode = false; edit(S.current); S.dirty = true; }
    else { S.jsonMode = true; fillJson(); }
    $('visual-editor').classList.toggle('hidden', S.jsonMode);
    $('json-editor').classList.toggle('hidden', !S.jsonMode);
  } catch (err) { toast(err.message, 'error'); }
});
['js-triggers', 'js-steps', 'js-followups'].forEach((id) => $(id).addEventListener('input', () => {
  try { readJson(); S.dirty = true; preview(); } catch (_) { /* JSON a medio escribir */ }
}));

$('reset-flows').addEventListener('click', async () => {
  if (!confirm('Esto borra TODOS tus flujos y carga los de ejemplo. ¿Continuar?')) return;
  await api('/api/flows/reset', { method: 'POST' });
  S.dirty = false;
  toast('Flujos de ejemplo restaurados');
  loadFlows();
});

document.addEventListener('click', (e) => {
  const dd = e.target.closest('.dropdown');
  document.querySelectorAll('.dropdown.open').forEach((x) => { if (x !== dd) x.classList.remove('open'); });
  if (e.target.closest('[data-dd]')) dd.classList.toggle('open');
  else if (e.target.closest('.dd-menu button')) dd.classList.remove('open');
});
window.addEventListener('beforeunload', (e) => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });

loadFlows();
