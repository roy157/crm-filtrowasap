// Resumen: números clave, embudo por etapa, flujos más usados y resultados por anuncio.
const pct = (a, b) => (b ? `${Math.round((a / b) * 100)}%` : '—');

async function load() {
  const d = await api('/api/stats/summary');
  const st = d.stages;
  const sold = st.cliente || 0;
  const tiles = [
    ['Contactos', d.total, `${d.new_7d} nuevos en 7 días`, '/panel'],
    ['Desde anuncios', d.from_ads, pct(d.from_ads, d.total) + ' del total', '/panel'],
    ['Pagos por validar', st.pago_pendiente || 0, 'revisa y envía el reporte', '/panel?stage=pago_pendiente'],
    ['Clientes', sold, `conversión ${pct(sold, d.total)}`, '/panel?stage=cliente'],
    ['Seguimientos programados', d.scheduled_pending, 'por enviarse', '/panel'],
    ['Mensajes 7 días', d.messages_in_7d + d.messages_out_7d, `${d.messages_in_7d} recibidos · ${d.messages_out_7d} enviados`, '/panel'],
  ];
  $('kpis').innerHTML = tiles.map(([label, value, sub, href]) => `
    <a class="kpi" href="${href}"><span class="kpi-label">${label}</span>
      <span class="kpi-value">${value.toLocaleString('es-PE')}</span><span class="kpi-sub">${esc(sub)}</span></a>`).join('');

  const max = Math.max(1, ...Object.values(st));
  $('funnel').innerHTML = Object.entries(STAGE_LABELS).map(([k, l]) => `
    <a class="bar-row" href="/panel?stage=${k}" title="${l}: ${st[k] || 0} contactos (${pct(st[k] || 0, d.total)})">
      <span class="bar-label">${l}</span>
      <span class="bar-track"><span class="bar" style="width:${((st[k] || 0) / max) * 100}%"></span></span>
      <span class="bar-value">${st[k] || 0}</span>
    </a>`).join('');

  const fmax = Math.max(1, ...d.flows.map((f) => f.count));
  $('flows-usage').innerHTML = d.flows.length ? d.flows.map((f) => `
    <div class="bar-row" title="${esc(f.name)}: ${f.count} mensajes">
      <span class="bar-label wide">${esc(f.name)}</span>
      <span class="bar-track"><span class="bar" style="width:${(f.count / fmax) * 100}%"></span></span>
      <span class="bar-value">${f.count}</span>
    </div>`).join('') : '<p class="muted small">Aún no se enviaron mensajes.</p>';

  $('ads').innerHTML = `<thead><tr><th>Anuncio</th><th>Llegaron</th><th>Interesados</th><th>Pago pendiente</th><th>Clientes</th><th>Conversión</th></tr></thead>
    <tbody>${d.ads.length ? d.ads.map((a) => `<tr>
      <td><div class="ad-cell">${a.image_url ? `<img src="${esc(a.image_url)}" alt="">` : ''}<div><b>${esc(a.headline)}</b><br><small class="muted">ID ${esc(a.ad_id)}</small></div></div></td>
      <td>${a.leads}</td><td>${a.interesado}</td><td>${a.pago_pendiente}</td><td><b>${a.cliente}</b></td><td>${pct(a.cliente, a.leads)}</td>
    </tr>`).join('') : '<tr><td colspan="6" class="muted">Aún no llegan clientes desde anuncios. Pruébalo con «📣 Simular clic en anuncio» en el simulador.</td></tr>'}</tbody>`;
}

load().catch((e) => toast(e.message, 'error'));
setInterval(() => load().catch(() => {}), 15000);
