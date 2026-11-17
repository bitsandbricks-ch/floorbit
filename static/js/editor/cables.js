// Floor plan editor: cables on the plan (floorbit/cable_plan.py). Network cables from switch ports
// to seats, uplinks between switches and power from distribution boards, each on its layer
// (Network, Electrical). A selected cable shows its bends: click the cable to add one, drag one to
// move it (it snaps to the grid), double-click one to remove it. Moved bends pin the route, so it
// stays when the cable's seat changes. The Cable tool (C) draws new cables.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

let cablePlan = { cables: [], panels: [], panel_names: [], auto: true };
let selectedCable = null;    // key
let cableDrag = null;        // { key, index, before, moved }
let cableDraft = null;       // the first click of the Cable tool: { kind, from }
let cablePlanTimer = null;
const cablesSvg = $('cables-svg');
const CABLE_SPEED_W = { 1: 1.6, 10: 2.4, 25: 2.8, 40: 3.2, 100: 3.6 };
const CABLE_MEDIA = { copper: 'Copper', fiber: 'Fiber', dac: 'DAC', power: 'Power' };

const cableEditable = () => !document.body.classList.contains('read-only');
const cableByKey = (key) => cablePlan.cables.find(c => c.key === key);

async function loadCablePlan() {
  try {
    const q = currentHall ? `?hall=${encodeURIComponent(currentHall)}` : '';
    cablePlan = await api('GET', `/api/cable-plan${q}`);
  } catch (_) {
    return;   // extra information; the floor plan works without it
  }
  if (selectedCable && !cableByKey(selectedCable)) selectedCable = null;
  if (!cableDrag) renderCables();
}

// Positions on the server follow blocks and switches: ask again shortly after the plan changes.
function scheduleCablePlan() {
  if (cableDrag) return;
  clearTimeout(cablePlanTimer);
  cablePlanTimer = setTimeout(loadCablePlan, 250);
}

// ── Drawing ──────────────────────────────────────────────────────────────────────────
function cablePx(p) {
  return [p[0] / 100 * wrapper.offsetWidth, p[1] / 100 * wrapper.offsetHeight];
}

function cablePath(points, corners) {
  const pts = points.map(cablePx);
  if (pts.length < 2) return '';
  const d = [`M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`];
  for (let i = 1; i < pts.length; i++) {
    const [x, y] = pts[i];
    if (corners !== 'round' || i === pts.length - 1) { d.push(`L${x.toFixed(1)} ${y.toFixed(1)}`); continue; }
    // A round corner: stop short of the bend, curve through it, carry on.
    const [px, py] = pts[i - 1], [nx, ny] = pts[i + 1];
    const lin = Math.hypot(x - px, y - py), lout = Math.hypot(nx - x, ny - y);
    const r = Math.min(12, lin / 2, lout / 2);
    if (!r) { d.push(`L${x.toFixed(1)} ${y.toFixed(1)}`); continue; }
    const ax = x - (x - px) / lin * r, ay = y - (y - py) / lin * r;
    const bx = x + (nx - x) / lout * r, by = y + (ny - y) / lout * r;
    d.push(`L${ax.toFixed(1)} ${ay.toFixed(1)} Q${x.toFixed(1)} ${y.toFixed(1)} ${bx.toFixed(1)} ${by.toFixed(1)}`);
  }
  return d.join(' ');
}

function cableTitle(c) {
  const parts = [];
  if (c.kind === 'lan') parts.push(`${c.ref.switch} ${c.ref.port} to seat ${c.ref.seat}`);
  else if (c.kind === 'uplink') parts.push(c.label);
  else parts.push(`Circuit ${c.label}`);
  if (c.kind === 'lan' && c.label) parts.push(c.label);
  if (c.via) parts.push(`through ${c.via}`);
  if (c.media && c.media !== 'power') parts.push(CABLE_MEDIA[c.media] || c.media);
  if (c.speed) parts.push(`${c.speed} Gbit/s`);
  if (c.kind === 'lan' && c.ref.source === 'watch') parts.push('from the port description');
  if (c.manual) parts.push('routed by hand');
  return parts.join(' · ');
}

