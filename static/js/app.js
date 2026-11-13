'use strict';

// ── Pin icon ─────────────────────────────────────────────────────────────────────────
// Teardrop pin – colour comes from the .switch-pin CSS class. The glyph in the
// head repeats the status as a shape, so it doesn't rely on colour alone.
function pinSVG(status) {
  let glyph;
  if (status === 'offline') {
    glyph = '<path d="M5.4 3.4l3.2 3.2M8.6 3.4L5.4 6.6" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>';
  } else if (status === 'online') {
    glyph = '<circle cx="7" cy="5" r="2.2" fill="rgba(255,255,255,0.85)"/>';
  } else {
    glyph = '<circle cx="7" cy="5" r="2.2" fill="rgba(255,255,255,0.30)"/>';
  }
  return `<svg viewBox="0 0 14 18" xmlns="http://www.w3.org/2000/svg">
    <path d="M7 0C4.24 0 2 2.24 2 5c0 4.5 5 13 5 13s5-8.5 5-13C12 2.24 9.76 0 7 0z"
          fill="currentColor" stroke="rgba(0,0,0,0.4)" stroke-width="0.6"/>
    ${glyph}
  </svg>`;
}

const STATUS_GLYPH = { online: '●', offline: '✕', warning: '!', unknown: '?' };
function statusGlyph(status) { return STATUS_GLYPH[status] || '?'; }
function statusBucket(status) {
  return status === 'online' || status === 'offline' ? status : 'unknown';
}

// ── State ───────────────────────────────────────────────────────────────────────────
let config         = { netbox_enabled: false, librenms_enabled: false };
let switches       = [];
let seats          = [];
let seatBlocks     = [];
let currentTool    = 'select';
let selectedId     = null;
let selectedType   = null; // 'switch' | 'block' | 'seat'
let pendingCoords  = null;
let pendingPickerDeviceId = null;   // selected device in the NetBox picker tab
let selectedDeviceIds = new Set();  // selected device IDs in multiselect mode
let contextTarget  = null;          // { type: 'switch'|'block', id }
let dragState      = null;
let panState       = null;
let suppressNextClick = false;
let heatmapVisible = false;
let seatHeatmapVisible = false;
let isRefreshing   = false;
let statusFilter   = 'all';
let snapEnabled    = true;
let lastRefreshAt  = null;
let lastRefreshFailed = false;
const view         = { x: 0, y: 0, k: 1 };   // pan (px) and zoom of the floor plan
const portStats    = {};             // { switchId: { up_ports, total_ports, ... } }
const seatHeatmapData = {};          // { seats: { seatNumber: { port_usage, ... } } }
const deviceSettings = readJSON('deviceSettings', {});
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 1.2;
const GRID_SNAP = 0.5; // Grid snap interval (% of the floor plan)
const REFRESH_INTERVAL = 10_000;

// Cache configuration
const CACHE_KEY = 'switchStatusCache';
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// ── localStorage helpers (never throw) ─────────────────────────────────────────
function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch { return fallback; }
}
function writeJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

function getCache() {
  const cache = readJSON(CACHE_KEY, null);
  if (!cache || Date.now() - cache.timestamp > CACHE_TTL) return null;
  return cache.data;
}
function setCache(data) { writeJSON(CACHE_KEY, { timestamp: Date.now(), data }); }

// ── Per-device settings ────────────────────────────────────────────────────────
// Server-wide defaults from Settings > Display defaults (sent in /api/config).
const DISPLAY_DEFAULT_KEYS = { hideLabel: 'hide_labels', excludeHeatmap: 'exclude_heatmap' };
function getDeviceSetting(id, key, def) {
  if (def === undefined) def = config.display_defaults?.[DISPLAY_DEFAULT_KEYS[key]] ?? false;
  return deviceSettings[id]?.[key] ?? def;
}
function setDeviceSetting(id, key, val) {
  if (!deviceSettings[id]) deviceSettings[id] = {};
  deviceSettings[id][key] = val;
  writeJSON('deviceSettings', deviceSettings);
}

// ── DOM refs ────────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const canvasArea       = $('canvas-area');
const wrapper          = $('floorplan-wrapper');
const overlay          = $('switches-overlay');
const seatsOverlay     = $('seats-overlay');
const blocksOverlay    = $('blocks-overlay');
const switchList       = $('switch-list');
const switchSearch     = $('switch-search');
const switchCount      = $('switch-count');
const listFilter       = $('list-filter');
const listFilterText   = $('list-filter-text');
const listFilterClear  = $('list-filter-clear');
const addCursor        = $('add-cursor');
const posX             = $('pos-x');
const posY             = $('pos-y');
const universalSearch  = $('universal-search');
const searchResults    = $('search-results');
const emptyCanvas      = $('empty-canvas');
const toolHint         = $('tool-hint');
const lastUpdatedEl    = $('last-updated');

const toolSelect       = $('tool-select');
const toolAddSwitch    = $('tool-add-switch');
const toolAddBlock     = $('tool-add-block');
const btnUndo          = $('btn-undo');
const btnRedo          = $('btn-redo');
const btnSnap          = $('btn-snap');
const btnRefreshAll    = $('btn-refresh-all');
const syncSection      = $('sync-section');
const btnSync          = $('btn-sync');
const syncInfo         = $('sync-info');
const btnLabels        = $('btn-labels');
const btnShortcuts     = $('btn-shortcuts');

// Add-switch modal
const modalBackdrop    = $('modal-backdrop');
const modalTabs        = $('modal-tabs');
const tabNetbox        = $('tab-netbox');
const tabManual        = $('tab-manual');
const modalNetbox      = $('modal-netbox');
const modalManual      = $('modal-manual');
const deviceFilter     = $('device-filter');
const deviceList       = $('device-list');
const switchNameInput  = $('switch-name-input');
const modalCancel      = $('modal-cancel');
const modalConfirm     = $('modal-confirm');
const multiselectToggle = $('multiselect-toggle');
const multiselectCount = $('multiselect-count');

// Rename modal
const renameBackdrop   = $('rename-backdrop');
const renameInput      = $('rename-input');
const renameCancel     = $('rename-cancel');
const renameConfirm    = $('rename-confirm');

// Confirm + shortcuts dialogs
const confirmBackdrop  = $('confirm-backdrop');
const confirmTitle     = $('confirm-title');
const confirmText      = $('confirm-text');
const confirmOk        = $('confirm-ok');
const confirmCancel    = $('confirm-cancel');
const shortcutsBackdrop = $('shortcuts-backdrop');
const shortcutsClose   = $('shortcuts-close');

// Context menu
const contextMenu      = $('context-menu');
const ctxRename        = $('ctx-rename');
const ctxDelete        = $('ctx-delete');

// Switch inspector
const detailPanel       = $('detail-panel');
const detailName        = $('detail-name');
const detailStatusBadge = $('detail-status-badge');
const ddSource          = $('dd-source');
const ddPosition        = $('dd-position');
const dtNetboxStatus    = $('dt-netbox-status');
const ddNetboxStatus    = $('dd-netbox-status');
const detailLibrenms    = $('detail-librenms');
const ddHostname        = $('dd-hostname');
const ddLnmsStatus      = $('dd-lnms-status');
const ddIp              = $('dd-ip');
const ddPorts           = $('dd-ports');
const ddTemperature     = $('dd-temperature');
const ddCpu             = $('dd-cpu');
const ddMem             = $('dd-mem');
const barCpu            = $('bar-cpu');
const barMem            = $('bar-mem');
const detailBtnRefresh  = $('detail-btn-refresh');
const detailBtnRename   = $('detail-btn-rename');
const detailBtnDelete   = $('detail-btn-delete');
const detailClose       = $('detail-close');
const settingExcludeHeatmap = $('setting-exclude-heatmap');
const settingHideLabel      = $('setting-hide-label');

// Zoom & layers
const btnZoomIn      = $('btn-zoom-in');
const btnZoomOut     = $('btn-zoom-out');
const btnZoomReset   = $('btn-zoom-reset');
const zoomLevelEl    = $('zoom-level');
const btnCenter      = $('btn-center');
const btnHeatmap     = $('btn-heatmap');
const btnSeatHeatmap = $('btn-seat-heatmap');
const heatCanvas     = $('heatmap-canvas');
const seatHeatCanvas = $('seat-heatmap-canvas');
const heatLegend     = $('heatmap-legend');
const seatHeatLegend = $('seat-heatmap-legend');

// Seat block inspector
const blockDetailPanel     = $('block-detail-panel');
const blockDetailName      = $('block-detail-name');
const blockDdName          = $('block-dd-name');
const blockDdPosition      = $('block-dd-position');
const blockDdSize          = $('block-dd-size');
const blockDdRotation      = $('block-dd-rotation');
const blockEditForm        = $('block-edit-form');
const blockEditName        = $('block-edit-name');
const blockEditCols        = $('block-edit-cols');
const blockEditRows        = $('block-edit-rows');
const blockEditRotation    = $('block-edit-rotation');
const blockEditRotationSeg = $('block-edit-rotation-seg');
const blockReverseNumbers  = $('block-edit-reverse-numbers');
const blockDetailClose     = $('block-detail-close');
const blockDetailDuplicate = $('block-detail-duplicate');
const blockDetailDelete    = $('block-detail-delete');

// Seat inspector
const blockSeatDetailPanel      = $('block-seat-detail-panel');
const blockSeatDetailNumber     = $('block-seat-detail-number');
const blockSeatUserBadge        = $('block-seat-user-badge');
const blockSeatDdNumber         = $('block-seat-dd-number');
const blockSeatDdUsername       = $('block-seat-dd-username');
const blockSeatDdPosition       = $('block-seat-dd-position');
const blockSeatDdIp             = $('block-seat-dd-ip');
const blockSeatDdMac            = $('block-seat-dd-mac');
const blockSeatDdSwitch         = $('block-seat-dd-switch');
const blockSeatDdPort           = $('block-seat-dd-port');
const blockSeatDdVlan           = $('block-seat-dd-vlan');
const blockSeatResolutionStatus = $('block-seat-resolution-status');
const blockSeatDetailClose      = $('block-seat-detail-close');
const blockSeatDdPortStatus     = $('block-seat-dd-port-status');
const blockSeatDdTotalTraffic   = $('block-seat-dd-total-traffic');
const blockSeatDdDownload       = $('block-seat-dd-download');
const blockSeatDdUpload         = $('block-seat-dd-upload');
const blockSeatDdPortSpeed      = $('block-seat-dd-port-speed');

// Top bar stats
const heroTotal    = $('hero-total');
const heroOnline   = $('hero-online');
const heroOffline  = $('hero-offline');
const heroUnknown  = $('hero-unknown');
const statusChips  = document.querySelectorAll('.status-chip');

// Seat mapping data from seats.json
let seatMappings = {};

