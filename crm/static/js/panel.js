// Bandeja del CRM: lista de chats, conversación y ficha del contacto.
const S = { stage: new URLSearchParams(location.search).get('stage') || '', q: '', selected: null, lastId: 0, contact: null, polling: false };

async function loadContacts() {
  try {
    const d = await api('/api/contacts?' + new URLSearchParams({ q: S.q, stage: S.stage }));
    renderStageFilter(d.stats, d.total);
    renderContacts(d.contacts);
  } catch (e) { console.error(e); }
}

function renderStageFilter(stats, total) {
  const items = [['', 'Todos', total], ...Object.keys(STAGE_LABELS).map((k) => [k, STAGE_LABELS[k], stats[k] || 0])];
  $('stage-filter').innerHTML = items
    .map(([k, l, n]) => `<button class="chip ${S.stage === k ? 'on' : ''}" data-stage="${k}">${l} <b>${n}</b></button>`)
    .join('');
}

function renderContacts(contacts) {
  const box = $('contact-list');
  if (!contacts.length) {
    box.innerHTML = '<p class="muted small" style="padding:12px">No hay conversaciones todavía.</p>';
    return;
  }
  box.innerHTML = contacts.map((c) => `
    <div class="contact ${c.id === S.selected ? 'on' : ''}" data-id="${c.id}">
      <div class="avatar">${esc((c.display_name || '?').replace('+', '').charAt(0).toUpperCase())}</div>
      <div class="grow">
        <div class="top"><span class="name">${esc(c.display_name)}</span><span class="time">${fmtShort(c.last_message_at)}</span></div>
        <div class="bottom">
          <span class="preview">${esc(c.last_preview)}</span>
          ${c.unread && c.id !== S.selected ? `<span class="unread">${c.unread}</span>` : ''}
        </div>
        <div class="chips" style="margin-top:4px">${stageChip(c.stage)}
          ${c.is_test ? '<span class="badge">🧪 prueba</span>' : ''}
          ${c.source === 'anuncio' ? '<span class="badge">📣 anuncio</span>' : ''}
          ${!c.bot_enabled ? '<span class="badge warn">⏸ bot</span>' : ''}</div>
      </div>
    </div>`).join('');
}

async function selectContact(id) {
  S.selected = id;
  S.lastId = 0;
  $('messages').innerHTML = '';
  $('chat-empty').classList.add('hidden');
  $('chat').classList.remove('hidden');
  $('detail').classList.remove('hidden');
  document.querySelector('.crm').classList.add('has-chat');
  const d = await api(`/api/contacts/${id}`);
  fillForm(d.contact);
  await pollMessages(true);
  loadContacts();
}

function fillForm(c) {
  $('f-name').value = c.name || '';
  $('f-stage').value = c.stage;
  $('f-tags').value = (c.tags || []).join(', ');
  $('f-notes').value = c.notes || '';
}

function renderDynamic(c, scheduled) {
  S.contact = c;
  $('chat-name').textContent = c.display_name;
  $('chat-sub').innerHTML = `+${esc(c.wa_id)} · ${stageChip(c.stage)}${c.is_test ? ' · 🧪 contacto de prueba' : ''}`;
  const wb = $('window-badge');
  if (c.window_open) { wb.className = 'badge ok'; wb.textContent = `Ventana 24 h abierta · cierra ${fmtRelative(c.window_expires_at)}`; }
  else { wb.className = 'badge bad'; wb.textContent = 'Ventana cerrada: solo plantillas'; }
  if (document.activeElement !== $('f-stage')) $('f-stage').value = c.stage;
  $('bot-state').innerHTML = c.bot_enabled
    ? '<span class="badge ok">🤖 Bot respondiendo</span>'
    : '<span class="badge warn">⏸ Bot pausado: responde un asesor</span>';
  $('toggle-bot').textContent = c.bot_enabled ? 'Pausar bot (tomar el chat)' : 'Reactivar bot';
  $('sched-list').innerHTML = renderScheduled(scheduled, { onCancel: true });
  const data = Object.entries(c.data || {});
  const ref = c.referral;
  $('vars').innerHTML = `<dl class="kv">
    <dt>Origen</dt><dd>${c.source === 'anuncio' ? '📣 Anuncio' : 'Orgánico'}</dd>
    ${ref ? `<dt>Anuncio</dt><dd>${esc(ref.headline || '')}<br><small class="muted">ID ${esc(ref.source_id || '')}</small></dd>` : ''}
    ${data.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
    <dt>Creado</dt><dd>${fmtDateTime(c.created_at)}</dd></dl>`;
}