function renderCables() {
  if (!cablesSvg) return;
  const w = wrapper.offsetWidth, h = wrapper.offsetHeight;
  cablesSvg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  cablesSvg.style.setProperty('--cable-k', view.k);
  const out = [];
  const shown = cablePlan.cables.filter(c => !hiddenMarkLayers.has(c.layer));
  // The selected cable last, so its bends sit on top.
  shown.sort((a, b) => (a.key === selectedCable) - (b.key === selectedCable));
  for (const c of shown) {
    const d = cablePath(c.points, c.corners);
    const sel = c.key === selectedCable;
    const width = c.kind === 'power' ? 2.4 : CABLE_SPEED_W[c.speed] || 1.6;
    out.push(`<g class="cable cable-${c.kind} media-${c.media || 'unknown'}${sel ? ' selected' : ''}${c.manual ? ' manual' : ''}" data-cable="${escHtml(c.key)}">` +
      `<title>${escHtml(cableTitle(c))}</title>` +
      `<path class="cable-hit" d="${d}"/>` +
      `<path class="cable-line" d="${d}" style="stroke-width:${width}px"/>`);
    if (sel) {
      c.points.forEach((p, i) => {
        const [x, y] = cablePx(p);
        const end = i === 0 || i === c.points.length - 1;
        out.push(`<circle class="${end ? 'cable-end' : 'cable-bend'}" cx="${x}" cy="${y}" r="5" data-index="${i}"/>`);
      });
    }
    out.push('</g>');
  }
  for (const p of cablePlan.panels || []) {
    if (p.x == null || hiddenMarkLayers.has('network')) continue;
    const [x, y] = cablePx([p.x, p.y]);
    out.push(`<g class="cable-panel" data-patch-panel="${escHtml(p.name)}" transform="translate(${x} ${y})">` +
      `<title>Patch panel ${escHtml(p.name)}</title><rect x="-14" y="-6" width="28" height="12" rx="2"/>` +
      `<path d="M-9 0h0M-4 0h0M1 0h0M6 0h0"/><text y="-10">${escHtml(p.name)}</text></g>`);
  }
  if (cableDraft && cableDraft.to) {
    const [ax, ay] = cablePx(cableDraft.at), [bx, by] = cablePx(cableDraft.to);
    out.push(`<path class="cable-draft" d="M${ax} ${ay} L${bx} ${by}"/>`);
  }
  cablesSvg.innerHTML = out.join('');
}

function selectCable(key) {
  if (selection.size || selectedId) deselectAll();
  if (typeof selectedMark !== 'undefined' && selectedMark) clearMarkSelection();
  selectedCable = key;
  renderCables();
}

// ── Saving a route ───────────────────────────────────────────────────────────────────
// What the server keeps about a cable's drawing, to put back on undo.
function routeState(c) {
  if (!c.drawn && !c.manual) return null;
  return { points: c.manual ? c.points.slice(1, -1) : null, corners: c.corners };
}

async function saveRoute(key, before, after, label) {
  await api('PUT', '/api/cable-plan/routes', { routes: { [key]: after } });
  pushHistory({
    label,
    undo: async () => { await api('PUT', '/api/cable-plan/routes', { routes: { [key]: before } }); await loadCablePlan(); },
    redo: async () => { await api('PUT', '/api/cable-plan/routes', { routes: { [key]: after } }); await loadCablePlan(); },
  });
  await loadCablePlan();
}

function snapPoint(p) { return [snapToGrid(p.x), snapToGrid(p.y)]; }