// ── API helper ───────────────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error('Cannot reach the server');
  }
  if (!res.ok) {
    let msg = `${method} ${path} failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.error) msg = data.error;
    } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return res.json();
}

// ── Toasts ──────────────────────────────────────────────────────────────────────────
const toastStack = $('toast-stack');

function toast(message, { type = 'info', action = null, duration = 5000 } = {}) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  const msg = document.createElement('span');
  msg.className = 'toast-msg';
  msg.textContent = message;
  el.appendChild(msg);

  let timer = null;
  const dismiss = () => {
    clearTimeout(timer);
    if (!el.isConnected) return;
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 180);
  };

  if (action) {
    const btn = document.createElement('button');
    btn.className = 'toast-action';
    btn.textContent = action.label;
    btn.addEventListener('click', () => { dismiss(); action.onClick(); });
    el.appendChild(btn);
  }
  const close = document.createElement('button');
  close.className = 'toast-close';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '✕';
  close.addEventListener('click', dismiss);
  el.appendChild(close);

  toastStack.appendChild(el);
  while (toastStack.children.length > 4) toastStack.firstElementChild.remove();
  if (duration) timer = setTimeout(dismiss, duration);
  el.addEventListener('mouseenter', () => clearTimeout(timer));
  el.addEventListener('mouseleave', () => { if (duration) timer = setTimeout(dismiss, duration); });
  return dismiss;
}

function toastError(prefix, err) {
  toast(`${prefix}: ${err && err.message ? err.message : err}`, { type: 'error', duration: 8000 });
}

window.addEventListener('unhandledrejection', (e) => {
  toastError('Something went wrong', e.reason);
});

// ── Dialog helpers ─────────────────────────────────────────────────────────────
let confirmResolver = null;

function confirmDialog({ title, text, okLabel = 'Delete' }) {
  confirmTitle.textContent = title;
  confirmText.textContent = text;
  confirmOk.textContent = okLabel;
  confirmBackdrop.classList.remove('hidden');
  confirmOk.focus();
  return new Promise((resolve) => { confirmResolver = resolve; });
}
function closeConfirm(result) {
  confirmBackdrop.classList.add('hidden');
  if (confirmResolver) { confirmResolver(result); confirmResolver = null; }
}
confirmOk.addEventListener('click', () => closeConfirm(true));
confirmCancel.addEventListener('click', () => closeConfirm(false));
confirmBackdrop.addEventListener('click', (e) => { if (e.target === confirmBackdrop) closeConfirm(false); });

btnShortcuts.addEventListener('click', () => shortcutsBackdrop.classList.remove('hidden'));
shortcutsClose.addEventListener('click', () => shortcutsBackdrop.classList.add('hidden'));
shortcutsBackdrop.addEventListener('click', (e) => { if (e.target === shortcutsBackdrop) shortcutsBackdrop.classList.add('hidden'); });

function anyModalOpen() {
  return [modalBackdrop, renameBackdrop, blockBackdropEl(), confirmBackdrop, shortcutsBackdrop]
    .some(el => el && !el.classList.contains('hidden'));
}
function closeAllModals() {
  if (!confirmBackdrop.classList.contains('hidden')) { closeConfirm(false); return; }
  if (!shortcutsBackdrop.classList.contains('hidden')) { shortcutsBackdrop.classList.add('hidden'); return; }
  if (!renameBackdrop.classList.contains('hidden')) { renameBackdrop.classList.add('hidden'); return; }
  if (!modalBackdrop.classList.contains('hidden')) { closeAddModal(); return; }
  if (!blockBackdropEl().classList.contains('hidden')) { closeBlockModal(); }
}
function blockBackdropEl() { return $('block-backdrop'); }

// ── Undo / redo ──────────────────────────────────────────────────────────────────────
// Each entry is { label, undo: async fn, redo: async fn }. Deleting and then
// restoring an item gives it a new server id, so ids are resolved through
// idAlias to keep older history entries pointing at the right item.
const history = [];
const future = [];
const idAlias = {};
const HISTORY_LIMIT = 100;
let historyBusy = false;
let undoToastDismiss = null;   // the latest "Deleted … · Undo" toast

function undoToast(message) {
  if (undoToastDismiss) undoToastDismiss();
  undoToastDismiss = toast(message, { action: { label: 'Undo', onClick: undo }, duration: 8000 });
}

function resolveId(id) {
  let cur = id;
  const seen = new Set();
  while (idAlias[cur] && !seen.has(cur)) { seen.add(cur); cur = idAlias[cur]; }
  return cur;
}
function aliasId(oldId, newId) { if (oldId !== newId) idAlias[oldId] = newId; }

function pushHistory(entry) {
  history.push(entry);
  if (history.length > HISTORY_LIMIT) history.shift();
  future.length = 0;
  updateHistoryButtons();
}
function updateHistoryButtons() {
  btnUndo.disabled = history.length === 0 || historyBusy;
  btnRedo.disabled = future.length === 0 || historyBusy;
  btnUndo.title = history.length ? `Undo ${history[history.length - 1].label} (Ctrl+Z)` : 'Undo (Ctrl+Z)';
  btnRedo.title = future.length ? `Redo ${future[future.length - 1].label} (Ctrl+Shift+Z)` : 'Redo (Ctrl+Shift+Z)';
}
async function undo() {
  if (historyBusy || !history.length) return;
  const entry = history.pop();
  if (undoToastDismiss) { undoToastDismiss(); undoToastDismiss = null; }
  historyBusy = true; updateHistoryButtons();
  try {
    await entry.undo();
    future.push(entry);
    toast(`Undid ${entry.label}`, { duration: 2500 });
  } catch (e) {
    toastError(`Could not undo ${entry.label}`, e);
  } finally {
    historyBusy = false; updateHistoryButtons();
    renderAll();
  }
}
async function redo() {
  if (historyBusy || !future.length) return;
  const entry = future.pop();
  historyBusy = true; updateHistoryButtons();
  try {
    await entry.redo();
    history.push(entry);
    toast(`Redid ${entry.label}`, { duration: 2500 });
  } catch (e) {
    toastError(`Could not redo ${entry.label}`, e);
  } finally {
    historyBusy = false; updateHistoryButtons();
    renderAll();
  }
}
btnUndo.addEventListener('click', undo);
btnRedo.addEventListener('click', redo);

// ── Data operations (server + local state) ──────────────────────────────────────
async function createManualSwitch(data) {
  const sw = await api('POST', '/api/switches', data);
  switches.push(sw);
  return sw;
}
async function updateSwitch(id, patch) {
  const updated = await api('PUT', `/api/switches/${id}`, patch);
  const idx = switches.findIndex(s => s.id === id);
  if (idx >= 0) {
    const keep = switches[idx].status;
    switches[idx] = { ...switches[idx], ...updated, placed: true };
    if (updated.status === 'unknown' && keep) switches[idx].status = keep;
  }
  return updated;
}
async function deleteSwitch(id) {
  await api('DELETE', `/api/switches/${id}`);
  // NetBox devices become unplaced; manual devices are fully removed
  const sw = switches.find(s => s.id === id);
  if (sw && sw.source !== 'manual') {
    sw.placed = false;
    sw.x = null;
    sw.y = null;
  } else {
    switches = switches.filter(s => s.id !== id);
  }
  if (selectedId === id) deselectAll();
}
async function createBlock(data) {
  const block = await api('POST', '/api/seat-blocks', data);
  seatBlocks.push(block);
  return block;
}
async function updateBlock(id, patch) {
  const updated = await api('PUT', `/api/seat-blocks/${id}`, patch);
  const block = seatBlocks.find(b => b.id === id);
  if (block) Object.assign(block, updated);
  return updated;
}
async function deleteBlock(id) {
  await api('DELETE', `/api/seat-blocks/${id}`);
  seatBlocks = seatBlocks.filter(b => b.id !== id);
  if (selectedId === id) deselectAll();
}

const BLOCK_FIELDS = ['name', 'x', 'y', 'cols', 'rows', 'seat_width', 'seat_height',
                      'spacing_x', 'spacing_y', 'rotation', 'reverse_numbers'];
function blockPayload(block) {
  const out = {};
  for (const k of BLOCK_FIELDS) if (block[k] !== undefined) out[k] = block[k];
  return out;
}

// High-level actions that record history
async function actionDeleteSwitch(id) {
  const sw = switches.find(s => s.id === id);
  if (!sw) return;
  const snapshot = { name: sw.name, x: sw.x, y: sw.y, source: sw.source };
  const ref = { id };
  await deleteSwitch(id);
  renderAll();
  const label = `delete ${snapshot.name}`;
  const restore = async () => {
    if (snapshot.source === 'manual') {
      const created = await createManualSwitch({ name: snapshot.name, x: snapshot.x, y: snapshot.y });
      aliasId(resolveId(ref.id), created.id);
      ref.id = created.id;
    } else {
      await updateSwitch(resolveId(ref.id), { x: snapshot.x, y: snapshot.y });
    }
  };
  pushHistory({ label, undo: restore, redo: () => deleteSwitch(resolveId(ref.id)) });
  undoToast(snapshot.source === 'manual' ? `Deleted ${snapshot.name}` : `Removed ${snapshot.name} from the map`);
}

async function actionDeleteBlock(id, { ask = true } = {}) {
  const block = seatBlocks.find(b => b.id === id);
  if (!block) return;
  const name = block.name || 'Unnamed block';
  if (ask) {
    const ok = await confirmDialog({
      title: 'Delete seat block?',
      text: `“${name}” and its ${block.cols * block.rows} seats will be removed from the map. You can undo this.`,
    });
    if (!ok) return;
  }
  const snapshot = blockPayload(block);
  const ref = { id };
  await deleteBlock(id);
  renderAll();
  pushHistory({
    label: `delete ${name}`,
    undo: async () => {
      const created = await createBlock(snapshot);
      aliasId(resolveId(ref.id), created.id);
      ref.id = created.id;
    },
    redo: () => deleteBlock(resolveId(ref.id)),
  });
  undoToast(`Deleted ${name}`);
}

function recordMove(type, id, from, to) {
  const label = type === 'block' ? 'move seat block' : 'move switch';
  const apply = (pos) => async () => {
    const rid = resolveId(id);
    if (type === 'block') await updateBlock(rid, pos);
    else await updateSwitch(rid, pos);
  };
  pushHistory({ label, undo: apply(from), redo: apply(to) });
}

async function deleteSelection() {
  if (!selectedId) return;
  if (selectedType === 'block') await actionDeleteBlock(selectedId);
  else if (selectedType === 'switch') await actionDeleteSwitch(selectedId);
}

// ── Load data ──────────────────────────────────────────────────────────────────────
async function loadSeatMappings() {
  try {
    const data = await api('GET', '/api/seats/info');
    seatMappings = data.seats || {};
  } catch (e) {
    seatMappings = {};
  }
}
async function loadSwitches()   { switches   = await api('GET', '/api/switches'); }
async function loadSeats()      { seats      = await api('GET', '/api/seats'); }
async function loadSeatBlocks() { seatBlocks = await api('GET', '/api/seat-blocks'); }

// ── Init ───────────────────────────────────────────────────────────────────────────
async function init() {
  restoreView();
  restoreLayerPrefs();
  initCollapsibleSections();

  const results = await Promise.allSettled([
    api('GET', '/api/config'),
    loadSwitches(),
    loadSeats(),
    loadSeatMappings(),
    loadSeatBlocks(),
  ]);
  if (results[0].status === 'fulfilled') config = results[0].value;
  const failed = results.filter(r => r.status === 'rejected');
  if (failed.length) toastError('Could not load all data', failed[0].reason);

  applyConfig();

  const cachedStatus = getCache();
  if (cachedStatus) applyCachedStatus(cachedStatus);

  renderAll();
  doRefreshAll().catch(() => {});
}

function applyCachedStatus(cache) {
  for (const [id, stats] of Object.entries(cache.portStats || {})) portStats[id] = stats;
  for (const sw of switches) {
    if (cache.statuses && cache.statuses[sw.id]) sw.status = cache.statuses[sw.id];
  }
}

function applyConfig() {
  syncSection.classList.toggle('hidden', !config.netbox_enabled);
  if (!config.librenms_enabled) {
    lastUpdatedEl.textContent = 'LibreNMS not configured';
    lastUpdatedEl.title = 'Set LIBRENMS_URL and LIBRENMS_TOKEN to see live switch status';
  }
}

// ── Collapsible sections ───────────────────────────────────────────────────────
function initCollapsibleSections() {
  document.querySelectorAll('.collapsible-section').forEach(section => {
    const name = section.dataset.section;
    const header = section.querySelector('.section-header');
    let saved = null;
    try { saved = localStorage.getItem(`section-${name}`); } catch { /* ignore */ }
    if (saved === 'collapsed') section.classList.add('collapsed');
    else if (saved === 'expanded') section.classList.remove('collapsed');

    header.setAttribute('role', 'button');
    header.setAttribute('tabindex', '0');
    const toggle = () => {
      const isCollapsed = section.classList.toggle('collapsed');
      header.setAttribute('aria-expanded', String(!isCollapsed));
      try { localStorage.setItem(`section-${name}`, isCollapsed ? 'collapsed' : 'expanded'); } catch { /* ignore */ }
    };
    header.setAttribute('aria-expanded', String(!section.classList.contains('collapsed')));
    header.addEventListener('click', toggle);
    header.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });
}

// ── Seat numbering ─────────────────────────────────────────────────────────────────
// Returns the seat numbers of a block in render order (row by row).
function blockSeatNumbers(block) {
  const totalSeats = block.cols * block.rows;
  const prefix = block.name ? block.name.toUpperCase() + '-' : '';
  const rotation = (block.rotation || 0) % 360;
  const base = Array.from({ length: totalSeats }, (_, i) => i + 1);

  let ordered = [];
  if (rotation >= 0 && rotation < 90) {
    ordered = [...base];
  } else if (rotation >= 90 && rotation < 180) {
    for (let row = 0; row < block.rows; row++) {
      ordered.push(...base.slice(row * block.cols, (row + 1) * block.cols).reverse());
    }
  } else if (rotation >= 180 && rotation < 270) {
    ordered = [...base].reverse();
  } else {
    for (let row = block.rows - 1; row >= 0; row--) {
      ordered.push(...base.slice(row * block.cols, (row + 1) * block.cols));
    }
  }
  if (block.reverse_numbers) ordered.reverse();
  return ordered.map(n => ({ number: `${prefix}${n}`, display: n }));
}

// ── Universal search ───────────────────────────────────────────────────────────────
let searchDebounceTimer = null;
let searchActiveIndex = -1;

function renderUniversalSearchResults() {
  const query = universalSearch.value.trim().toLowerCase();
  searchActiveIndex = -1;
  if (!query) { searchResults.innerHTML = ''; return; }

  let html = '';
  const switchMatches = switches
    .filter(s => s.placed !== false && s.name.toLowerCase().includes(query))
    .slice(0, 10);

  if (switchMatches.length) {
    html += '<div class="search-result-group"><div class="search-result-group-title">Switches</div>';
    for (const sw of switchMatches) {
      html += `
        <div class="search-result-item" data-type="switch" data-id="${escHtml(sw.id)}">
          <span class="switch-item-glyph status-${escHtml(statusBucket(sw.status))}">${statusGlyph(sw.status)}</span>
          <span class="search-result-item-name">${escHtml(sw.name)}</span>
          <span class="search-result-item-sub">${escHtml(sw.status || '')}</span>
        </div>`;
    }
    html += '</div>';
  }

  const seatMatches = [];
  for (const block of seatBlocks) {
    for (const { number } of blockSeatNumbers(block)) {
      if (number.toLowerCase().includes(query)) {
        const user = seatMappings[number]?.username || '';
        seatMatches.push({ blockId: block.id, seatNumber: number, name: number, sub: user || block.name || 'block' });
      }
      const seatData = seatMappings[number];
      if (seatData && seatData.username && seatData.username.toLowerCase().includes(query)) {
        seatMatches.push({ blockId: block.id, seatNumber: number, name: seatData.username, sub: number });
      }
    }
  }
  const uniqueSeatMatches = seatMatches
    .filter((item, index, self) => index === self.findIndex(t => t.seatNumber === item.seatNumber && t.name === item.name))
    .slice(0, 10);

  if (uniqueSeatMatches.length) {
    html += '<div class="search-result-group"><div class="search-result-group-title">Seats</div>';
    for (const seat of uniqueSeatMatches) {
      html += `
        <div class="search-result-item" data-type="seat-block" data-block-id="${escHtml(seat.blockId)}" data-seat-number="${escHtml(seat.seatNumber)}">
          <span class="search-result-item-type">Seat</span>
          <span class="search-result-item-name">${escHtml(seat.name)}</span>
          <span class="search-result-item-sub">${escHtml(seat.sub)}</span>
        </div>`;
    }
    html += '</div>';
  }

  searchResults.innerHTML = html || '<div class="search-no-results">No matches</div>';
  searchResults.querySelectorAll('.search-result-item').forEach(item => {
    item.addEventListener('click', () => handleSearchResultClick(item));
  });
}

function handleSearchResultClick(item) {
  const type = item.dataset.type;
  if (type === 'switch') {
    selectSwitch(item.dataset.id);
    focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(item.dataset.id)}"]`));
  } else if (type === 'seat-block') {
    showBlockSeatDetail(item.dataset.seatNumber);
    focusOnItem(blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(item.dataset.seatNumber)}"]`));
  }
  universalSearch.value = '';
  searchResults.innerHTML = '';
  universalSearch.blur();
}

