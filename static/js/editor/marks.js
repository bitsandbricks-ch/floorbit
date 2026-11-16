// Floor plan editor: text labels, walls, zones and icons on the plan (floorbit/plan_marks.py).
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

let planMarks = [];          // this hall's marks
let markIcons = {};          // icon name -> [path d, ...]
let selectedMark = null;     // id
let markDraft = null;        // first click of a wall or zone: {kind, x, y, style}
let markDrag = null;

const marksSvg = $('marks-svg');
const marksOverlay = $('marks-overlay');
const markPanel = $('mark-detail-panel');
const markForm = $('mark-edit-form');
const MARK_LABEL = { text: 'Label', icon: 'Icon', wall: 'Wall', zone: 'Zone' };
const MARK_ICON_NAMES = {
  exit: 'Exit', wc: 'Toilets', shower: 'Showers', bar: 'Bar', food: 'Food', coffee: 'Coffee', info: 'Info',
  'first-aid': 'First aid', stage: 'Stage', games: 'Games', stairs: 'Stairs', sleep: 'Sleeping area', wifi: 'Wi-Fi',
  'arrow-up': 'Arrow up', 'arrow-right': 'Arrow right', 'arrow-down': 'Arrow down', 'arrow-left': 'Arrow left',
  extinguisher: 'Fire extinguisher', escape: 'Escape route', assembly: 'Assembly point', server: 'Server',
  router: 'Router', 'access-point': 'Access point', power: 'Power', socket: 'Socket',
};
// The Seats view's layer a new icon lands on (floorbit/plan_marks.py LAYERS); the rest go on the overview.
const MARK_ICON_LAYER = {
  extinguisher: 'safety', escape: 'safety', assembly: 'safety', server: 'services',
  router: 'network', 'access-point': 'network', power: 'electrical', socket: 'electrical',
};

// Mark layers hidden while editing (the Layers section), so a busy plan can be worked on one
// layer at a time. Kept per browser; the Seats view has its own choice in its address.
const MARK_LAYERS = ['overview', 'safety', 'network', 'electrical', 'services'];
let hiddenMarkLayers = new Set(readJSON('layer-marks-hidden', []).filter(l => MARK_LAYERS.includes(l)));
const markLayerOf = (m) => m.layer || 'overview';

function setMarkLayerShown(layer, on) {
  if (on) hiddenMarkLayers.delete(layer); else hiddenMarkLayers.add(layer);
  writeJSON('layer-marks-hidden', [...hiddenMarkLayers]);
  for (const b of document.querySelectorAll('[data-mark-layer]'))
    setLayerButton(b, !hiddenMarkLayers.has(b.dataset.markLayer));
  const sel = planMarks.find(x => x.id === selectedMark);
  if (sel && hiddenMarkLayers.has(markLayerOf(sel))) clearMarkSelection();
  else renderMarks();
  updateSeatsViewLink();
}

// A mark just placed or moved to a hidden layer would vanish under the cursor: show its layer.
function revealMarkLayer(m) {
  if (hiddenMarkLayers.has(markLayerOf(m))) setMarkLayerShown(markLayerOf(m), true);
}

// The Seats view link opens this hall with the mark layers shown here (frontend/src/pages/plan/layers.ts).
const MARK_TO_VIEW = { overview: 'marks', safety: 'safety', network: 'network', electrical: 'electrical', services: 'services' };
function updateSeatsViewLink() {
  const a = $('seats-view-link');
  if (!a) return;
  const q = new URLSearchParams();
  if (currentHall) q.set('hall', currentHall);
  const on = MARK_LAYERS.filter(l => !hiddenMarkLayers.has(l)).map(l => MARK_TO_VIEW[l]);
  q.set('layers', [...new Set([...on, 'checkin'])].join(','));
  a.href = `/plan?${q}`;
}

document.querySelectorAll('[data-mark-layer]').forEach(b => {
  setLayerButton(b, !hiddenMarkLayers.has(b.dataset.markLayer));
  b.addEventListener('click', () => setMarkLayerShown(b.dataset.markLayer, hiddenMarkLayers.has(b.dataset.markLayer)));
});

async function loadMarks() {
  try {
    const body = await api('GET', '/api/plan-marks');
    markIcons = body.icons || {};
    planMarks = inHall(body.marks || []);
  } catch (_) { planMarks = []; }
  fillIconPicker();
  renderMarks();
}

