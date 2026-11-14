'use strict';

// Settings > Audit log: loads GET /api/settings/audit page by page, newest first.
// The filters go into the URL too, so a filtered view can be shared or reloaded.

(() => {
  const form = document.getElementById('au-filters');
  const rowsEl = document.getElementById('au-rows');
  const countEl = document.getElementById('au-count');
  const moreBtn = document.getElementById('au-more');
  const csvLink = document.getElementById('au-csv');
  const PAGE = 100;
  let offset = 0;
  let timer = null;

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function filters() {
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(form)) if (String(v).trim()) p.set(k, String(v).trim());
    return p;
  }

  function when(iso) {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' });
  }

  function row(e) {
    const tr = el('tr');
    const t = el('td', 'au-time', when(e.time));
    t.title = e.time;
    tr.append(t);
    tr.append(el('td', 'au-user' + (e.user ? '' : ' none'), e.user || 'nobody signed in'));
    const area = el('td');
    area.append(el('span', 'au-area', e.area));
    tr.append(area);
    const what = el('td', 'au-what' + (e.ok === false ? ' au-failed' : ''), e.action);
    if (e.target) what.append(el('span', 'au-target', e.target));
    tr.append(what);
    tr.append(el('td', 'au-fields au-fields-cell', (e.fields || []).join(', ')));
    return tr;
  }

  async function load(append = false) {
    const p = filters();
    if (!append) {
      offset = 0;
      history.replaceState(null, '', p.toString() ? `?${p}` : location.pathname);
      csvLink.href = '/api/settings/audit.csv' + (p.toString() ? `?${p}` : '');
    }
    p.set('limit', PAGE);
    p.set('offset', offset);
    try {
      const res = await fetch('/api/settings/audit?' + p);
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || `Could not load the audit log (${res.status})`);
      if (!append) rowsEl.replaceChildren();
      rowsEl.append(...body.entries.map(row));
      offset += body.entries.length;
      if (!body.total) {
        const td = el('td', 'au-empty', 'Nothing logged yet, or nothing matches these filters.');
        td.colSpan = 5;
        const tr = el('tr'); tr.append(td); rowsEl.replaceChildren(tr);
      }
      countEl.textContent = body.total ? `Showing ${offset} of ${body.total}` : '';
      moreBtn.classList.toggle('hidden', offset >= body.total);
    } catch (err) {
      countEl.textContent = err.message;
    }
  }

  // Start from filters in the URL.
  for (const [k, v] of new URLSearchParams(location.search)) {
    if (form.elements[k]) form.elements[k].value = v;
  }
  form.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => load(), 250); });
  form.addEventListener('submit', (e) => { e.preventDefault(); load(); });
  moreBtn.addEventListener('click', () => load(true));
  load();
})();