universalSearch.addEventListener('input', () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(renderUniversalSearchResults, 150);
});
universalSearch.addEventListener('keydown', (e) => {
  const items = [...searchResults.querySelectorAll('.search-result-item')];
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!items.length) return;
    e.preventDefault();
    searchActiveIndex = (searchActiveIndex + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items.forEach((el, i) => el.classList.toggle('kbd-active', i === searchActiveIndex));
    items[searchActiveIndex].scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'Enter') {
    const target = items[searchActiveIndex] || items[0];
    if (target) handleSearchResultClick(target);
  } else if (e.key === 'Escape') {
    universalSearch.value = '';
    searchResults.innerHTML = '';
    universalSearch.blur();
  }
});

// ── Tool selection ───────────────────────────────────────────────────────────────────
const TOOL_HINTS = {
  'add-switch': 'Click on the map to place a switch · Esc to cancel',
  'add-block':  'Click on the map to place a seat block · Esc to cancel',
};

function setTool(tool) {
  currentTool = tool;
  toolSelect.classList.toggle('active', tool === 'select');
  toolAddSwitch.classList.toggle('active', tool === 'add-switch');
  toolAddBlock.classList.toggle('active', tool === 'add-block');
  wrapper.dataset.tool = tool;
  toolHint.textContent = TOOL_HINTS[tool] || '';
  toolHint.classList.toggle('hidden', !TOOL_HINTS[tool]);
  if (tool !== 'select') deselectAll();
}

toolSelect.addEventListener('click', () => setTool('select'));
toolAddSwitch.addEventListener('click', () => setTool('add-switch'));
toolAddBlock.addEventListener('click', () => setTool('add-block'));

function setSnap(on) {
  snapEnabled = on;
  btnSnap.classList.toggle('active', on);
  btnSnap.setAttribute('aria-pressed', String(on));
  writeJSON('snapEnabled', on);
}
btnSnap.addEventListener('click', () => setSnap(!snapEnabled));

// ── NetBox sync ──────────────────────────────────────────────────────────────────────
btnSync.addEventListener('click', async () => {
  btnSync.disabled = true;
  btnSync.classList.add('is-busy');
  syncInfo.classList.add('hidden');
  try {
    const synced = await api('POST', '/api/switches/sync');
    // Keep the live status we already know about
    const statusById = Object.fromEntries(switches.map(s => [s.id, s.status]));
    const manual = switches.filter(s => s.source === 'manual');
    switches = [...synced.map(s => ({ ...s, status: statusById[s.id] || s.status })), ...manual];
    renderAll();
    const unplaced = switches.filter(s => !s.placed && s.source !== 'manual').length;
    syncInfo.textContent = `Synced ${synced.length} device(s), ${unplaced} not on the map yet`;
    syncInfo.classList.remove('hidden');
    toast(`NetBox sync done: ${synced.length} device(s)`, { type: 'success' });
  } catch (e) {
    syncInfo.textContent = 'Sync failed: ' + e.message;
    syncInfo.classList.remove('hidden');
    toastError('NetBox sync failed', e);
  } finally {
    btnSync.disabled = false;
    btnSync.classList.remove('is-busy');
  }
});

// ── Coordinates ──────────────────────────────────────────────────────────────────────
function snapToGrid(value) {
  return snapEnabled ? Math.round(value / GRID_SNAP) * GRID_SNAP : Math.round(value * 100) / 100;
}
function clientToPercent(clientX, clientY) {
  const rect = wrapper.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const x = (clientX - rect.left) / rect.width * 100;
  const y = (clientY - rect.top) / rect.height * 100;
  return isFinite(x) && isFinite(y) ? { x, y } : null;
}
function updatePositionDisplay(x, y) {
  posX.textContent = snapToGrid(x).toFixed(2);
  posY.textContent = snapToGrid(y).toFixed(2);
}

// ── Floor plan click (place items, pick seats) ──────────────────────────────────
wrapper.addEventListener('click', (e) => {
  if (suppressNextClick) { suppressNextClick = false; return; }

  if (currentTool === 'select') {
    const seatEl = e.target.closest('.seat-block-seat');
    if (seatEl && seatEl.dataset.seatNumber) {
      e.stopPropagation();
      showBlockSeatDetail(seatEl.dataset.seatNumber);
    }
    return;
  }
  if (e.target.closest('.switch-marker, .seat-marker, .seat-block, .seat-block-seat')) return;

  const p = clientToPercent(e.clientX, e.clientY);
  if (!p) return;
  pendingCoords = {
    x: Math.min(100, Math.max(0, snapToGrid(p.x))),
    y: Math.min(100, Math.max(0, snapToGrid(p.y))),
  };

  if (currentTool === 'add-switch') openAddModal();
  else if (currentTool === 'add-block') openBlockModal();
});

wrapper.addEventListener('mousemove', (e) => {
  const rect = wrapper.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  addCursor.style.left = ((e.clientX - rect.left) / view.k) + 'px';
  addCursor.style.top  = ((e.clientY - rect.top) / view.k) + 'px';
  const p = clientToPercent(e.clientX, e.clientY);
  if (p) updatePositionDisplay(p.x, p.y);
});

