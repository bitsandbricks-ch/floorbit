'use strict';

// Dashboard: tiles from plugins. Each widget is data (floorbit/plugins/widgets.py), drawn here
// with textContent only, so nothing a plugin returns is ever treated as HTML.
(() => {
  const grid = document.getElementById('db-grid');
  const empty = document.getElementById('db-empty');
  if (!grid) return;
  const SVG = 'http://www.w3.org/2000/svg';

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children) if (c != null && c !== '') node.append(c);
    return node;
  }

  async function getJSON(url, options) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function sparkline(points, min, max) {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('class', 'db-spark');
    svg.setAttribute('viewBox', '0 0 100 30');
    svg.setAttribute('preserveAspectRatio', 'none');
    if (points.length < 2) return svg;
    const lo = min ?? Math.min(...points);
    const hi = max ?? Math.max(...points);
    const span = hi - lo || 1;
    const path = document.createElementNS(SVG, 'polyline');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.5');
    path.setAttribute('vector-effect', 'non-scaling-stroke');
    path.setAttribute('points', points.map((p, i) =>
      `${(i / (points.length - 1)) * 100},${30 - ((p - lo) / span) * 28 - 1}`).join(' '));
    svg.append(path);
    return svg;
  }

  function body(w) {
    switch (w.type) {
      case 'stat':
        return el('div', { class: 'db-stat ' + (w.tone || '') }, String(w.value ?? '–'), w.unit ? el('small', {}, w.unit) : '');
      case 'status':
        return el('ul', { class: 'db-items' }, ...w.items.map((i) => el('li', {},
          el('span', { class: 'db-dot ' + i.state, title: i.state }),
          el('span', { class: 'db-label' }, i.label),
          el('span', { class: 'db-detail' }, i.detail))));
      case 'list':
        return el('ul', { class: 'db-items' }, ...w.items.map((i) => el('li', {},
          el('span', { class: 'db-label' }, i.label), el('span', { class: 'db-detail ' + (i.tone || '') }, i.value))));
      case 'table':
        return el('table', { class: 'db-table' },
          el('thead', {}, el('tr', {}, ...w.columns.map((c) => el('th', {}, c.label)))),
          el('tbody', {}, ...w.rows.map((r) => el('tr', {}, ...w.columns.map((c) => el('td', {}, r[c.key]))))));
      case 'sparkline':
        return el('div', {}, w.value != null ? el('div', { class: 'db-stat' }, String(w.value), w.unit ? el('small', {}, w.unit) : '') : '',
          sparkline(w.points, w.min, w.max));
      default:
        return el('p', { class: 'db-err' }, 'This tile can’t be drawn.');
    }
  }

  function widgetTile(t) {
    const content = el('div', {}, el('p', { class: 'db-sub' }, 'Loading…'));
    const tile = el('section', { class: 'st-card db-tile' + (t.size === 'wide' ? ' wide' : '') },
      el('h2', {}, t.label, el('span', { class: 'db-from' }, t.plugin_name)), content);
    async function load() {
      try {
        const w = await getJSON(t.url);
        content.replaceChildren(body(w), w.sub ? el('p', { class: 'db-sub' }, w.sub) : '',
          w.link ? el('a', { class: 'db-link', href: w.link }, 'Details') : '');
      } catch (e) {
        content.replaceChildren(el('p', { class: 'db-err' }, '✕ ' + e.message));
      }
    }
    load();
    setInterval(() => { if (!document.hidden) load(); }, Math.max(10, t.refresh) * 1000);
    return tile;
  }

  function actionTile(t) {
    const result = el('p', { class: 'db-sub', role: 'status' });
    const button = el('button', { class: 'st-btn' + (t.danger ? ' st-btn-danger' : ' st-btn-primary'), type: 'button',
      onclick: async () => {
        if (t.danger && !window.confirm(`${t.label}: are you sure?`)) return;
        button.disabled = true;
        result.textContent = 'Working…';
        try {
          const r = await getJSON(t.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
          result.textContent = '✓ ' + r.message;
        } catch (e) { result.textContent = '✕ ' + e.message; } finally { button.disabled = false; }
      } }, t.label);
    return el('section', { class: 'st-card db-tile' },
      el('h2', {}, t.plugin_name), button, result);
  }

  getJSON('/api/dashboard').then((data) => {
    const tiles = data.tiles || [];
    empty.classList.toggle('hidden', tiles.length > 0);
    grid.replaceChildren(...tiles.map((t) => (t.kind === 'action' ? actionTile(t) : widgetTile(t))));
  }).catch((e) => { empty.classList.remove('hidden'); empty.textContent = '✕ ' + e.message; });
})();
