// Floor plan editor: State, DOM references, storage, the API helper, toasts, dialogs, undo/redo and small utils.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
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
// ── State ───────────────────────────────────────────────────────────────────────────
let config         = { netbox_enabled: false, librenms_enabled: false };
let switches       = [];
let seats          = [];
let seatBlocks     = [];
let currentTool    = 'select';
let selectedId     = null;
let selectedType   = null; // 'switch' | 'block' | 'seat' | 'multi'
const selection    = new Set();      // selected map items as 'switch:<id>' / 'block:<id>'
let pendingCoords  = null;
let pendingPickerDeviceId = null;   // selected device in the NetBox picker tab
let selectedDeviceIds = new Set();  // selected device IDs in multiselect mode
let contextTarget  = null;          // { type: 'switch'|'block'|'multi', id }
let dragState      = null;
let panState       = null;
let marqueeState   = null;
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
const btnGrid        = $('btn-grid');
const gridEl         = $('canvas-grid');
const btnTraffic     = $('btn-traffic');
const trafficOptions = $('traffic-options');
const trafficLevelSeg = $('traffic-level');
const trafficLegendSeat   = $('traffic-legend-seat');
const trafficLegendSwitch = $('traffic-legend-switch');
const trafficSummary = $('traffic-summary');
const trafficNodataLabel = $('traffic-nodata-label');
const heatCanvas     = $('heatmap-canvas');
const seatHeatCanvas = $('seat-heatmap-canvas');

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
const blockSeatDdDownload       = $('block-seat-dd-download');
const blockSeatDdUpload         = $('block-seat-dd-upload');
const blockSeatDdPortSpeed      = $('block-seat-dd-port-speed');
const seatPortState             = $('seat-port-state');
const seatPortDesc              = $('seat-port-desc');
const seatPortErrors            = $('seat-port-errors');
const barSeatPort               = $('bar-seat-port');
const seatPortLoad              = $('seat-port-load');
const seatPortRefresh           = $('seat-port-refresh');
const seatPortLibrenms          = $('seat-port-librenms');
const seatPortPolled            = $('seat-port-polled');

// Multi-selection inspector
const multiDetailPanel   = $('multi-detail-panel');
const multiDetailName    = $('multi-detail-name');
const multiDetailSummary = $('multi-detail-summary');
const multiList          = $('multi-list');
const multiDetailClose   = $('multi-detail-close');
const multiDetailClear   = $('multi-detail-clear');
const multiDetailDelete  = $('multi-detail-delete');

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
// ── Utils ─────────────────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