// ── Pan & zoom ───────────────────────────────────────────────────────────────────────
function applyView() {
  wrapper.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.k})`;
  addCursor.style.transform = `translate(-50%, -50%) scale(${1 / view.k})`;
  zoomLevelEl.textContent = Math.round(view.k * 100) + '%';
}
let saveViewTimer = null;
function saveView() {
  clearTimeout(saveViewTimer);
  saveViewTimer = setTimeout(() => writeJSON('floorplanView', view), 300);
}
function restoreView() {
  const saved = readJSON('floorplanView', null);
  if (saved && isFinite(saved.x) && isFinite(saved.y) && isFinite(saved.k)) {
    view.x = saved.x; view.y = saved.y;
    view.k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, saved.k));
  }
  applyView();
}
function setView(x, y, k) {
  view.k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, k));
  view.x = x; view.y = y;
  applyView();
  saveView();
}
function zoomAt(clientX, clientY, factor) {
  const area = canvasArea.getBoundingClientRect();
  const cx = clientX - area.left;
  const cy = clientY - area.top;
  const newK = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, view.k * factor));
  const wx = (cx - view.x) / view.k;
  const wy = (cy - view.y) / view.k;
  setView(cx - wx * newK, cy - wy * newK, newK);
}
function zoomCentered(factor) {
  const area = canvasArea.getBoundingClientRect();
  zoomAt(area.left + area.width / 2, area.top + area.height / 2, factor);
}
function resetView() { setView(0, 0, 1); }

// Fit all placed items in view
function fitToContent() {
  const els = [
    ...overlay.querySelectorAll('.switch-marker'),
    ...blocksOverlay.querySelectorAll('.seat-block'),
    ...seatsOverlay.querySelectorAll('.seat-marker'),
  ];
  if (!els.length) { resetView(); return; }
  const wr = wrapper.getBoundingClientRect();
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    minX = Math.min(minX, (r.left - wr.left) / view.k);
    minY = Math.min(minY, (r.top - wr.top) / view.k);
    maxX = Math.max(maxX, (r.right - wr.left) / view.k);
    maxY = Math.max(maxY, (r.bottom - wr.top) / view.k);
  }
  const area = canvasArea.getBoundingClientRect();
  const pad = 80;
  const w = Math.max(maxX - minX, 40);
  const h = Math.max(maxY - minY, 40);
  const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.min((area.width - pad * 2) / w, (area.height - pad * 2) / h)));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  setView(area.width / 2 - cx * k, area.height / 2 - cy * k, k);
}

// Pan so an element is visible (used after search)
function focusOnItem(el) {
  if (!el) return;
  const area = canvasArea.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const margin = 60;
  if (r.left >= area.left + margin && r.right <= area.right - margin &&
      r.top >= area.top + margin && r.bottom <= area.bottom - margin) return;
  const dx = area.left + area.width / 2 - (r.left + r.width / 2);
  const dy = area.top + area.height / 2 - (r.top + r.height / 2);
  setView(view.x + dx, view.y + dy, view.k);
}

btnZoomIn.addEventListener('click',    () => zoomCentered(ZOOM_STEP));
btnZoomOut.addEventListener('click',   () => zoomCentered(1 / ZOOM_STEP));
btnZoomReset.addEventListener('click', resetView);
zoomLevelEl.addEventListener('click',  resetView);
btnCenter.addEventListener('click',    fitToContent);

// Wheel / trackpad pinch zooms toward the cursor
canvasArea.addEventListener('wheel', (e) => {
  if (e.target.closest('.toolbar, .zoom-bar')) return;
  e.preventDefault();
  const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
  zoomAt(e.clientX, e.clientY, Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.0015)));
}, { passive: false });

// Drag on empty space pans (left button in Select, middle button or Space anywhere)
let spaceHeld = false;
canvasArea.addEventListener('mousedown', (e) => {
  if (e.target.closest('.toolbar, .zoom-bar, .switch-marker, .seat-marker, .seat-block')) return;
  const canPan = e.button === 1 || (e.button === 0 && (currentTool === 'select' || spaceHeld));
  if (!canPan) return;
  e.preventDefault();
  panState = { startX: e.clientX, startY: e.clientY, origX: view.x, origY: view.y, moved: false };
  document.addEventListener('mousemove', onPanMove);
  document.addEventListener('mouseup', onPanUp);
});
function onPanMove(e) {
  if (!panState) return;
  const dx = e.clientX - panState.startX;
  const dy = e.clientY - panState.startY;
  if (!panState.moved && Math.hypot(dx, dy) < 3) return;
  if (!panState.moved) canvasArea.classList.add('panning');
  panState.moved = true;
  setView(panState.origX + dx, panState.origY + dy, view.k);
}
function onPanUp() {
  document.removeEventListener('mousemove', onPanMove);
  document.removeEventListener('mouseup', onPanUp);
  canvasArea.classList.remove('panning');
  if (panState && panState.moved) {
    suppressNextClick = true;
    setTimeout(() => { suppressNextClick = false; }, 0);
  } else if (panState && currentTool === 'select') {
    deselectAll(); // plain click on empty space
  }
  panState = null;
}

window.addEventListener('resize', () => {
  if (heatmapVisible) renderHeatmap();
  if (seatHeatmapVisible) renderSeatHeatmap();
});

// ── Add-switch modal ─────────────────────────────────────────────────────────────────
let activeModalTab = 'manual'; // 'netbox' | 'manual'
let isMultiselectMode = false;

function openAddModal() {
  pendingPickerDeviceId = null;
  selectedDeviceIds.clear();
  isMultiselectMode = false;
  multiselectToggle.checked = false;
  updateMultiselectCount();

  if (config.netbox_enabled) {
    modalTabs.classList.remove('hidden');
    const unplaced = switches.filter(s => !s.placed && s.source !== 'manual');
    setModalTab(unplaced.length > 0 ? 'netbox' : 'manual');
  } else {
    modalTabs.classList.add('hidden');
    setModalTab('manual');
  }

  let n = switches.filter(s => s.source === 'manual').length + 1;
  let def = `SW-${String(n).padStart(2, '0')}`;
  const names = switches.map(s => s.name);
  while (names.includes(def)) { n++; def = `SW-${String(n).padStart(2, '0')}`; }
  switchNameInput.value = def;

  modalBackdrop.classList.remove('hidden');

  if (activeModalTab === 'netbox') {
    deviceFilter.value = '';
    renderDevicePicker('');
    deviceFilter.focus();
  } else {
    switchNameInput.focus();
    switchNameInput.select();
  }
}

function setModalTab(tab) {
  activeModalTab = tab;
  tabNetbox.classList.toggle('active', tab === 'netbox');
  tabManual.classList.toggle('active', tab === 'manual');
  modalNetbox.classList.toggle('hidden', tab !== 'netbox');
  modalManual.classList.toggle('hidden', tab !== 'manual');
}

tabNetbox.addEventListener('click', () => {
  setModalTab('netbox');
  deviceFilter.value = '';
  renderDevicePicker('');
  deviceFilter.focus();
});
tabManual.addEventListener('click', () => {
  setModalTab('manual');
  switchNameInput.focus();
  switchNameInput.select();
});

function renderDevicePicker(filter) {
  const unplaced = switches.filter(s =>
    !s.placed && s.source !== 'manual' && s.name.toLowerCase().includes(filter.toLowerCase()));
  if (!unplaced.length) {
    deviceList.innerHTML = `<div class="device-empty">No devices left to place${filter ? ' matching the filter' : ''}</div>`;
    return;
  }
  deviceList.innerHTML = '';
  for (const dev of unplaced) {
    const item = document.createElement('div');
    const isSelected = selectedDeviceIds.has(dev.id);
    item.className = 'device-item' + (isMultiselectMode ? ' multiselect-mode' : '') +
      (dev.id === pendingPickerDeviceId || isSelected ? ' selected' : '');
    item.dataset.id = dev.id;
    item.innerHTML = `
      ${isMultiselectMode ? `<span class="device-item-checkbox ${isSelected ? 'checked' : ''}"></span>` : ''}
      <span class="device-item-name">${escHtml(dev.name)}</span>
      <span class="device-item-badge">${escHtml(dev.netbox_status || '')}</span>`;
    item.addEventListener('click', () => {
      if (isMultiselectMode) {
        if (selectedDeviceIds.has(dev.id)) selectedDeviceIds.delete(dev.id);
        else selectedDeviceIds.add(dev.id);
        updateMultiselectCount();
        renderDevicePicker(filter);
      } else {
        pendingPickerDeviceId = dev.id;
        for (const el of deviceList.querySelectorAll('.device-item'))
          el.classList.toggle('selected', el.dataset.id === dev.id);
      }
    });
    item.addEventListener('dblclick', () => { if (!isMultiselectMode) modalConfirm.click(); });
    deviceList.appendChild(item);
  }
}

function updateMultiselectCount() {
  const count = selectedDeviceIds.size;
  multiselectCount.textContent = `${count} selected`;
  multiselectCount.style.display = count > 0 ? 'block' : 'none';
}

deviceFilter.addEventListener('input', () => renderDevicePicker(deviceFilter.value));
deviceFilter.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  modalConfirm.click();
  if (e.key === 'Escape') closeAddModal();
});

multiselectToggle.addEventListener('change', () => {
  isMultiselectMode = multiselectToggle.checked;
  if (isMultiselectMode) {
    if (pendingPickerDeviceId) { selectedDeviceIds.add(pendingPickerDeviceId); pendingPickerDeviceId = null; }
  } else {
    selectedDeviceIds.clear();
  }
  updateMultiselectCount();
  renderDevicePicker(deviceFilter.value);
});

function closeAddModal() {
  modalBackdrop.classList.add('hidden');
  pendingCoords = null;
  pendingPickerDeviceId = null;
  selectedDeviceIds.clear();
  isMultiselectMode = false;
}

modalCancel.addEventListener('click', closeAddModal);
modalBackdrop.addEventListener('click', (e) => { if (e.target === modalBackdrop) closeAddModal(); });
switchNameInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  modalConfirm.click();
  if (e.key === 'Escape') closeAddModal();
});

modalConfirm.addEventListener('click', async () => {
  if (!pendingCoords) return;
  modalConfirm.disabled = true;
  try {
    if (activeModalTab === 'netbox' && config.netbox_enabled) {
      const ids = isMultiselectMode ? Array.from(selectedDeviceIds)
                                    : (pendingPickerDeviceId ? [pendingPickerDeviceId] : []);
      if (!ids.length) { deviceFilter.focus(); return; }

      // Place several devices in a grid around the click point
      const cols = Math.ceil(Math.sqrt(ids.length));
      const rowsCount = Math.ceil(ids.length / cols);
      const spacing = 8; // % of the floor plan
      const placements = ids.map((id, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;
        return {
          id,
          x: Math.max(0, Math.min(100, pendingCoords.x + (col - (cols - 1) / 2) * spacing)),
          y: Math.max(0, Math.min(100, pendingCoords.y + (row - (rowsCount - 1) / 2) * spacing)),
        };
      });

      const placed = [];
      for (const p of placements) {
        try {
          await updateSwitch(p.id, { x: p.x, y: p.y });
          placed.push(p);
        } catch (e) {
          const name = switches.find(s => s.id === p.id)?.name || p.id;
          toastError(`Could not place ${name}`, e);
        }
      }
      closeAddModal();
      setTool('select');
      renderAll();
      if (placed.length) {
        if (placed.length === 1) selectSwitch(placed[0].id);
        pushHistory({
          label: placed.length === 1 ? 'place switch' : `place ${placed.length} switches`,
          undo: async () => { for (const p of placed) await deleteSwitch(resolveId(p.id)); },
          redo: async () => { for (const p of placed) await updateSwitch(resolveId(p.id), { x: p.x, y: p.y }); },
        });
      }
    } else {
      const name = switchNameInput.value.trim();
      if (!name) { switchNameInput.focus(); return; }
      const data = { name, ...pendingCoords };
      const sw = await createManualSwitch(data);
      const ref = { id: sw.id };
      closeAddModal();
      setTool('select');
      renderAll();
      selectSwitch(sw.id);
      pushHistory({
        label: `add ${name}`,
        undo: () => deleteSwitch(resolveId(ref.id)),
        redo: async () => {
          const created = await createManualSwitch(data);
          aliasId(resolveId(ref.id), created.id);
          ref.id = created.id;
        },
      });
    }
  } catch (e) {
    toastError('Could not place switch', e);
  } finally {
    modalConfirm.disabled = false;
  }
});

// ── Seat block modal ─────────────────────────────────────────────────────────────────
const blockBackdrop    = $('block-backdrop');
const blockName        = $('block-name');
const blockCols        = $('block-cols');
const blockRows        = $('block-rows');
const blockSpacingX    = $('block-spacing-x');
const blockSpacingY    = $('block-spacing-y');
const blockRotation    = $('block-rotation');
const blockReverseNumbersModal = $('block-reverse-numbers-modal');
const blockCancel      = $('block-cancel');
const blockConfirm     = $('block-confirm');
const blockPreview     = $('block-preview');

function blockModalValues() {
  return {
    name: blockName.value.trim(),
    cols: Math.max(1, parseInt(blockCols.value) || 1),
    rows: Math.max(1, parseInt(blockRows.value) || 1),
    seat_width: 1.5,
    seat_height: 1.5,
    spacing_x: parseFloat(blockSpacingX.value) || 0.5,
    spacing_y: parseFloat(blockSpacingY.value) || 1,
    numbering_pattern: 'blockname_number',
    reverse_numbers: blockReverseNumbersModal.checked,
    rotation: parseInt(blockRotation.value) || 0,
  };
}
function updateBlockPreview() {
  const v = blockModalValues();
  const nums = blockSeatNumbers(v);
  const first = nums[0]?.number;
  const last = nums[nums.length - 1]?.number;
  blockPreview.textContent = `${nums.length} seat${nums.length === 1 ? '' : 's'}` +
    (first ? ` · numbered ${first}${nums.length > 1 ? ` to ${last}` : ''}` : '');
}
[blockName, blockCols, blockRows, blockRotation].forEach(el => el.addEventListener('input', updateBlockPreview));
blockReverseNumbersModal.addEventListener('change', updateBlockPreview);

function openBlockModal() {
  blockName.value = '';
  blockCols.value = '8';
  blockRows.value = '1';
  blockSpacingX.value = '0.5';
  blockSpacingY.value = '1';
  blockRotation.value = '0';
  blockReverseNumbersModal.checked = false;
  updateBlockPreview();
  blockBackdrop.classList.remove('hidden');
  blockName.focus();
}

function closeBlockModal() {
  blockBackdrop.classList.add('hidden');
  pendingCoords = null;
}

blockCancel.addEventListener('click', closeBlockModal);
blockBackdrop.addEventListener('click', (e) => { if (e.target === blockBackdrop) closeBlockModal(); });
blockBackdrop.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') blockConfirm.click();
});
blockConfirm.addEventListener('click', async () => {
  if (!pendingCoords) return;
  blockConfirm.disabled = true;
  try {
    const data = { ...blockModalValues(), ...pendingCoords };
    const block = await createBlock(data);
    const ref = { id: block.id };
    closeBlockModal();
    setTool('select');
    renderAll();
    selectBlock(block.id);
    pushHistory({
      label: `add ${data.name || 'seat block'}`,
      undo: () => deleteBlock(resolveId(ref.id)),
      redo: async () => {
        const created = await createBlock(data);
        aliasId(resolveId(ref.id), created.id);
        ref.id = created.id;
      },
    });
  } catch (e) {
    toastError('Could not create seat block', e);
  } finally {
    blockConfirm.disabled = false;
  }
});

// ── Rendering ──────────────────────────────────────────────────────────────────────
function renderAll() {
  renderOverlay();
  renderSeats();
  renderBlocks();
  renderSidebar();
  updateHeroStats();
  updateEmptyState();
  if (heatmapVisible) renderHeatmap();
  if (seatHeatmapVisible) renderSeatHeatmap();
}

function matchesStatusFilter(sw) {
  return statusFilter === 'all' || statusBucket(sw.status) === statusFilter;
}

function renderOverlay() {
  overlay.innerHTML = '';
  for (const sw of switches) {
    if (sw.placed !== false && sw.x != null) overlay.appendChild(createMarker(sw));
  }
}

function renderSeats() {
  seatsOverlay.innerHTML = '';
  for (const seat of seats) seatsOverlay.appendChild(createSeatMarker(seat));
}

function renderBlocks() {
  blocksOverlay.innerHTML = '';
  for (const block of seatBlocks) blocksOverlay.appendChild(createBlockMarker(block));
}

function updateEmptyState() {
  const placed = switches.some(s => s.placed !== false && s.x != null);
  emptyCanvas.classList.toggle('hidden', placed || seatBlocks.length > 0 || seats.length > 0);
}

function renderSidebar() {
  const placed = switches.filter(s => s.placed !== false);
  switchCount.textContent = placed.length;

  const searchTerm = switchSearch.value.trim().toLowerCase();
  const filtered = placed.filter(s => s.name.toLowerCase().includes(searchTerm) && matchesStatusFilter(s));

  listFilter.classList.toggle('hidden', statusFilter === 'all');
  listFilterText.textContent = statusFilter === 'all' ? '' : `Showing ${statusFilter} switches only`;

  if (!filtered.length) {
    switchList.innerHTML = placed.length
      ? '<p class="empty-hint">No switches match.</p>'
      : '<p class="empty-hint">No switches placed yet. Press <kbd>S</kbd> and click on the map.</p>';
    return;
  }

  // Offline first, then by name, so problems surface at the top
  const order = { offline: 0, warning: 1, unknown: 2, online: 3 };
  filtered.sort((a, b) => (order[a.status] ?? 2) - (order[b.status] ?? 2) || a.name.localeCompare(b.name));

  const frag = document.createDocumentFragment();
  for (const sw of filtered) {
    const item = document.createElement('div');
    item.className = 'switch-item' + (sw.id === selectedId && selectedType === 'switch' ? ' active' : '');
    item.dataset.id = sw.id;
    item.tabIndex = 0;

    const stats = portStats[sw.id];
    const parts = [];
    if (stats && stats.total_traffic_bps != null) parts.push(fmtBps(stats.total_traffic_bps));
    if (stats && stats.temperature != null) parts.push(stats.temperature + '°C');
    const detail = parts.length ? parts.join(' · ') : (sw.status || 'unknown');

    item.innerHTML = `
      <span class="switch-item-glyph status-${escHtml(statusBucket(sw.status))}" title="${escHtml(sw.status || 'unknown')}">${statusGlyph(sw.status)}</span>
      <span class="switch-item-name">${escHtml(sw.name)}</span>
      <span class="switch-item-status">${escHtml(detail)}</span>`;
    const activate = () => {
      selectSwitch(sw.id);
      focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(sw.id)}"]`));
    };
    item.addEventListener('click', activate);
    item.addEventListener('keydown', (e) => { if (e.key === 'Enter') activate(); });
    frag.appendChild(item);
  }
  switchList.innerHTML = '';
  switchList.appendChild(frag);
}