// The segment of a cable nearest to a point on the plan (in px).
function nearestSegment(points, at) {
  const pts = points.map(cablePx);
  let best = 0, bestD = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const len2 = (bx - ax) ** 2 + (by - ay) ** 2 || 1;
    const t = Math.max(0, Math.min(1, ((at[0] - ax) * (bx - ax) + (at[1] - ay) * (by - ay)) / len2));
    const d = Math.hypot(at[0] - (ax + t * (bx - ax)), at[1] - (ay + t * (by - ay)));
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

function onCableMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  const g = e.target.closest('[data-cable]');
  if (!g) return;
  e.stopPropagation();
  e.preventDefault();
  const c = cableByKey(g.dataset.cable);
  if (!c) return;
  if (selectedCable !== c.key) { selectCable(c.key); return; }
  if (!cableEditable()) return;
  const p = clientToPercent(e.clientX, e.clientY);
  if (!p) return;
  const before = routeState(c);
  let index;
  if (e.target.classList.contains('cable-bend')) {
    index = Number(e.target.dataset.index);
  } else if (e.target.classList.contains('cable-end')) {
    return;   // the ends belong to the switch, seat or board
  } else {
    const seg = nearestSegment(c.points, cablePx([p.x, p.y]));
    index = seg + 1;
    c.points.splice(index, 0, snapPoint(p));
  }
  cableDrag = { key: c.key, index, before, moved: !e.target.classList.contains('cable-bend') };
  renderCables();
  document.addEventListener('mousemove', onCableDragMove);
  document.addEventListener('mouseup', onCableDragUp, { once: true });
}

function onCableDragMove(e) {
  const c = cableDrag && cableByKey(cableDrag.key);
  const p = clientToPercent(e.clientX, e.clientY);
  if (!c || !p) return;
  c.points[cableDrag.index] = snapPoint(p);
  cableDrag.moved = true;
  renderCables();
}

async function onCableDragUp() {
  document.removeEventListener('mousemove', onCableDragMove);
  const drag = cableDrag;
  cableDrag = null;
  const c = drag && cableByKey(drag.key);
  if (!c || !drag.moved) return;
  try {
    await saveRoute(c.key, drag.before, { points: c.points.slice(1, -1), corners: c.corners }, 'route a cable');
  } catch (err) {
    toastError('Could not save the route', err);
    loadCablePlan();
  }
}

async function onCableDblClick(e) {
  const bend = e.target.closest('.cable-bend');
  if (!bend || !cableEditable()) return;
  e.stopPropagation();
  const c = cableByKey(bend.closest('[data-cable]').dataset.cable);
  if (!c) return;
  const before = routeState(c);
  const bends = c.points.slice(1, -1);
  bends.splice(Number(bend.dataset.index) - 1, 1);
  // No bends left: back to the automatic route, still drawn.
  try {
    await saveRoute(c.key, before, { points: bends.length ? bends : null, corners: c.corners }, 'remove a bend');
  } catch (err) { toastError('Could not save the route', err); }
}

async function setCableCorners(key, corners) {
  const c = cableByKey(key);
  if (!c) return;
  const before = routeState(c);
  try {
    await saveRoute(key, before, { points: c.manual ? c.points.slice(1, -1) : null, corners }, `${corners} corners`);
  } catch (err) { toastError('Could not change the corners', err); }
}

async function resetCableRoute(key) {
  const c = cableByKey(key);
  if (!c) return;
  try {
    await saveRoute(key, routeState(c), { points: null, corners: c.corners }, 'automatic route');
  } catch (err) { toastError('Could not reset the route', err); }
}