async function pollMessages(scrollToEnd = false) {
  if (!S.selected || S.polling) return;
  S.polling = true;
  const id = S.selected;
  try {
    const d = await api(`/api/contacts/${id}/messages?after=${S.lastId}`);
    if (id !== S.selected) return;
    const box = $('messages');
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    d.messages.forEach((m) => {
      box.appendChild(renderMessage(m, { mine: m.direction === 'out', showMeta: true }));
      S.lastId = Math.max(S.lastId, m.id);
    });
    if (d.messages.length && (nearBottom || scrollToEnd)) box.scrollTop = box.scrollHeight;
    renderDynamic(d.contact, d.scheduled);
  } catch (e) {
    console.error(e);
  } finally {
    S.polling = false;
  }
}

async function patchContact(body) {
  const d = await api(`/api/contacts/${S.selected}`, { method: 'PATCH', body });
  await pollMessages();
  loadContacts();
  return d.contact;
}

async function loadFlows() {
  const d = await api('/api/flows');
  $('flow-select').innerHTML = d.flows.map((f) => `<option value="${f.id}">${esc(f.name)}</option>`).join('');
}

// ---------------------------------------------------------------- eventos
$('f-stage').innerHTML = Object.entries(STAGE_LABELS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('');

$('stage-filter').addEventListener('click', (e) => {
  const chip = e.target.closest('[data-stage]');
  if (!chip) return;
  S.stage = chip.dataset.stage;
  loadContacts();
});

let searchTimer;
$('search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { S.q = e.target.value; loadContacts(); }, 250);
});

$('contact-list').addEventListener('click', (e) => {
  const item = e.target.closest('.contact');
  if (item) selectContact(Number(item.dataset.id));
});

$('back').addEventListener('click', () => {
  document.querySelector('.crm').classList.remove('has-chat');
});

$('composer').addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = $('composer-text').value.trim();
  if (!text || !S.selected) return;
  try {
    const d = await api(`/api/contacts/${S.selected}/send`, { method: 'POST', body: { text, pause_bot: $('pause-on-send').checked } });
    $('composer-text').value = '';
    if (d.message.status === 'skipped' || d.message.status === 'failed') toast(d.message.error, 'error');
    await pollMessages(true);
    loadContacts();
  } catch (err) { toast(err.message, 'error'); }
});

$('composer-text').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('composer').requestSubmit(); }
});

$('save-contact').addEventListener('click', async () => {
  try {
    const c = await patchContact({ name: $('f-name').value, stage: $('f-stage').value, tags: $('f-tags').value, notes: $('f-notes').value });
    fillForm(c);
    toast('Contacto guardado');
  } catch (err) { toast(err.message, 'error'); }
});

$('toggle-bot').addEventListener('click', async () => {
  try { await patchContact({ bot_enabled: !S.contact.bot_enabled }); } catch (err) { toast(err.message, 'error'); }
});

$('run-flow').addEventListener('click', async () => {
  try {
    await api(`/api/contacts/${S.selected}/run_flow`, { method: 'POST', body: { flow_id: Number($('flow-select').value) } });
    toast('Flujo enviado');
  } catch (err) { toast(err.message, 'error'); }
});

$('sched-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-cancel]');
  if (!btn) return;
  try { await api(`/api/scheduled/${btn.dataset.cancel}/cancel`, { method: 'POST' }); pollMessages(); } catch (err) { toast(err.message, 'error'); }
});

$('delete-contact').addEventListener('click', async () => {
  if (!S.contact || !confirm(`¿Eliminar a ${S.contact.display_name} y todo su historial?`)) return;
  await api(`/api/contacts/${S.selected}`, { method: 'DELETE' });
  S.selected = null;
  $('chat').classList.add('hidden');
  $('detail').classList.add('hidden');
  $('chat-empty').classList.remove('hidden');
  document.querySelector('.crm').classList.remove('has-chat');
  loadContacts();
});

loadContacts();
loadFlows();
setInterval(loadContacts, 4000);
setInterval(() => pollMessages(), 2000);