function createMarker(sw) {
  const el = document.createElement('div');
  const isSelected = sw.id === selectedId && selectedType === 'switch';
  el.className = 'switch-marker' + (isSelected ? ' selected' : '') + (matchesStatusFilter(sw) ? '' : ' dimmed');
  el.dataset.id = sw.id;
  el.style.left = sw.x + '%';
  el.style.top  = sw.y + '%';
  el.title = `${sw.name} · ${sw.status || 'unknown'}`;
  const hideLabel = getDeviceSetting(sw.id, 'hideLabel');
  el.innerHTML = `
    <div class="switch-pin status-${escHtml(sw.status || 'unknown')}">${pinSVG(sw.status)}</div>
    ${hideLabel ? '' : `<div class="switch-label">${escHtml(sw.name)}</div>`}`;
  el.addEventListener('mousedown', onMarkerMouseDown);
  el.addEventListener('contextmenu', onMarkerContextMenu);
  return el;
}

function createSeatMarker(seat) {
  const el = document.createElement('div');
  const isSelected = selectedId === seat.id && selectedType === 'seat';
  el.className = 'seat-marker' + (isSelected ? ' selected' : '');
  el.dataset.id = seat.id;
  el.dataset.type = 'seat';
  if (seat.number) el.dataset.seatNumber = seat.number;
  el.style.left = seat.x + '%';
  el.style.top = seat.y + '%';
  el.style.transform = `translate(-50%, -50%) rotate(${seat.rotation || 0}deg)`;
  const typeChar = { chair: '☐', desk: '▭', booth: '▢', vip: '★' }[seat.type] || '☐';
  el.innerHTML = `
    <div class="seat-icon">${typeChar}</div>
    ${seat.number ? `<div class="seat-number">${escHtml(seat.number)}</div>` : ''}`;
  return el;
}

function createBlockMarker(block) {
  const el = document.createElement('div');
  const isSelected = selectedId === block.id && selectedType === 'block';
  el.className = 'seat-block' + (isSelected ? ' selected' : '');
  el.dataset.id = block.id;
  el.dataset.type = 'block';
  el.style.left = block.x + '%';
  el.style.top = block.y + '%';
  const rotation = (block.rotation || 0) % 360;
  el.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;

  let html = block.name ? `<div class="seat-block-label">${escHtml(block.name)}</div>` : '';
  const numbers = blockSeatNumbers(block);
  const counterRotation = rotation ? `transform: rotate(${-rotation}deg);` : '';
  let i = 0;
  for (let row = 0; row < block.rows; row++) {
    html += '<div class="seat-block-row">';
    for (let col = 0; col < block.cols; col++) {
      const { number, display } = numbers[i++];
      const user = seatMappings[number]?.username;
      const cls = 'seat-block-seat' + (user ? ' has-user' : '') +
                  (selectedType === 'seat' && currentBlockSeatNumber === number ? ' selected' : '');
      const title = user ? `${number} · ${user}` : number;
      html += `<div class="${cls}" style="${counterRotation}" data-seat-number="${escHtml(number)}" title="${escHtml(title)}">${escHtml(display)}</div>`;
    }
    html += '</div>';
  }
  el.innerHTML = html;

  el.addEventListener('mousedown', onBlockMouseDown);
  el.addEventListener('contextmenu', onBlockContextMenu);
  return el;
}