// ── Deleting a cable: the cable itself (seat cable, uplink) or the circuit's feed ─────────
async function deleteCable(key) {
  const c = cableByKey(key);
  if (!c || !cableEditable()) return;
  if (c.kind === 'lan' && c.ref.source !== 'floorbit') {
    toast(c.ref.source === 'import' ? 'This cable comes from NetBox: change it there'
      : 'This cable comes from the port description on the switch. Turn off automatic cabling in Settings to hide it.');
    return;
  }
  try {
    if (c.kind === 'lan') {
      const cable = (await api('GET', `/api/cables?ids=${encodeURIComponent(c.ref.cable)}`)).cables[0];
      await api('DELETE', `/api/cables/${c.ref.cable}`);
      await api('PUT', '/api/cable-plan/routes', { routes: { [key]: null } });
      const ref = { id: c.ref.cable };
      pushHistory({
        label: 'delete a cable',
        undo: async () => {
          const made = await api('POST', '/api/cables', cable);
          ref.id = made.id;
          await api('PUT', '/api/cable-plan/routes', { routes: { [key]: routeState(c) || { points: null } } });
          await loadCablePlan();
        },
        redo: async () => { await api('DELETE', `/api/cables/${ref.id}`); await loadCablePlan(); },
      });
    } else if (c.kind === 'uplink') {
      const link = (await api('GET', '/api/links')).links.find(l => l.id === c.ref.link);
      await api('DELETE', `/api/links/${c.ref.link}`);
      const ref = { id: c.ref.link };
      pushHistory({
        label: 'delete an uplink',
        undo: async () => { ref.id = (await api('POST', '/api/links', link)).id; await loadCablePlan(); },
        redo: async () => { await api('DELETE', `/api/links/${ref.id}`); await loadCablePlan(); },
      });
    } else {
      const circuit = (await api('GET', '/api/power')).circuits.find(x => x.id === c.ref.circuit);
      if (!circuit) return;
      const before = { blocks: circuit.blocks, switches: circuit.switches };
      const after = c.ref.block ? { blocks: circuit.blocks.filter(f => f.block !== c.ref.block) }
                                : { switches: circuit.switches.filter(s => s !== c.ref.switch) };
      await api('PATCH', `/api/power/circuits/${circuit.id}`, after);
      pushHistory({
        label: 'delete a power cable',
        undo: async () => { await api('PATCH', `/api/power/circuits/${circuit.id}`, before); await loadCablePlan(); },
        redo: async () => { await api('PATCH', `/api/power/circuits/${circuit.id}`, after); await loadCablePlan(); },
      });
      if (typeof loadPowerMarkers === 'function') loadPowerMarkers();
    }
    selectedCable = null;
    await loadCablePlan();
    toast('Cable deleted · Ctrl+Z brings it back');
  } catch (err) { toastError('Could not delete the cable', err); }
}

// The right-click menu of a cable (menus.js asks).
function cableMenuEntries(key) {
  const c = cableByKey(key);
  if (!c) return [];
  const items = [];
  if (cableEditable()) {
    items.push(c.corners === 'round'
      ? { label: 'Square corners', run: () => setCableCorners(key, 'square') }
      : { label: 'Round corners', run: () => setCableCorners(key, 'round') });
    if (c.manual) items.push({ label: 'Back to the automatic route', run: () => resetCableRoute(key) });
    items.push({ sep: true });
    items.push({ label: 'Delete cable', run: () => deleteCable(key), danger: true, key: 'Del' });
  }
  if (c.kind === 'lan' && c.ref.cable) {
    items.unshift({ label: 'Open in Cables', run: () => { window.location.href = `/cables?cable=${encodeURIComponent(c.ref.cable)}`; } });
  }
  return items;
}
function cableMenuTitle(key) {
  const c = cableByKey(key);
  if (!c) return 'Cable';
  if (c.kind === 'lan') return `${c.ref.switch} ${c.ref.port} → ${c.ref.seat}`;
  return c.kind === 'power' ? `Power: ${c.label}` : 'Uplink';
}