function iconSvg(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${
    (markIcons[name] || []).map(d => `<path d="${escHtml(d)}"/>`).join('')}</svg>`;
}

// ── Drawing ──────────────────────────────────────────────────────────────────────────
function renderMarks() {
  if (!marksSvg) return;
  const svg = [];
  const html = [];
  updateSeatsViewLink();
  for (const m of planMarks) {
    if (hiddenMarkLayers.has(markLayerOf(m))) continue;
    const sel = m.id === selectedMark ? ' selected' : '';
    if (m.kind === 'zone') {
      svg.push(`<g class="mark-zone zone-${m.color}${sel}" data-mark="${m.id}"><rect x="${m.x}" y="${m.y}" width="${m.w}" height="${m.h}" vector-effect="non-scaling-stroke"/></g>`);
      if (m.label) html.push(`<div class="mark-zone-label zone-${m.color}" style="left:${m.x}%;top:${m.y}%" data-mark="${m.id}">${escHtml(m.label)}</div>`);
    } else if (m.kind === 'wall') {
      svg.push(`<g class="mark-wall${m.style === 'dashed' ? ' dashed' : ''}${sel}" data-mark="${m.id}">` +
        `<line class="hit" x1="${m.x}" y1="${m.y}" x2="${m.x2}" y2="${m.y2}" vector-effect="non-scaling-stroke"/>` +
        `<line x1="${m.x}" y1="${m.y}" x2="${m.x2}" y2="${m.y2}" vector-effect="non-scaling-stroke"/></g>`);
    } else {
      const turn = m.rotation ? ` rotate(${m.rotation}deg)` : '';
      const inner = m.kind === 'text' ? escHtml(m.text) : iconSvg(m.icon);
      html.push(`<div class="mark-${m.kind} size-${m.size}${sel}" style="left:${m.x}%;top:${m.y}%;transform:translate(-50%,-50%)${turn}" data-mark="${m.id}"` +
        `${m.kind === 'icon' ? ` title="${escHtml(MARK_ICON_NAMES[m.icon] || m.icon)}"` : ''}>${inner}</div>`);
    }
  }
  marksSvg.innerHTML = svg.join('');
  marksOverlay.innerHTML = html.join('');
}

// ── Placing ──────────────────────────────────────────────────────────────────────────
// Called by canvas.js for the add-text, add-icon, add-wall, add-dashed and add-zone tools.
async function placeMark(tool, at) {
  if (tool === 'wall' || tool === 'dashed' || tool === 'zone') {
    if (!markDraft) {
      markDraft = { tool, x: at.x, y: at.y };
      toolHint.textContent = tool === 'zone' ? 'Click the opposite corner of the zone · Esc to cancel'
        : 'Click where the line ends · Esc to cancel';
      return;
    }
    const start = markDraft;
    markDraft = null;
    const body = tool === 'zone'
      ? { kind: 'zone', x: Math.min(start.x, at.x), y: Math.min(start.y, at.y), w: Math.abs(at.x - start.x), h: Math.abs(at.y - start.y) }
      : { kind: 'wall', x: start.x, y: start.y, x2: at.x, y2: at.y, style: tool === 'dashed' ? 'dashed' : 'solid' };
    await addMark(body);
    setTool(tool === 'zone' ? 'select' : currentTool);   // walls: keep drawing the next one
    if (tool !== 'zone') toolHint.textContent = TOOL_HINTS[currentTool];
    return;
  }
  const body = tool === 'text'
    ? { kind: 'text', x: at.x, y: at.y, text: 'Label', size: 'm' }
    : { kind: 'icon', x: at.x, y: at.y, icon: markIconChoice, size: 'm' };
  await addMark(body);
  setTool('select');
}

async function addMark(body) {
  try {
    if (!body.layer && body.kind === 'icon' && MARK_ICON_LAYER[body.icon]) body = { ...body, layer: MARK_ICON_LAYER[body.icon] };
    let mark = await api('POST', '/api/plan-marks', { ...body, hall_id: currentHall });
    planMarks.push(mark);
    revealMarkLayer(mark);
    renderMarks();
    selectMark(mark.id);
    const ref = { id: mark.id };
    pushHistory({
      label: `add ${MARK_LABEL[mark.kind].toLowerCase()}`,
      undo: () => removeMark(resolveId(ref.id)),
      redo: async () => {
        mark = await api('POST', '/api/plan-marks', { ...body, hall_id: currentHall });
        planMarks.push(mark);
        aliasId(resolveId(ref.id), mark.id);
        ref.id = mark.id;
        renderMarks();
      },
    });
    if (mark.kind === 'text') { markField('text').focus(); markField('text').select(); }
  } catch (e) {
    toastError('Could not add it to the plan', e);
  }
}

async function saveMark(id, patch) {
  const updated = await api('PUT', `/api/plan-marks/${id}`, patch);
  const i = planMarks.findIndex(m => m.id === id);
  if (i >= 0) planMarks[i] = updated;
  renderMarks();
  return updated;
}

async function removeMark(id) {
  await api('DELETE', `/api/plan-marks/${id}`);
  planMarks = planMarks.filter(m => m.id !== id);
  if (selectedMark === id) clearMarkSelection();
  renderMarks();
}

// ── Choosing an icon before placing it ─────────────────────────────────────────────────
let markIconChoice = 'exit';
function fillIconPicker() {
  const picker = $('mark-icon-picker');
  const select = markField('icon');
  if (!picker || !select) return;
  const names = Object.keys(markIcons);
  picker.innerHTML = names.map(n => `<button type="button" class="mark-icon-choice" data-icon="${n}" title="${escHtml(MARK_ICON_NAMES[n] || n)}" aria-label="${escHtml(MARK_ICON_NAMES[n] || n)}">${iconSvg(n)}</button>`).join('');
  select.innerHTML = names.map(n => `<option value="${n}">${escHtml(MARK_ICON_NAMES[n] || n)}</option>`).join('');
}

// ── Selecting and editing ──────────────────────────────────────────────────────────────
function markField(name) { return markForm ? markForm.elements[name] : null; }

function selectMark(id) {
  deselectAll();
  selectedMark = id;
  const m = planMarks.find(x => x.id === id);
  if (!m) return;
  $('mark-detail-kind').textContent = MARK_LABEL[m.kind];
  $('mark-detail-name').textContent = m.text || m.label || MARK_ICON_NAMES[m.icon] || (m.style === 'dashed' ? 'Dashed line' : MARK_LABEL[m.kind]);
  for (const el of markForm.querySelectorAll('[data-for]'))
    el.classList.toggle('hidden', !el.dataset.for.split(' ').includes(m.kind));
  markField('text').value = m.kind === 'zone' ? (m.label || '') : (m.text || '');
  markField('size').value = m.size || 'm';
  markField('rotation').value = String(m.rotation || 0);
  markField('icon').value = m.icon || 'exit';
  markField('style').value = m.style || 'solid';
  markField('color').value = m.color || 'muted';
  markField('layer').value = m.layer || 'overview';
  markPanel.classList.remove('hidden');
  renderMarks();
}

function clearMarkSelection() {
  selectedMark = null;
  if (markPanel) markPanel.classList.add('hidden');
  renderMarks();
}

if (markForm) {
  markForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const m = planMarks.find(x => x.id === selectedMark);
    if (!m) return;
    const patch = {
      text: { text: markField('text').value, size: markField('size').value, rotation: Number(markField('rotation').value) },
      icon: { icon: markField('icon').value, size: markField('size').value, rotation: Number(markField('rotation').value) },
      wall: { style: markField('style').value },
      zone: { label: markField('text').value, color: markField('color').value },
    }[m.kind];
    patch.layer = markField('layer').value;
    const before = Object.fromEntries(Object.keys(patch).map(k => [k, m[k]]));
    const id = m.id;
    try {
      await saveMark(id, patch);
      revealMarkLayer(patch);
      pushHistory({ label: `edit ${MARK_LABEL[m.kind].toLowerCase()}`, undo: () => saveMark(resolveId(id), before), redo: () => saveMark(resolveId(id), patch) });
      selectMark(id);
      toast('Saved', { type: 'success', duration: 2000 });
    } catch (err) {
      toastError('Could not save it', err);
    }
  });
  $('mark-detail-close').addEventListener('click', clearMarkSelection);
  $('mark-detail-delete').addEventListener('click', () => deleteSelectedMark());
}

async function deleteSelectedMark() {
  const m = planMarks.find(x => x.id === selectedMark);
  if (!m) return false;
  const body = { ...m };
  const ref = { id: m.id };
  try {
    await removeMark(m.id);
    pushHistory({
      label: `delete ${MARK_LABEL[m.kind].toLowerCase()}`,
      undo: async () => {
        const again = await api('POST', '/api/plan-marks', body);
        planMarks.push(again);
        aliasId(resolveId(ref.id), again.id);
        ref.id = again.id;
        renderMarks();
      },
      redo: () => removeMark(resolveId(ref.id)),
    });
  } catch (err) {
    toastError('Could not delete it', err);
  }
  return true;
}

// ── Moving ─────────────────────────────────────────────────────────────────────────────
function onMarkMouseDown(e) {
  const el = e.target.closest('[data-mark]');
  if (!el || e.button !== 0 || currentTool !== 'select') return;
  const m = planMarks.find(x => x.id === el.dataset.mark);
  if (!m) return;
  e.stopPropagation();
  e.preventDefault();
  if (selectedMark !== m.id) selectMark(m.id);
  const p = clientToPercent(e.clientX, e.clientY);
  if (!p) return;
  markDrag = { id: m.id, start: p, orig: { ...m }, moved: false };
  document.addEventListener('mousemove', onMarkMouseMove);
  document.addEventListener('mouseup', onMarkMouseUp, { once: true });
}

function movedBy(orig, dx, dy) {
  const out = { x: snapToGrid(orig.x + dx), y: snapToGrid(orig.y + dy) };
  if (orig.kind === 'wall') Object.assign(out, { x2: orig.x2 + (out.x - orig.x), y2: orig.y2 + (out.y - orig.y) });
  return out;
}

function onMarkMouseMove(e) {
  if (!markDrag) return;
  const p = clientToPercent(e.clientX, e.clientY);
  if (!p) return;
  const dx = p.x - markDrag.start.x, dy = p.y - markDrag.start.y;
  if (!markDrag.moved && Math.hypot(dx, dy) < 0.3) return;
  markDrag.moved = true;
  const m = planMarks.find(x => x.id === markDrag.id);
  if (m) Object.assign(m, movedBy(markDrag.orig, dx, dy));
  renderMarks();
}

async function onMarkMouseUp() {
  document.removeEventListener('mousemove', onMarkMouseMove);
  const drag = markDrag;
  markDrag = null;
  if (!drag || !drag.moved) return;
  suppressNextClick = true;
  setTimeout(() => { suppressNextClick = false; }, 0);
  const m = planMarks.find(x => x.id === drag.id);
  if (!m) return;
  const patch = { x: m.x, y: m.y, ...(m.kind === 'wall' ? { x2: m.x2, y2: m.y2 } : {}) };
  const before = Object.fromEntries(Object.keys(patch).map(k => [k, drag.orig[k]]));
  try {
    await saveMark(m.id, patch);
    pushHistory({ label: 'move', undo: () => saveMark(resolveId(m.id), before), redo: () => saveMark(resolveId(m.id), patch) });
  } catch (err) {
    Object.assign(m, before);
    renderMarks();
    toastError('Could not move it', err);
  }
}

if (marksSvg) {
  marksSvg.addEventListener('mousedown', onMarkMouseDown);
  marksOverlay.addEventListener('mousedown', onMarkMouseDown);
}

// ── The Draw menu in the toolbar ─────────────────────────────────────────────────────────
const drawBtn = $('tool-draw');
const drawMenu = $('draw-menu');
if (drawBtn) {
  drawBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = drawMenu.classList.toggle('hidden') === false;
    drawBtn.setAttribute('aria-expanded', String(open));
  });
  drawMenu.addEventListener('click', (e) => {
    const icon = e.target.closest('[data-icon]');
    const item = e.target.closest('[data-draw]');
    if (icon) { markIconChoice = icon.dataset.icon; setTool('add-icon'); }
    else if (item) setTool(`add-${item.dataset.draw}`);
    else return;
    drawMenu.classList.add('hidden');
    drawBtn.setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('click', (e) => {
    if (!drawMenu.contains(e.target) && e.target !== drawBtn) drawMenu.classList.add('hidden');
  });
}