// ── Selection & inspector ────────────────────────────────────────────────────────────────
function hideInspectors() {
  detailPanel.classList.add('hidden');
  blockDetailPanel.classList.add('hidden');
  blockSeatDetailPanel.classList.add('hidden');
}

function markSelection() {
  for (const m of overlay.querySelectorAll('.switch-marker'))
    m.classList.toggle('selected', selectedType === 'switch' && m.dataset.id === selectedId);
  for (const m of blocksOverlay.querySelectorAll('.seat-block'))
    m.classList.toggle('selected', selectedType === 'block' && m.dataset.id === selectedId);
  for (const s of blocksOverlay.querySelectorAll('.seat-block-seat'))
    s.classList.toggle('selected', selectedType === 'seat' && s.dataset.seatNumber === currentBlockSeatNumber);
  for (const item of switchList.querySelectorAll('.switch-item'))
    item.classList.toggle('active', selectedType === 'switch' && item.dataset.id === selectedId);
}

function selectSwitch(id) {
  if (!id) { deselectAll(); return; }
  const sw = switches.find(s => s.id === id);
  if (!sw) { deselectAll(); return; }

  selectedId = id;
  selectedType = 'switch';
  currentBlockSeatNumber = null;
  markSelection();
  hideInspectors();

  detailName.textContent = sw.name;
  setStatusBadge(sw.status);
  ddSource.textContent   = sw.source === 'manual' ? 'Manual' : 'NetBox';
  ddPosition.textContent = sw.x != null ? `${Number(sw.x).toFixed(1)}% / ${Number(sw.y).toFixed(1)}%` : '—';

  const hasNetbox = sw.netbox_status !== undefined;
  dtNetboxStatus.classList.toggle('hidden', !hasNetbox);
  ddNetboxStatus.classList.toggle('hidden', !hasNetbox);
  if (hasNetbox) ddNetboxStatus.textContent = sw.netbox_status;

  detailLibrenms.style.display = config.librenms_enabled ? '' : 'none';
  populateLnmsFields({ hostname: sw.name, status: sw.status, ...(portStats[id] || {}) });
  if (config.librenms_enabled) fetchSwitchStatus(id);

  settingExcludeHeatmap.checked = getDeviceSetting(id, 'excludeHeatmap');
  settingHideLabel.checked      = getDeviceSetting(id, 'hideLabel');

  detailPanel.classList.remove('hidden');
}

function setStatusBadge(status) {
  detailStatusBadge.textContent = status || 'unknown';
  detailStatusBadge.className = `detail-status-badge status-${status || 'unknown'}`;
}

function storePortStats(id, data) {
  if (data.up_ports != null) {
    portStats[id] = {
      up_ports:          data.up_ports,
      total_ports:       data.total_ports,
      traffic_util:      data.traffic_util      ?? null,
      total_traffic_bps: data.total_traffic_bps ?? null,
      temperature:       data.temperature       ?? null,
    };
  }
}

async function fetchSwitchStatus(id) {
  try {
    const data = await api('GET', `/api/switches/${id}/status`);
    const sw = switches.find(s => s.id === id);
    if (sw) sw.status = data.status;
    storePortStats(id, data);
    if (selectedId === id && selectedType === 'switch') {
      setStatusBadge(data.status);
      populateLnmsFields(data);
    }
    renderOverlay();
    renderSidebar();
    markSelection();
    updateHeroStats();
    saveStatusCache();
  } catch (e) {
    if (selectedId === id) ddLnmsStatus.textContent = 'Lookup failed';
  }
}

function deselectAll() {
  selectedId = null;
  selectedType = null;
  currentBlockSeatNumber = null;
  currentBlockSeatResolution = null;
  hideInspectors();
  markSelection();
}

// ── Seat inspector ───────────────────────────────────────────────────────────────────
let currentBlockSeatNumber = null;
let currentBlockSeatResolution = null;

function resetSeatNetworkFields() {
  for (const el of [blockSeatDdMac, blockSeatDdSwitch, blockSeatDdPort, blockSeatDdVlan,
                    blockSeatDdPortStatus, blockSeatDdTotalTraffic, blockSeatDdDownload,
                    blockSeatDdUpload, blockSeatDdPortSpeed]) {
    el.textContent = '—';
    el.style.color = '';
  }
}
function setResolution(text, tone) {
  blockSeatResolutionStatus.textContent = text;
  blockSeatResolutionStatus.style.color = tone ? `var(--${tone})` : '';
}

async function showBlockSeatDetail(seatNumber) {
  deselectAll();
  selectedType = 'seat';
  currentBlockSeatNumber = seatNumber;
  currentBlockSeatResolution = null;
  markSelection();

  const seatData = seatMappings[seatNumber];
  blockSeatDetailNumber.textContent = seatNumber;
  blockSeatDdNumber.textContent = seatNumber;
  blockSeatDdPosition.textContent = seatNumber;
  resetSeatNetworkFields();

  if (!seatData) {
    blockSeatUserBadge.textContent = 'Not mapped';
    blockSeatUserBadge.className = 'detail-status-badge badge-plain';
    blockSeatDdUsername.textContent = '—';
    blockSeatDdIp.textContent = '—';
    setResolution('This seat has no entry in seats.json.', 'warning');
    blockSeatDetailPanel.classList.remove('hidden');
    return;
  }

  blockSeatUserBadge.textContent = seatData.username || 'No user';
  blockSeatUserBadge.className = 'detail-status-badge badge-plain' + (seatData.username ? ' status-online' : '');
  blockSeatDdUsername.textContent = seatData.username || '—';
  blockSeatDdIp.textContent = seatData.ip_address || '—';
  blockSeatDetailPanel.classList.remove('hidden');

  if (!seatData.ip_address) {
    setResolution('No IP address configured for this seat.', 'warning');
    return;
  }

  setResolution('Looking up switch port…');
  try {
    const result = await api('GET', `/api/resolve/${encodeURIComponent(seatData.ip_address)}`);
    if (currentBlockSeatNumber !== seatNumber) return; // user moved on
    currentBlockSeatResolution = result;
    blockSeatDdMac.textContent = result.mac || '—';
    blockSeatDdSwitch.textContent = result.device_name || result.hostname || '—';
    blockSeatDdPort.textContent = result.port || '—';
    blockSeatDdVlan.textContent = result.vlan || '—';

    let portUsage = null;
    if (result.stats) {
      const stats = result.stats;
      blockSeatDdPortStatus.textContent = stats.ifOperStatus || '—';
      blockSeatDdPortStatus.style.color = stats.ifOperStatus === 'up' ? 'var(--success)' : 'var(--danger)';
      const inRate = (parseFloat(stats.ifInOctets_rate) || 0) * 8;
      const outRate = (parseFloat(stats.ifOutOctets_rate) || 0) * 8;
      const speedBps = parseFloat(stats.ifSpeed) || 0;
      blockSeatDdTotalTraffic.textContent = fmtBps(inRate + outRate);
      blockSeatDdDownload.textContent = fmtBps(inRate);
      blockSeatDdUpload.textContent = fmtBps(outRate);
      blockSeatDdPortSpeed.textContent = fmtBps(speedBps);
      portUsage = { total_bps: inRate + outRate, in_rate_bps: inRate, out_rate_bps: outRate,
                    status: stats.ifOperStatus, speed_bps: speedBps };
    }
    setResolution(`Found via ${result.arp_source || 'the LibreNMS ARP table'}.`, 'success');

    if (seatHeatmapVisible) {
      seatHeatmapData.seats = seatHeatmapData.seats || {};
      seatHeatmapData.seats[seatNumber] = {
        username: seatData.username, ip_address: seatData.ip_address, resolved: true,
        port_usage: portUsage, device_name: result.device_name, port: result.port,
        vlan: result.vlan, mac: result.mac,
      };
      renderSeatHeatmap();
    }
  } catch (e) {
    if (currentBlockSeatNumber !== seatNumber) return;
    resetSeatNetworkFields();
    setResolution(`Lookup failed: ${e.message}`, 'danger');
    if (seatHeatmapVisible) {
      seatHeatmapData.seats = seatHeatmapData.seats || {};
      seatHeatmapData.seats[seatNumber] = {
        username: seatData.username, ip_address: seatData.ip_address,
        resolved: false, port_usage: null, error: e.message || 'Could not resolve',
      };
      renderSeatHeatmap();
    }
  }
}

// ── Block inspector ──────────────────────────────────────────────────────────────────
function selectBlock(id) {
  if (!id) { deselectAll(); return; }
  const block = seatBlocks.find(b => b.id === id);
  if (!block) { deselectAll(); return; }

  selectedId = id;
  selectedType = 'block';
  currentBlockSeatNumber = null;
  markSelection();
  hideInspectors();
  fillBlockInspector(block);
  blockDetailPanel.classList.remove('hidden');
}

function fillBlockInspector(block) {
  blockDetailName.textContent = block.name || 'Unnamed block';
  blockDdName.textContent = block.name || '—';
  blockDdPosition.textContent = `${Number(block.x).toFixed(1)}% / ${Number(block.y).toFixed(1)}%`;
  blockDdSize.textContent = `${block.cols} × ${block.rows} · ${block.cols * block.rows} seats`;
  blockDdRotation.textContent = `${block.rotation || 0}°`;

  blockEditName.value = block.name || '';
  blockEditCols.value = block.cols;
  blockEditRows.value = block.rows;
  setRotationInput(block.rotation || 0);
  blockReverseNumbers.checked = !!block.reverse_numbers;
}

function setRotationInput(deg) {
  blockEditRotation.value = deg;
  for (const b of blockEditRotationSeg.querySelectorAll('button'))
    b.classList.toggle('active', Number(b.dataset.rot) === Number(deg));
}
blockEditRotationSeg.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-rot]');
  if (b) setRotationInput(Number(b.dataset.rot));
});
blockEditRotation.addEventListener('input', () => setRotationInput(parseInt(blockEditRotation.value) || 0));

blockEditForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedId || selectedType !== 'block') return;
  const block = seatBlocks.find(b => b.id === selectedId);
  if (!block) return;
  const patch = {
    name: blockEditName.value.trim(),
    cols: Math.min(50, Math.max(1, parseInt(blockEditCols.value) || block.cols)),
    rows: Math.min(20, Math.max(1, parseInt(blockEditRows.value) || block.rows)),
    rotation: parseInt(blockEditRotation.value) || 0,
    reverse_numbers: blockReverseNumbers.checked,
  };
  const before = Object.fromEntries(Object.keys(patch).map(k => [k, block[k]]));
  const id = block.id;
  try {
    await updateBlock(id, patch);
    pushHistory({
      label: 'edit seat block',
      undo: () => updateBlock(resolveId(id), before),
      redo: () => updateBlock(resolveId(id), patch),
    });
    renderAll();
    selectBlock(id);
    toast('Seat block saved', { type: 'success', duration: 2500 });
  } catch (err) {
    toastError('Could not save seat block', err);
  }
});