// ── Patch panels: placed from the right-click menu, dragged like the rest ─────────────────
async function placePanel(name, at) {
  const old = (cablePlan.panels || []).find(p => p.name.toLowerCase() === name.toLowerCase());
  try {
    await api('PUT', `/api/cable-plan/panels/${encodeURIComponent(name)}`, { ...at, hall_id: currentHall });
    pushHistory({
      label: `place ${name}`,
      undo: async () => {
        if (old && old.x != null) await api('PUT', `/api/cable-plan/panels/${encodeURIComponent(name)}`, { x: old.x, y: old.y, hall_id: currentHall });
        else await api('DELETE', `/api/cable-plan/panels/${encodeURIComponent(name)}`);
        await loadCablePlan();
      },
      redo: async () => { await api('PUT', `/api/cable-plan/panels/${encodeURIComponent(name)}`, { ...at, hall_id: currentHall }); await loadCablePlan(); },
    });
    await loadCablePlan();
  } catch (err) { toastError('Could not place the patch panel', err); }
}

async function removePanel(name) {
  const old = (cablePlan.panels || []).find(p => p.name === name);
  try {
    await api('DELETE', `/api/cable-plan/panels/${encodeURIComponent(name)}`);
    pushHistory({
      label: `remove ${name}`,
      undo: async () => { await api('PUT', `/api/cable-plan/panels/${encodeURIComponent(name)}`, { x: old.x, y: old.y, hall_id: currentHall }); await loadCablePlan(); },
      redo: async () => { await api('DELETE', `/api/cable-plan/panels/${encodeURIComponent(name)}`); await loadCablePlan(); },
    });
    await loadCablePlan();
  } catch (err) { toastError('Could not remove the patch panel', err); }
}

// Floor menu: the patch panels the cables name that are not on the plan yet.
function panelMenuEntries(at) {
  if (!cableEditable() || !at) return [];
  const placed = new Set((cablePlan.panels || []).map(p => p.name.toLowerCase()));
  return (cablePlan.panel_names || []).filter(n => !placed.has(n.toLowerCase())).slice(0, 8)
    .map(n => ({ label: `Put patch panel ${n} here`, run: () => placePanel(n, at) }));
}

let panelDrag = null;
function onPanelMouseDown(e) {
  const g = e.target.closest('[data-patch-panel]');
  if (!g || e.button !== 0 || currentTool !== 'select' || !cableEditable()) return;
  e.stopPropagation();
  e.preventDefault();
  panelDrag = { name: g.dataset.patchPanel, moved: false };
  const move = (ev) => {
    const p = clientToPercent(ev.clientX, ev.clientY);
    const panel = p && cablePlan.panels.find(x => x.name === panelDrag.name);
    if (!panel) return;
    panel.x = snapToGrid(p.x); panel.y = snapToGrid(p.y);
    panelDrag.moved = true;
    renderCables();
  };
  document.addEventListener('mousemove', move);
  document.addEventListener('mouseup', async () => {
    document.removeEventListener('mousemove', move);
    const drag = panelDrag;
    panelDrag = null;
    const panel = cablePlan.panels.find(x => x.name === drag.name);
    if (drag.moved && panel) { await placePanel(panel.name, { x: panel.x, y: panel.y }); }
  }, { once: true });
}

// ── The Cable tool ───────────────────────────────────────────────────────────────────
const cableBtn = $('tool-cable');
const cableMenu = $('cable-menu');
let cableDialogTarget = null;

function cableToolChanged() {
  cableDraft = null;
  if (currentTool === 'cable-power' && typeof setPowerLayer === 'function' && !powerLayer) setPowerLayer(true);
  if (currentTool.startsWith('cable-')) {
    // A new cable lands on its layer: show it.
    const layer = currentTool === 'cable-power' ? 'electrical' : 'network';
    if (hiddenMarkLayers.has(layer)) setMarkLayerShown(layer, true);
  }
  renderCables();
}