blockDetailDuplicate.addEventListener('click', async () => {
  if (!selectedId || selectedType !== 'block') return;
  const original = seatBlocks.find(b => b.id === selectedId);
  if (!original) return;
  const data = {
    ...blockPayload(original),
    name: `${original.name || 'Block'} (copy)`,
    numbering_pattern: 'blockname_number',
    x: Math.min(95, original.x + 5),
    y: Math.min(95, original.y + 5),
  };
  try {
    const dup = await createBlock(data);
    const ref = { id: dup.id };
    renderAll();
    selectBlock(dup.id);
    pushHistory({
      label: 'duplicate seat block',
      undo: () => deleteBlock(resolveId(ref.id)),
      redo: async () => {
        const created = await createBlock(data);
        aliasId(resolveId(ref.id), created.id);
        ref.id = created.id;
      },
    });
  } catch (e) {
    toastError('Could not duplicate seat block', e);
  }
});

blockDetailDelete.addEventListener('click', () => {
  if (selectedId && selectedType === 'block') actionDeleteBlock(selectedId);
});
blockDetailClose.addEventListener('click', deselectAll);
blockSeatDetailClose.addEventListener('click', deselectAll);

// ── Switch inspector wiring ────────────────────────────────────────────────────────────────
function setBar(barEl, valueEl, pct) {
  const p = pct != null ? Math.min(100, Math.max(0, pct)) : null;
  if (p == null) {
    barEl.style.width = '0%';
    barEl.className = 'resource-bar';
    valueEl.textContent = '—';
    return;
  }
  barEl.style.width = p + '%';
  barEl.className = 'resource-bar' + (p >= 90 ? ' crit' : p >= 70 ? ' warn' : '');
  valueEl.textContent = p + '%';
}

function fmtBps(bps) {
  if (bps == null) return null;
  if (bps >= 1e9) return (bps / 1e9).toFixed(1) + ' Gbps';
  if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' Mbps';
  if (bps >= 1e3) return (bps / 1e3).toFixed(1) + ' Kbps';
  return Math.round(bps) + ' bps';
}

function populateLnmsFields(data) {
  ddHostname.textContent   = data.hostname || '—';
  ddLnmsStatus.textContent = data.status   || '—';
  ddIp.textContent         = data.ip       || '—';

  let portsText = '—';
  if (data.up_ports != null) {
    portsText = `${data.up_ports} / ${data.total_ports ?? '?'}`;
    const rate = fmtBps(data.total_traffic_bps);
    if (rate) portsText += ` · ${rate}`;
  }
  ddPorts.textContent = portsText;
  ddTemperature.textContent = data.temperature != null ? `${data.temperature}°C` : '—';
  setBar(barCpu, ddCpu, data.cpu_load ?? null);
  setBar(barMem, ddMem, data.mem_percent ?? null);
}

detailClose.addEventListener('click', deselectAll);

settingExcludeHeatmap.addEventListener('change', () => {
  if (!selectedId) return;
  setDeviceSetting(selectedId, 'excludeHeatmap', settingExcludeHeatmap.checked);
  if (heatmapVisible) renderHeatmap();
});
settingHideLabel.addEventListener('change', () => {
  if (!selectedId) return;
  setDeviceSetting(selectedId, 'hideLabel', settingHideLabel.checked);
  renderOverlay();
  markSelection();
});

detailBtnRename.addEventListener('click', () => {
  if (selectedId && selectedType === 'switch') openRenameModal(selectedId);
});
detailBtnDelete.addEventListener('click', () => {
  if (selectedId && selectedType === 'switch') actionDeleteSwitch(selectedId);
});
detailBtnRefresh.addEventListener('click', async () => {
  if (!selectedId) return;
  detailBtnRefresh.disabled = true;
  detailBtnRefresh.classList.add('is-busy');
  try { await fetchSwitchStatus(selectedId); }
  finally {
    detailBtnRefresh.disabled = false;
    detailBtnRefresh.classList.remove('is-busy');
  }
});

// ── Drag ─────────────────────────────────────────────────────────────────────────────
function startDrag(e, type, item, marker) {
  dragState = {
    id: item.id,
    type,
    startX: e.clientX,
    startY: e.clientY,
    origX: item.x,
    origY: item.y,
    wrapperRect: wrapper.getBoundingClientRect(),
    moved: false,
  };
  marker.classList.add('dragging');
  document.addEventListener('mousemove', onDocMouseMove);
  document.addEventListener('mouseup', onDocMouseUp);
}

function onMarkerMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();
  const marker = e.currentTarget;
  const sw = switches.find(s => s.id === marker.dataset.id);
  if (!sw) return;
  selectSwitch(sw.id);
  startDrag(e, 'switch', sw, marker);
}

function onBlockMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();
  const marker = e.currentTarget;
  const block = seatBlocks.find(b => b.id === marker.dataset.id);
  if (!block) return;
  // Clicking a seat selects the seat (on click); dragging moves the whole block
  if (!e.target.closest('.seat-block-seat')) selectBlock(block.id);
  startDrag(e, 'block', block, marker);
}

function onDocMouseMove(e) {
  if (!dragState) return;
  const { id, type, startX, startY, origX, origY, wrapperRect } = dragState;
  const dx = e.clientX - startX;
  const dy = e.clientY - startY;
  if (!dragState.moved && Math.hypot(dx, dy) < 3) return;
  if (!dragState.moved && type === 'block' && selectedId !== id) selectBlock(id);
  dragState.moved = true;

  const newX = Math.min(100, Math.max(0, snapToGrid(origX + (dx / wrapperRect.width * 100))));
  const newY = Math.min(100, Math.max(0, snapToGrid(origY + (dy / wrapperRect.height * 100))));

  const container = type === 'block' ? blocksOverlay : overlay;
  const marker = container.querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (marker) { marker.style.left = newX + '%'; marker.style.top = newY + '%'; }
  const item = type === 'block' ? seatBlocks.find(b => b.id === id) : switches.find(s => s.id === id);
  if (item) { item.x = newX; item.y = newY; }

  updatePositionDisplay(newX, newY);
  if (heatmapVisible) renderHeatmap();
}

async function onDocMouseUp() {
  if (!dragState) return;
  document.removeEventListener('mousemove', onDocMouseMove);
  document.removeEventListener('mouseup', onDocMouseUp);

  const { id, type, moved, origX, origY } = dragState;
  dragState = null;
  const container = type === 'block' ? blocksOverlay : overlay;
  const marker = container.querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (marker) marker.classList.remove('dragging');
  if (!moved) return;

  suppressNextClick = true;
  setTimeout(() => { suppressNextClick = false; }, 0);

  const item = type === 'block' ? seatBlocks.find(b => b.id === id) : switches.find(s => s.id === id);
  if (!item) return;
  const to = { x: item.x, y: item.y };
  const from = { x: origX, y: origY };
  if (from.x === to.x && from.y === to.y) return;
  try {
    if (type === 'block') await api('PUT', `/api/seat-blocks/${id}`, to);
    else await api('PUT', `/api/switches/${id}`, to);
    recordMove(type, id, from, to);
    if (selectedId === id) {
      if (type === 'block') fillBlockInspector(item);
      else ddPosition.textContent = `${to.x.toFixed(1)}% / ${to.y.toFixed(1)}%`;
    }
  } catch (e) {
    item.x = from.x; item.y = from.y;
    renderAll();
    markSelection();
    toastError('Could not save the new position', e);
  }
}

// ── Context menu ───────────────────────────────────────────────────────────────────────
function openContextMenu(e, target) {
  contextTarget = target;
  ctxRename.textContent = target.type === 'block' ? 'Edit…' : 'Rename…';
  contextMenu.classList.remove('hidden');
  const { innerWidth, innerHeight } = window;
  const w = contextMenu.offsetWidth, h = contextMenu.offsetHeight;
  contextMenu.style.left = Math.min(e.clientX, innerWidth - w - 8) + 'px';
  contextMenu.style.top  = Math.min(e.clientY, innerHeight - h - 8) + 'px';
}
function onMarkerContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  selectSwitch(id);
  openContextMenu(e, { type: 'switch', id });
}
function onBlockContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  selectBlock(id);
  openContextMenu(e, { type: 'block', id });
}

document.addEventListener('click', () => contextMenu.classList.add('hidden'));
document.addEventListener('scroll', () => contextMenu.classList.add('hidden'), true);

ctxRename.addEventListener('click', (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  if (!contextTarget) return;
  if (contextTarget.type === 'switch') openRenameModal(contextTarget.id);
  else { selectBlock(contextTarget.id); blockEditName.focus(); blockEditName.select(); }
});
ctxDelete.addEventListener('click', (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  if (!contextTarget) return;
  if (contextTarget.type === 'switch') actionDeleteSwitch(contextTarget.id);
  else actionDeleteBlock(contextTarget.id);
});

// ── Rename modal ───────────────────────────────────────────────────────────────────────
let renameTargetId = null;

function openRenameModal(id) {
  const sw = switches.find(s => s.id === id);
  if (!sw) return;
  renameTargetId = id;
  renameInput.value = sw.name;
  renameBackdrop.classList.remove('hidden');
  renameInput.focus();
  renameInput.select();
}

renameCancel.addEventListener('click', () => renameBackdrop.classList.add('hidden'));
renameBackdrop.addEventListener('click', (e) => {
  if (e.target === renameBackdrop) renameBackdrop.classList.add('hidden');
});
renameInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  renameConfirm.click();
  if (e.key === 'Escape') renameBackdrop.classList.add('hidden');
});

renameConfirm.addEventListener('click', async () => {
  const name = renameInput.value.trim();
  if (!name || !renameTargetId) { renameInput.focus(); return; }
  const id = renameTargetId;
  const sw = switches.find(s => s.id === id);
  const oldName = sw ? sw.name : '';
  if (name === oldName) { renameBackdrop.classList.add('hidden'); return; }
  try {
    await updateSwitch(id, { name });
    renameBackdrop.classList.add('hidden');
    pushHistory({
      label: `rename ${oldName}`,
      undo: () => updateSwitch(resolveId(id), { name: oldName }),
      redo: () => updateSwitch(resolveId(id), { name }),
    });
    renderAll();
    if (selectedId === id) selectSwitch(id);
  } catch (e) {
    toastError('Could not rename switch', e);
  }
});