// What the Cable tool clicked: a switch, a seat, a seat block or a distribution board.
function cableTargetOf(el) {
  const sw = el.closest('.switch-marker');
  if (sw) return { type: 'switch', id: sw.dataset.id };
  const board = el.closest('.power-board');
  if (board) return { type: 'board', id: board.dataset.board };
  const seat = el.closest('.seat-block-seat');
  const block = el.closest('.seat-block');
  if (seat && seat.dataset.seatNumber && cableDraft?.kind === 'lan') return { type: 'seat', seat: seat.dataset.seatNumber, block: block?.dataset.id };
  if (block) return { type: 'block', id: block.dataset.id };
  return null;
}

function targetPoint(t) {
  if (t.type === 'switch') { const s = switches.find(x => x.id === t.id); return s ? [s.x, s.y] : null; }
  if (t.type === 'board') { const b = (powerMarkers.boards || []).find(x => x.id === t.id); return b ? [b.x, b.y] : null; }
  if (t.type === 'block') { const b = seatBlocks.find(x => x.id === t.id); return b ? [b.x, b.y] : null; }
  return null;
}

function targetName(t) {
  if (t.type === 'switch') return switches.find(x => x.id === t.id)?.name || 'switch';
  if (t.type === 'board') return (powerMarkers.boards || []).find(x => x.id === t.id)?.name || 'board';
  if (t.type === 'block') return `block ${seatBlocks.find(x => x.id === t.id)?.name || ''}`.trim();
  return `seat ${t.seat}`;
}

function onCableToolClick(e) {
  if (!currentTool.startsWith('cable-')) return;
  if (e.target.closest('.zoom-bar, .empty-canvas, .tool-rail')) return;
  e.preventDefault();
  e.stopPropagation();
  suppressNextClick = false;   // a click while drawing is always meant
  const kind = currentTool === 'cable-power' ? 'power' : 'lan';
  const t = cableTargetOf(e.target);
  if (!cableDraft) {
    if (!t || (kind === 'lan' && t.type !== 'switch') || (kind === 'power' && t.type !== 'board')) {
      toast(kind === 'lan' ? 'A network cable starts at a switch: click one' : 'A power cable starts at a distribution board: click one');
      return;
    }
    cableDraft = { kind, from: t, at: targetPoint(t) };
    toolHint.textContent = kind === 'lan' ? 'Now click a seat, a seat block or another switch · Esc to stop'
      : 'Now click a seat block or a switch · Esc to stop';
    return;
  }
  const ok = t && (kind === 'lan' ? ['seat', 'block', 'switch'].includes(t.type) && !(t.type === 'switch' && t.id === cableDraft.from.id)
    : ['block', 'switch'].includes(t.type));
  if (!ok) { toast(kind === 'lan' ? 'Click a seat, a seat block or another switch' : 'Click a seat block or a switch'); return; }
  openCableDialog(cableDraft.kind, cableDraft.from, t);
}

function onCableToolMove(e) {
  if (!cableDraft) return;
  const p = clientToPercent(e.clientX, e.clientY);
  if (!p) return;
  cableDraft.to = [p.x, p.y];
  renderCables();
}

function cableDialogOpen() { return !$('cable-backdrop').classList.contains('hidden'); }
function closeCableDialog() {
  $('cable-backdrop').classList.add('hidden');
  cableDialogTarget = null;
  cableDraft = null;
  if (currentTool.startsWith('cable-')) toolHint.textContent = TOOL_HINTS[currentTool];
  renderCables();
}