// ── Keyboard shortcuts ─────────────────────────────────────────────────────────────────
function isTyping(e) {
  const t = e.target;
  return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable;
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (anyModalOpen()) { closeAllModals(); return; }
    if (!contextMenu.classList.contains('hidden')) { contextMenu.classList.add('hidden'); return; }
    if (isTyping(e)) { e.target.blur(); return; }
    deselectAll();
    setTool('select');
    return;
  }
  if (isTyping(e) || anyModalOpen()) return;

  const mod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (mod && key === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
  if (mod && key === 'y') { e.preventDefault(); redo(); return; }
  if (mod) return;

  if (e.key === ' ' && !spaceHeld) { spaceHeld = true; canvasArea.classList.add('panning'); e.preventDefault(); return; }

  switch (e.key) {
    case 'Delete':
    case 'Backspace':
      if (selectedId) { e.preventDefault(); deleteSelection(); }
      break;
    case 'v': case 'V': setTool('select'); break;
    case 's': case 'S': setTool('add-switch'); break;
    case 'b': case 'B': setTool('add-block'); break;
    case 'g': case 'G': setSnap(!snapEnabled); break;
    case 'f': case 'F': fitToContent(); break;
    case '+': case '=': zoomCentered(ZOOM_STEP); break;
    case '-': case '_': zoomCentered(1 / ZOOM_STEP); break;
    case '0': resetView(); break;
    case '/': e.preventDefault(); universalSearch.focus(); break;
    case '?': shortcutsBackdrop.classList.remove('hidden'); break;
  }
});
document.addEventListener('keyup', (e) => {
  if (e.key === ' ') { spaceHeld = false; canvasArea.classList.remove('panning'); }
});

// ── Switch list filter & status chips ────────────────────────────────────────────────────
switchSearch.addEventListener('input', () => renderSidebar());

function setStatusFilter(status) {
  statusFilter = status;
  statusChips.forEach(c => c.classList.toggle('active', status !== 'all' && c.dataset.status === status));
  renderOverlay();
  renderSidebar();
  markSelection();
}
statusChips.forEach(chip => chip.addEventListener('click', () => {
  const s = chip.dataset.status;
  setStatusFilter(s === statusFilter ? 'all' : s);
}));
listFilterClear.addEventListener('click', () => setStatusFilter('all'));

// ── Refresh status ─────────────────────────────────────────────────────────────────────
async function doRefreshAll() {
  if (isRefreshing) return;
  isRefreshing = true;
  btnRefreshAll.classList.add('is-busy');
  try {
    const placed = switches.filter(s => s.placed !== false);
    let failures = 0;
    await Promise.all(placed.map(async (sw) => {
      try {
        const data = await api('GET', `/api/switches/${sw.id}/status`);
        sw.status = data.status;
        storePortStats(sw.id, data);
      } catch {
        failures++;
      }
    }));

    const allFailed = placed.length > 0 && failures === placed.length;
    if (allFailed && !lastRefreshFailed) toast('Status refresh failed. Is the server reachable?', { type: 'error' });
    lastRefreshFailed = allFailed;
    if (!allFailed) lastRefreshAt = Date.now();
    updateLastUpdated();

    renderOverlay();
    renderSidebar();
    markSelection();
    updateHeroStats();
    if (heatmapVisible) renderHeatmap();
    saveStatusCache();

    if (seatHeatmapVisible) {
      await fetchSeatHeatmapData();
      renderSeatHeatmap();
    }
  } finally {
    isRefreshing = false;
    btnRefreshAll.classList.remove('is-busy');
  }
}

function updateLastUpdated() {
  if (!config.librenms_enabled) return;
  if (lastRefreshFailed) {
    lastUpdatedEl.textContent = 'Refresh failed';
    lastUpdatedEl.className = 'last-updated error';
    return;
  }
  if (!lastRefreshAt) return;
  const secs = Math.round((Date.now() - lastRefreshAt) / 1000);
  lastUpdatedEl.textContent = secs < 5 ? 'Updated just now'
    : secs < 60 ? `Updated ${secs}s ago`
    : `Updated ${Math.round(secs / 60)} min ago`;
  lastUpdatedEl.className = 'last-updated' + (secs > 60 ? ' stale' : '');
}
setInterval(updateLastUpdated, 1000);

function saveStatusCache() {
  const statuses = {};
  for (const sw of switches) if (sw.status) statuses[sw.id] = sw.status;
  setCache({ portStats: { ...portStats }, statuses });
}

btnRefreshAll.addEventListener('click', async () => {
  if (isRefreshing) return;
  btnRefreshAll.disabled = true;
  try { await doRefreshAll(); } finally { btnRefreshAll.disabled = false; }
});

// Auto-refresh (skipped while the tab is hidden)
setInterval(() => {
  if (!document.hidden) doRefreshAll().catch(() => {});
}, REFRESH_INTERVAL);

// ── Top bar stats ──────────────────────────────────────────────────────────────────────
function updateHeroStats() {
  const placed  = switches.filter(s => s.placed !== false);
  const online  = placed.filter(s => s.status === 'online').length;
  const offline = placed.filter(s => s.status === 'offline').length;
  heroTotal.textContent   = placed.length;
  heroOnline.textContent  = online;
  heroOffline.textContent = offline;
  heroUnknown.textContent = placed.length - online - offline;
  document.querySelector('.chip-offline').classList.toggle('has-items', offline > 0);
}

// ── Layers ────────────────────────────────────────────────────────────────────────────
function setLayerButton(btn, on) {
  btn.classList.toggle('heatmap-on', on);
  btn.setAttribute('aria-pressed', String(on));
}

function setHeatmapVisible(on) {
  heatmapVisible = on;
  setLayerButton(btnHeatmap, on);
  heatCanvas.style.display = on ? 'block' : 'none';
  heatLegend.classList.toggle('hidden', !on);
  if (on) renderHeatmap();
  writeJSON('layer-heatmap', on);
}
async function setSeatHeatmapVisible(on) {
  seatHeatmapVisible = on;
  setLayerButton(btnSeatHeatmap, on);
  seatHeatCanvas.style.display = on ? 'block' : 'none';
  seatHeatLegend.classList.toggle('hidden', !on);
  writeJSON('layer-seat-heatmap', on);
  if (on) {
    await fetchSeatHeatmapData();
    renderSeatHeatmap();
  } else {
    const ctx = seatHeatCanvas.getContext('2d');
    ctx.clearRect(0, 0, seatHeatCanvas.width, seatHeatCanvas.height);
  }
}
function setLabelsAlways(on) {
  wrapper.classList.toggle('labels-always', on);
  setLayerButton(btnLabels, on);
  writeJSON('layer-labels', on);
}
function restoreLayerPrefs() {
  setSnap(readJSON('snapEnabled', true));
  setLabelsAlways(readJSON('layer-labels', false));
  if (readJSON('layer-heatmap', false)) setHeatmapVisible(true);
  if (readJSON('layer-seat-heatmap', false)) setSeatHeatmapVisible(true);
}

btnHeatmap.addEventListener('click', () => setHeatmapVisible(!heatmapVisible));
btnSeatHeatmap.addEventListener('click', () => setSeatHeatmapVisible(!seatHeatmapVisible));
btnLabels.addEventListener('click', () => setLabelsAlways(!wrapper.classList.contains('labels-always')));

// ── Heatmaps ──────────────────────────────────────────────────────────────────────────
// Colour-blind-friendly ramp shared by both heatmaps (matches the legends)
const HEAT = {
  unknown: [110, 118, 129],
  low:     [76, 154, 255],   // blue
  mid:     [46, 196, 182],   // teal
  high:    [244, 196, 48],   // yellow
  higher:  [255, 140, 66],   // orange
  max:     [214, 34, 70],    // crimson
};

async function fetchSeatHeatmapData() {
  try {
    const data = await api('GET', '/api/seats/heatmap');
    seatHeatmapData.seats = data.seats || {};
  } catch (e) {
    seatHeatmapData.seats = {};
    toastError('Could not load seat port usage', e);
  }
}

function prepareCanvas(canvas) {
  const cw = canvas.offsetWidth || wrapper.offsetWidth;
  const ch = canvas.offsetHeight || wrapper.offsetHeight;
  if (!cw || !ch) return null;
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, cw, ch);
  // Screen pixels → canvas pixels (undoes the current zoom)
  const rect = canvas.getBoundingClientRect();
  const scale = rect.width > 0 ? cw / rect.width : 1;
  return { ctx, cw, ch, rect, scale };
}

function renderSeatHeatmap() {
  if (!seatHeatmapData.seats) return;
  const c = prepareCanvas(seatHeatCanvas);
  if (!c) return;
  const { ctx, rect, scale } = c;

  for (const [seatNumber, seatData] of Object.entries(seatHeatmapData.seats)) {
    const seatEl = blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(seatNumber)}"]`) ||
                   seatsOverlay.querySelector(`[data-seat-number="${CSS.escape(seatNumber)}"]`);
    if (!seatEl) continue;

    const r = seatEl.getBoundingClientRect();
    const cx = (r.left + r.width / 2 - rect.left) * scale;
    const cy = (r.top + r.height / 2 - rect.top) * scale;

    let rgb = HEAT.unknown;
    const usage = seatData.resolved ? seatData.port_usage : null;
    if (usage && usage.status === 'up') {
      const mbps = (usage.total_bps || 0) / 1e6;
      rgb = mbps >= 500 ? HEAT.max : mbps >= 100 ? HEAT.high : mbps >= 10 ? HEAT.mid : HEAT.low;
    }

    const radius = Math.min(r.width, r.height) / 2 * scale * 0.9;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    grad.addColorStop(0,   `rgba(${rgb},0.9)`);
    grad.addColorStop(0.6, `rgba(${rgb},0.7)`);
    grad.addColorStop(1,   `rgba(${rgb},0.3)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

function renderHeatmap() {
  const c = prepareCanvas(heatCanvas);
  if (!c) return;
  const { ctx, cw, ch, rect, scale } = c;
  const baseR = Math.min(cw, ch) * 0.18;

  const visible = switches.filter(sw =>
    sw.placed !== false && sw.x != null && !getDeviceSetting(sw.id, 'excludeHeatmap') &&
    sw.status !== 'offline' && portStats[sw.id] && portStats[sw.id].total_traffic_bps != null);
  const maxThroughput = Math.max(0, ...visible.map(sw => portStats[sw.id].total_traffic_bps));

  for (const sw of visible) {
    let cx, cy;
    const pin = overlay.querySelector(`[data-id="${CSS.escape(sw.id)}"] .switch-pin`);
    if (pin) {
      const pr = pin.getBoundingClientRect();
      cx = (pr.left + pr.width / 2 - rect.left) * scale;
      cy = (pr.top + pr.height * 5 / 18 - rect.top) * scale; // pin head centre
    } else {
      cx = (sw.x / 100) * cw;
      cy = (sw.y / 100) * ch;
    }

    const throughput = portStats[sw.id].total_traffic_bps;
    const normalized = maxThroughput > 0 ? throughput / maxThroughput : 0;
    const r = baseR * Math.min(1.8, 0.6 + normalized * 1.2);
    const gbps = throughput / 1e9;
    const rgb = gbps >= 10 ? HEAT.max : gbps >= 5 ? HEAT.higher : gbps >= 1 ? HEAT.high
              : gbps >= 0.1 ? HEAT.mid : HEAT.low;

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0,    `rgba(${rgb},0.95)`);
    grad.addColorStop(0.5,  `rgba(${rgb},0.7)`);
    grad.addColorStop(0.75, `rgba(${rgb},0.3)`);
    grad.addColorStop(1,    `rgba(${rgb},0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Bootstrap ───────────────────────────────────────────────────────────────────────────
updateHistoryButtons();
init();