async function openCableDialog(kind, from, to) {
  cableDialogTarget = { kind, from, to };
  const form = $('cable-form');
  form.querySelector('.cable-net').classList.toggle('hidden', kind !== 'lan');
  form.querySelector('.cable-power').classList.toggle('hidden', kind !== 'power');
  $('cable-error').hidden = true;
  $('cable-title').textContent = kind === 'power' ? 'New power cable' : to.type === 'switch' ? 'New uplink' : 'New network cable';
  $('cable-text').textContent = `From ${targetName(from)} to ${targetName(to)}.`;
  if (kind === 'lan') {
    $('cable-port').value = '';
    $('cable-port-b').value = '';
    $('cable-port-label').textContent = to.type === 'block'
      ? `First port on ${targetName(from)} (the next seats count up)` : `Port on ${targetName(from)}`;
    $('cable-port-b-label').textContent = `Port on ${targetName(to)}`;
    $('cable-port-b-field').classList.toggle('hidden', to.type !== 'switch');
    $('cable-order-field').classList.toggle('hidden', to.type !== 'block');
  } else {
    const select = $('cable-circuit');
    select.innerHTML = '';
    let circuits = [];
    try { circuits = (await api('GET', '/api/power')).circuits.filter(c => c.board === from.id); } catch (_) { /* a new one then */ }
    for (const c of circuits) select.add(new Option(`${c.name} (${c.phase}, ${c.rating_a} A)`, c.id));
    select.add(new Option('New circuit…', ''));
    select._circuits = circuits;
    const syncName = () => { $('cable-circuit-name-field').classList.toggle('hidden', select.value !== ''); };
    select.onchange = syncName;
    syncName();
    $('cable-circuit-name').value = '';
  }
  $('cable-backdrop').classList.remove('hidden');
  (kind === 'lan' ? $('cable-port') : $('cable-circuit')).focus();
}

function cableFields() {
  return { type: $('cable-type').value || '', speed: $('cable-speed').value ? Number($('cable-speed').value) : null };
}

async function markDrawn(keys) {
  if (!keys.length) return;
  await api('PUT', '/api/cable-plan/routes', { routes: Object.fromEntries(keys.map(k => [k, { points: null }])) });
}

// Makes the cable. Returns what undo needs.
async function createLanCable(from, to) {
  const sw = switches.find(x => x.id === from.id);
  const port = $('cable-port').value.trim();
  const fields = cableFields();
  if (to.type === 'seat') {
    const cable = await api('POST', '/api/cables', { switch: sw.name, port, seat: to.seat, ...fields });
    const key = `lan:${sw.name.toLowerCase()}|${port.toLowerCase()}`;
    await markDrawn([key]);
    return { label: `cable to ${to.seat}`, undo: () => api('DELETE', `/api/cables/${cable.id}`), redoBody: cable };
  }
  if (to.type === 'switch') {
    const other = switches.find(x => x.id === to.id);
    const link = await api('POST', '/api/links', { a: sw.name, a_port: port, b: other.name, b_port: $('cable-port-b').value.trim(), ...fields });
    return { label: `uplink to ${other.name}`, undo: () => api('DELETE', `/api/links/${link.id}`), link };
  }
  // A whole block: one cable per seat, ports counting up (POST /api/cables/block).
  const body = { block: to.id, switch: sw.name, first_port: port, order: $('cable-order').value, ...fields };
  let res;
  try {
    res = await api('POST', '/api/cables/block', body);
  } catch (err) {
    if (!/already have a cable/.test(err.message)) throw err;
    const ok = await confirmDialog({ title: 'Replace the cables in the way?', text: `${err.message} Replace them with the new ones? You can undo this.` });
    if (!ok) return null;
    res = await api('POST', '/api/cables/block', { ...body, replace: true });
  }
  const ports = new Set(res.cables.map(c => c.port.toLowerCase()));
  const made = (await api('GET', '/api/cables')).cables.filter(c => c.switch === sw.name && ports.has(c.port.toLowerCase()));
  await markDrawn(made.map(c => `lan:${sw.name.toLowerCase()}|${c.port.toLowerCase()}`));
  return { label: `cable ${res.created} seats`, undo: async () => { for (const c of made) await api('DELETE', `/api/cables/${c.id}`); } };
}

async function createPowerCable(from, to) {
  const select = $('cable-circuit');
  const feed = to.type === 'block' ? { blocks: [{ block: to.id, rows: [] }] } : { switches: [to.id] };
  if (!select.value) {
    const name = $('cable-circuit-name').value.trim() || targetName(to);
    const circuit = await api('POST', '/api/power/circuits', { board: from.id, name, ...feed });
    return { label: `power to ${targetName(to)}`, undo: () => api('DELETE', `/api/power/circuits/${circuit.id}`) };
  }
  const circuit = select._circuits.find(c => c.id === select.value);
  const before = { blocks: circuit.blocks, switches: circuit.switches };
  const after = to.type === 'block'
    ? { blocks: [...circuit.blocks.filter(f => f.block !== to.id), ...feed.blocks] }
    : { switches: [...new Set([...circuit.switches, to.id])] };
  await api('PATCH', `/api/power/circuits/${circuit.id}`, after);
  return { label: `power to ${targetName(to)}`, undo: () => api('PATCH', `/api/power/circuits/${circuit.id}`, before),
           redo: () => api('PATCH', `/api/power/circuits/${circuit.id}`, after) };
}

$('cable-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const t = cableDialogTarget;
  if (!t) return;
  $('cable-ok').disabled = true;
  try {
    const done = t.kind === 'lan' ? await createLanCable(t.from, t.to) : await createPowerCable(t.from, t.to);
    if (!done) return;
    // Redo draws it again the same way.
    const again = { ...t };
    pushHistory({
      label: done.label,
      undo: async () => { await done.undo(); await loadCablePlan(); if (typeof loadPowerMarkers === 'function') loadPowerMarkers(); },
      redo: async () => {
        if (done.redo) await done.redo();
        else {
          const redone = again.kind === 'lan' ? await createLanCable(again.from, again.to) : await createPowerCable(again.from, again.to);
          if (redone) done.undo = redone.undo;
        }
        await loadCablePlan();
      },
    });
    closeCableDialog();
    await loadCablePlan();
    if (t.kind === 'power' && typeof loadPowerMarkers === 'function') loadPowerMarkers();
    toast(`Added: ${done.label}`);
  } catch (err) {
    $('cable-error').textContent = err.message;
    $('cable-error').hidden = false;
  } finally {
    $('cable-ok').disabled = false;
  }
});
$('cable-cancel')?.addEventListener('click', closeCableDialog);
$('cable-backdrop')?.addEventListener('click', (e) => { if (e.target === $('cable-backdrop')) closeCableDialog(); });

if (cableBtn) {
  if (typeof powerOn !== 'undefined' && !powerOn) cableMenu.querySelector('[data-cable="power"]')?.remove();
  cableBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!cableEditable()) return;
    const open = cableMenu.classList.toggle('hidden') === false;
    cableBtn.setAttribute('aria-expanded', String(open));
    if (open) cableMenu.querySelector('button')?.focus();
  });
  cableMenu.addEventListener('click', (e) => {
    const item = e.target.closest('[data-cable]');
    if (!item) return;
    setTool(`cable-${item.dataset.cable}`);
    cableMenu.classList.add('hidden');
    cableBtn.setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('click', (e) => {
    if (!cableMenu.contains(e.target) && e.target !== cableBtn) cableMenu.classList.add('hidden');
  });
}

if (cablesSvg) {
  cablesSvg.addEventListener('mousedown', onCableMouseDown);
  cablesSvg.addEventListener('mousedown', onPanelMouseDown);
  cablesSvg.addEventListener('dblclick', onCableDblClick);
  canvasArea.addEventListener('click', onCableToolClick, true);
  canvasArea.addEventListener('mousemove', onCableToolMove);
  // A click on the floor away from the cable lets go of it.
  canvasArea.addEventListener('mousedown', (e) => {
    if (selectedCable && !e.target.closest('[data-cable]')) { selectedCable = null; renderCables(); }
  });
  window.addEventListener('lal:live', (e) => {
    const type = e.detail && e.detail.type;
    if (type === 'cables.changed' || type === 'power.changed' || type === 'links.changed') scheduleCablePlan();
  });
  window.addEventListener('resize', renderCables);
}
