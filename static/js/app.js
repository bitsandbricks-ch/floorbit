'use strict';

// ── Pin icon (replaces bulky switch SVG) ──────────────────────────────────────
function pinSVG() {
  // Teardrop pin – colour comes from the .switch-pin CSS class
  return `<svg viewBox="0 0 14 18" xmlns="http://www.w3.org/2000/svg">
    <path d="M7 0C4.24 0 2 2.24 2 5c0 4.5 5 13 5 13s5-8.5 5-13C12 2.24 9.76 0 7 0z"
          fill="currentColor" stroke="rgba(0,0,0,0.35)" stroke-width="0.6"/>
    <circle cx="7" cy="5" r="2.4" fill="rgba(255,255,255,0.30)"/>
  </svg>`;
}

// ── State ────────────────────────────────────────────────────────────────────
let config         = { netbox_enabled: false, librenms_enabled: false };
let switches       = [];
let seats          = [];
let seatBlocks     = [];
let currentTool    = 'select';
let selectedId     = null;
let selectedType   = null; // 'switch', 'block'
let pendingCoords  = null;
let pendingPickerDeviceId = null;   // selected device in the NetBox picker tab
let selectedDeviceIds = new Set();   // selected device IDs in multiselect mode
let contextId      = null;
let dragState      = null;
let zoom           = 1;
let heatmapVisible = false;
let seatHeatmapVisible = false;
let isRefreshing   = false;
let planningMode   = true;          // always in planning/editing mode
const portStats    = {};             // { switchId: { up_ports, total_ports } }
const seatHeatmapData = {};         // { seatNumber: { port_usage, ... } }
const deviceSettings = JSON.parse(localStorage.getItem('deviceSettings') || '{}');
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.15;
const GRID_SNAP = 0.5; // Grid snap interval

// Cache configuration
const CACHE_KEY = 'switchStatusCache';
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes in milliseconds

// ── Cache helpers ──────────────────────────────────────────────────────────────
function getCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cache = JSON.parse(raw);
    // Check if cache has expired
    if (Date.now() - cache.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }
    return cache.data;
  } catch (e) {
    console.error('Error reading cache:', e);
    return null;
  }
}

function setCache(data) {
  try {
    const cache = {
      timestamp: Date.now(),
      data: data
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch (e) {
    console.error('Error writing cache:', e);
  }
}

function clearCache() {
  try {
    localStorage.removeItem(CACHE_KEY);
  } catch (e) {
    console.error('Error clearing cache:', e);
  }
}

// ── Per-device settings helpers ───────────────────────────────────────────────
function getDeviceSetting(id, key, def = false) {
  return deviceSettings[id]?.[key] ?? def;
}
function setDeviceSetting(id, key, val) {
  if (!deviceSettings[id]) deviceSettings[id] = {};
  deviceSettings[id][key] = val;
  localStorage.setItem('deviceSettings', JSON.stringify(deviceSettings));
}

// ── DOM refs ─────────────────────────────────────────────────────────────────
const wrapper          = document.getElementById('floorplan-wrapper');
const overlay          = document.getElementById('switches-overlay');
const seatsOverlay     = document.getElementById('seats-overlay');
const blocksOverlay    = document.getElementById('blocks-overlay');
const switchList       = document.getElementById('switch-list');
const switchSearch     = document.getElementById('switch-search');
const switchCount      = document.getElementById('switch-count');
const addCursor        = document.getElementById('add-cursor');
const positionDisplay  = document.getElementById('position-display');
const posX            = document.getElementById('pos-x');
const posY            = document.getElementById('pos-y');
const universalSearch  = document.getElementById('universal-search');
const searchResults    = document.getElementById('search-results');

const toolSelect       = document.getElementById('tool-select');
const toolAddSwitch    = document.getElementById('tool-add-switch');
const toolAddBlock     = document.getElementById('tool-add-block');
const btnRefreshAll    = document.getElementById('btn-refresh-all');
const syncSection      = document.getElementById('sync-section');
const btnSync          = document.getElementById('btn-sync');
const syncInfo         = document.getElementById('sync-info');

// Modal (add switch)
const modalBackdrop    = document.getElementById('modal-backdrop');
const modalTabs        = document.getElementById('modal-tabs');
const tabNetbox        = document.getElementById('tab-netbox');
const tabManual        = document.getElementById('tab-manual');
const modalNetbox      = document.getElementById('modal-netbox');
const modalManual      = document.getElementById('modal-manual');
const deviceFilter     = document.getElementById('device-filter');
const deviceList       = document.getElementById('device-list');
const switchNameInput  = document.getElementById('switch-name-input');
const modalCancel      = document.getElementById('modal-cancel');
const modalConfirm     = document.getElementById('modal-confirm');
const multiselectToggle = document.getElementById('multiselect-toggle');
const multiselectCount = document.getElementById('multiselect-count');

// Rename modal
const renameBackdrop   = document.getElementById('rename-backdrop');
const renameInput      = document.getElementById('rename-input');
const renameCancel     = document.getElementById('rename-cancel');
const renameConfirm    = document.getElementById('rename-confirm');

// Context menu
const contextMenu      = document.getElementById('context-menu');
const ctxRename        = document.getElementById('ctx-rename');
const ctxDelete        = document.getElementById('ctx-delete');

// Detail panel
const detailPanel       = document.getElementById('detail-panel');
const detailName        = document.getElementById('detail-name');
const detailStatusBadge = document.getElementById('detail-status-badge');
const ddSource          = document.getElementById('dd-source');
const ddPosition        = document.getElementById('dd-position');
const dtNetboxStatus    = document.getElementById('dt-netbox-status');
const ddNetboxStatus    = document.getElementById('dd-netbox-status');
const detailLibrenms    = document.getElementById('detail-librenms');
const ddHostname        = document.getElementById('dd-hostname');
const ddLnmsStatus      = document.getElementById('dd-lnms-status');
const ddIp              = document.getElementById('dd-ip');
const ddPorts           = document.getElementById('dd-ports');
const ddTemperature      = document.getElementById('dd-temperature');
const ddCpu             = document.getElementById('dd-cpu');
const ddMem             = document.getElementById('dd-mem');
const barCpu            = document.getElementById('bar-cpu');
const barMem            = document.getElementById('bar-mem');
const detailBtnRefresh  = document.getElementById('detail-btn-refresh');
const detailBtnRename   = document.getElementById('detail-btn-rename');
const detailBtnDelete   = document.getElementById('detail-btn-delete');
const detailClose       = document.getElementById('detail-close');
const settingExcludeHeatmap = document.getElementById('setting-exclude-heatmap');
const settingHideLabel      = document.getElementById('setting-hide-label');

// Zoom
const btnZoomIn    = document.getElementById('btn-zoom-in');
const btnZoomOut   = document.getElementById('btn-zoom-out');
const btnZoomReset = document.getElementById('btn-zoom-reset');
const zoomLevelEl  = document.getElementById('zoom-level');
const btnCenter    = document.getElementById('btn-center');
const btnHeatmap   = document.getElementById('btn-heatmap');
const btnSeatHeatmap = document.getElementById('btn-seat-heatmap');
const heatCanvas   = document.getElementById('heatmap-canvas');
const seatHeatCanvas = document.getElementById('seat-heatmap-canvas');
const heatLegend   = document.getElementById('heatmap-legend');
const seatHeatLegend = document.getElementById('seat-heatmap-legend');
// Removed: view toggle (always in planning mode)

// Seat block detail panel
const blockDetailPanel     = document.getElementById('block-detail-panel');
const blockDetailName      = document.getElementById('block-detail-name');
const blockDdName          = document.getElementById('block-dd-name');
const blockDdPosition      = document.getElementById('block-dd-position');
const blockDdSize          = document.getElementById('block-dd-size');
const blockDdRotation      = document.getElementById('block-dd-rotation');
const blockEditName        = document.getElementById('block-edit-name');
const blockEditRotation    = document.getElementById('block-edit-rotation');
const blockReverseNumbers  = document.getElementById('block-edit-reverse-numbers');
const blockDetailClose     = document.getElementById('block-detail-close');
const blockDetailSave      = document.getElementById('block-detail-save');
const blockDetailDuplicate = document.getElementById('block-detail-duplicate');
const blockDetailDelete    = document.getElementById('block-detail-delete');

// Block seat detail panel
const blockSeatDetailPanel     = document.getElementById('block-seat-detail-panel');
const blockSeatDetailNumber    = document.getElementById('block-seat-detail-number');
const blockSeatDdNumber       = document.getElementById('block-seat-dd-number');
const blockSeatDdUsername     = document.getElementById('block-seat-dd-username');
const blockSeatDdPosition     = document.getElementById('block-seat-dd-position');
const blockSeatDdIp          = document.getElementById('block-seat-dd-ip');
const blockSeatDdMac         = document.getElementById('block-seat-dd-mac');
const blockSeatDdSwitch       = document.getElementById('block-seat-dd-switch');
const blockSeatDdPort        = document.getElementById('block-seat-dd-port');
const blockSeatDdVlan        = document.getElementById('block-seat-dd-vlan');
const blockSeatResolutionStatus = document.getElementById('block-seat-resolution-status');
const blockSeatDetailClose    = document.getElementById('block-seat-detail-close');
const blockSeatDdPortStatus  = document.getElementById('block-seat-dd-port-status');
const blockSeatDdTotalTraffic = document.getElementById('block-seat-dd-total-traffic');
const blockSeatDdDownload    = document.getElementById('block-seat-dd-download');
const blockSeatDdUpload      = document.getElementById('block-seat-dd-upload');
const blockSeatDdPortSpeed   = document.getElementById('block-seat-dd-port-speed');

// Seat mapping data from seats.json
let seatMappings = {};

// Hero bar
const heroTotal    = document.getElementById('hero-total');
const heroOnline   = document.getElementById('hero-online');
const heroOffline  = document.getElementById('hero-offline');
const heroUnknown  = document.getElementById('hero-unknown');

// ── API helpers ──────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json();
}

// ── Load seat mappings ─────────────────────────────────────────────────────
async function loadSeatMappings() {
  try {
    const data = await api('GET', '/api/seats/info');
    seatMappings = data.seats || {};
  } catch (e) {
    console.error('Failed to load seat mappings:', e);
    seatMappings = {};
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  // Always use planning mode
  document.getElementById('canvas-area').classList.add('planning-mode');

  const [cfg] = await Promise.all([
    api('GET', '/api/config'),
    loadSwitches(),
    loadSeats(),
    loadSeatMappings(),
    loadSeatBlocks(),
  ]);
  config = cfg;
  applyConfig();

  // Initialize collapsible sections
  initCollapsibleSections();

  // Load cached status if available for immediate display
  const cachedStatus = getCache();
  if (cachedStatus) {
    applyCachedStatus(cachedStatus);
  }

  // Fetch fresh status in background
  doRefreshAll().catch(console.error);
}

function applyCachedStatus(cache) {
  // Apply cached port statistics
  for (const [id, stats] of Object.entries(cache.portStats || {})) {
    portStats[id] = stats;
  }

  // Apply cached status to switches
  for (const sw of switches) {
    if (cache.statuses && cache.statuses[sw.id]) {
      sw.status = cache.statuses[sw.id];
    }
  }

  // Update UI with cached data
  renderAll();
}

function applyConfig() {
  if (config.netbox_enabled) {
    syncSection.classList.remove('hidden');
  }
}

async function loadFloorplan() {
  const data = await api('GET', '/api/floorplan');
  if (data.url) {
    applyFloorplan(data.url);
  } else {
    // No floorplan loaded - remove has-image class to allow full canvas placement
    wrapper.classList.remove('has-image');
  }
}

async function loadSwitches() {
  switches = await api('GET', '/api/switches');
  renderAll();
}

async function loadSeats() {
  seats = await api('GET', '/api/seats');
  renderAll();
}

async function loadSeatBlocks() {
  seatBlocks = await api('GET', '/api/seat-blocks');
  renderAll();
}

// ── Collapsible sections ─────────────────────────────────────────────────────
function initCollapsibleSections() {
  const sections = document.querySelectorAll('.collapsible-section');

  sections.forEach(section => {
    const sectionName = section.dataset.section;
    const header = section.querySelector('.section-header');

    // Load saved state from localStorage
    const savedState = localStorage.getItem(`section-${sectionName}`);
    if (savedState === 'collapsed') {
      section.classList.add('collapsed');
    } else if (savedState === 'expanded') {
      section.classList.remove('collapsed');
    }

    // Add click handler
    header.addEventListener('click', () => {
      const isCollapsed = section.classList.toggle('collapsed');
      // Save state to localStorage
      localStorage.setItem(`section-${sectionName}`, isCollapsed ? 'collapsed' : 'expanded');
    });
  });
}

// ── Universal search ─────────────────────────────────────────────────────
let searchDebounceTimer = null;

function renderUniversalSearchResults() {
  const query = universalSearch.value.trim().toLowerCase();

  if (!query) {
    searchResults.innerHTML = '';
    return;
  }

  let html = '';

  // Search switches by name
  const switchMatches = switches
    .filter(s => s.placed !== false && s.name.toLowerCase().includes(query))
    .slice(0, 10); // Limit to 10 results

  if (switchMatches.length > 0) {
    html += '<div class="search-result-group">';
    html += '<div class="search-result-group-title">Switches</div>';
    for (const sw of switchMatches) {
      html += `
        <div class="search-result-item" data-type="switch" data-id="${escHtml(sw.id)}">
          <span class="search-result-item-type">SW</span>
          <span class="search-result-item-name">${escHtml(sw.name)}</span>
          <span class="search-result-item-sub">${escHtml(sw.status)}</span>
        </div>
      `;
    }
    html += '</div>';
  }

  // Search seats by number and username
  const seatMatches = [];

  // Individual seats
  for (const seat of seats) {
    if (seat.number && seat.number.toLowerCase().includes(query)) {
      seatMatches.push({
        type: 'seat',
        id: seat.id,
        name: seat.number,
        sub: seat.username || '',
      });
    }
  }

  // Seat blocks
  for (const block of seatBlocks) {
    const blockPrefix = block.name ? block.name.toUpperCase() + '-' : '';
    const totalSeats = block.cols * block.rows;

    for (let i = 1; i <= totalSeats; i++) {
      const seatNumber = `${blockPrefix}${i}`;

      if (seatNumber.toLowerCase().includes(query)) {
        seatMatches.push({
          type: 'seat-block',
          blockId: block.id,
          seatNumber: seatNumber,
          name: seatNumber,
          sub: block.name || 'block',
        });
      }

      const seatData = seatMappings[seatNumber];
      if (seatData && seatData.username && seatData.username.toLowerCase().includes(query)) {
        seatMatches.push({
          type: 'seat-block',
          blockId: block.id,
          seatNumber: seatNumber,
          name: seatData.username,
          sub: `${seatNumber} (${block.name || 'block'})`,
        });
      }
    }
  }

  // Deduplicate and limit seat results
  const uniqueSeatMatches = seatMatches
    .filter((item, index, self) =>
      index === self.findIndex(t =>
        t.type === item.type &&
        t.name === item.name &&
        t.sub === item.sub
      )
    )
    .slice(0, 10);

  if (uniqueSeatMatches.length > 0) {
    html += '<div class="search-result-group">';
    html += '<div class="search-result-group-title">Seats</div>';
    for (const seat of uniqueSeatMatches) {
      html += `
        <div class="search-result-item" data-type="${escHtml(seat.type)}" data-id="${escHtml(seat.id)}" data-block-id="${escHtml(seat.blockId || '')}" data-seat-number="${escHtml(seat.seatNumber || '')}">
          <span class="search-result-item-type">${seat.type === 'seat' ? 'SEAT' : 'SEAT'}</span>
          <span class="search-result-item-name">${escHtml(seat.name)}</span>
          <span class="search-result-item-sub">${escHtml(seat.sub)}</span>
        </div>
      `;
    }
    html += '</div>';
  }

  if (!html) {
    html = '<div class="search-no-results">No matches found</div>';
  }

  searchResults.innerHTML = html;

  // Add click handlers
  searchResults.querySelectorAll('.search-result-item').forEach(item => {
    item.addEventListener('click', () => handleSearchResultClick(item));
  });
}

function handleSearchResultClick(item) {
  const type = item.dataset.type;
  const id = item.dataset.id;
  const blockId = item.dataset.blockId;
  const seatNumber = item.dataset.seatNumber;

  if (type === 'switch') {
    selectSwitch(id);
  } else if (type === 'seat') {
    selectSeat(id);
  } else if (type === 'seat-block') {
    // Find the seat block and click on the specific seat
    const block = seatBlocks.find(b => b.id === blockId);
    if (block) {
      selectBlock(blockId);
      // Trigger the seat detail panel
      showBlockSeatDetail(seatNumber);
    }
  }

  // Clear search
  universalSearch.value = '';
  searchResults.innerHTML = '';
}

universalSearch.addEventListener('input', () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(renderUniversalSearchResults, 300);
});

// ── Tool selection ───────────────────────────────────────────────────────────
function setTool(tool) {
  currentTool = tool;
  toolSelect.classList.toggle('active', tool === 'select');
  toolAddSwitch.classList.toggle('active', tool === 'add-switch');
  toolAddSeat.classList.toggle('active',   tool === 'add-seat');
  toolAddBlock.classList.toggle('active',  tool === 'add-block');
  wrapper.dataset.tool = tool;
  deselectAll();
}

toolSelect.addEventListener('click', () => setTool('select'));
toolAddSwitch.addEventListener('click', () => setTool('add-switch'));
toolAddBlock.addEventListener('click', () => setTool('add-block'));

// ── NetBox sync ──────────────────────────────────────────────────────────────
btnSync.addEventListener('click', async () => {
  btnSync.disabled = true;
  syncInfo.classList.add('hidden');
  try {
    switches = await api('POST', '/api/switches/sync');
    renderAll();
    const count = switches.filter(s => !s.placed && s.source !== 'manual').length;
    syncInfo.textContent = `Synced – ${switches.length} device(s), ${count} unplaced`;
    syncInfo.classList.remove('hidden');
  } catch (e) {
    syncInfo.textContent = 'Sync failed: ' + e.message;
    syncInfo.classList.remove('hidden');
  } finally {
    btnSync.disabled = false;
  }
});

// ── Floor plan click (place items) ────────────────────────────────────────
wrapper.addEventListener('click', (e) => {
  if (currentTool === 'select') {
    // Handle clicking on individual seats within blocks
    const seatEl = e.target.closest('.seat-block-seat');
    if (seatEl && seatEl.dataset.seatNumber) {
      e.stopPropagation();
      showBlockSeatDetail(seatEl.dataset.seatNumber);
      return;
    }
    return;
  }
  if (e.target.closest('.switch-marker') || e.target.closest('.seat-marker') || e.target.closest('.seat-block') ||
      e.target.closest('.seat-block-seat') || e.target.closest('.detail-panel')) return;

  const wrapperRect = wrapper.getBoundingClientRect();
  if (!wrapperRect.width || !wrapperRect.height) return;

  // Use wrapper as coordinate system (0-100% range)
  const x = parseFloat(((e.clientX - wrapperRect.left) / wrapperRect.width * 100).toFixed(2));
  const y = parseFloat(((e.clientY - wrapperRect.top) / wrapperRect.height * 100).toFixed(2));
  if (!isFinite(x) || !isFinite(y)) return;

  // Snap to grid
  const snappedX = snapToGrid(x);
  const snappedY = snapToGrid(y);

  pendingCoords = { x: snappedX, y: snappedY };

  if (currentTool === 'add-switch') {
    openAddModal();
  } else if (currentTool === 'add-block') {
    openBlockModal();
  }
});

// ── Planning mode toggle ─────────────────────────────────────────────────────
// Removed: always in planning mode

// ── Grid snapping ─────────────────────────────────────────────────────────────
function snapToGrid(value) {
  return Math.round(value / GRID_SNAP) * GRID_SNAP;
}

function updatePositionDisplay(x, y) {
  const snappedX = snapToGrid(x).toFixed(2);
  const snappedY = snapToGrid(y).toFixed(2);
  posX.textContent = snappedX;
  posY.textContent = snappedY;
}

// Cursor follow in add mode
wrapper.addEventListener('mousemove', (e) => {
  const rect = wrapper.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  // Update cursor position
  addCursor.style.left = (e.clientX - rect.left) + 'px';
  addCursor.style.top  = (e.clientY - rect.top)  + 'px';

  // Update position display
  const x = ((e.clientX - rect.left) / rect.width * 100);
  const y = ((e.clientY - rect.top) / rect.height * 100);
  if (isFinite(x) && isFinite(y)) {
    updatePositionDisplay(x, y);
  }
});

// Click on canvas background → deselect
wrapper.addEventListener('mousedown', (e) => {
  if (e.target === wrapper || e.target === floorplanImg) deselectAll();
});

// ── Add Modal ────────────────────────────────────────────────────────────────
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
    // Default to netbox tab if devices available, else manual
    const unplaced = switches.filter(s => !s.placed && s.source !== 'manual');
    setModalTab(unplaced.length > 0 ? 'netbox' : 'manual');
  } else {
    modalTabs.classList.add('hidden');
    setModalTab('manual');
  }

  // Set default name for manual tab
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
    !s.placed &&
    s.source !== 'manual' &&
    s.name.toLowerCase().includes(filter.toLowerCase())
  );
  if (unplaced.length === 0) {
    deviceList.innerHTML = `<div class="device-empty">No unplaced devices${filter ? ' matching filter' : ''}</div>`;
    return;
  }
  deviceList.innerHTML = '';
  for (const dev of unplaced) {
    const item = document.createElement('div');
    const isSelected = selectedDeviceIds.has(dev.id);
    item.className = 'device-item' + (isMultiselectMode ? ' multiselect-mode' : '') + (dev.id === pendingPickerDeviceId || isSelected ? ' selected' : '');
    item.dataset.id = dev.id;

    if (isMultiselectMode) {
      item.innerHTML = `
        <span class="device-item-checkbox ${isSelected ? 'checked' : ''}"></span>
        <span class="device-item-name">${escHtml(dev.name)}</span>
        <span class="device-item-badge">${escHtml(dev.netbox_status || '')}</span>
      `;
    } else {
      item.innerHTML = `
        <span class="device-item-name">${escHtml(dev.name)}</span>
        <span class="device-item-badge">${escHtml(dev.netbox_status || '')}</span>
      `;
    }
    item.addEventListener('click', () => {
      if (isMultiselectMode) {
        if (selectedDeviceIds.has(dev.id)) {
          selectedDeviceIds.delete(dev.id);
        } else {
          selectedDeviceIds.add(dev.id);
        }
        updateMultiselectCount();
        renderDevicePicker(filter);
      } else {
        pendingPickerDeviceId = dev.id;
        for (const el of deviceList.querySelectorAll('.device-item'))
          el.classList.toggle('selected', el.dataset.id === dev.id);
      }
    });
    deviceList.appendChild(item);
  }
}

function updateMultiselectCount() {
  const count = selectedDeviceIds.size;
  if (count > 0) {
    multiselectCount.textContent = `${count} selected`;
    multiselectCount.style.display = 'block';
  } else {
    multiselectCount.style.display = 'none';
  }
}

deviceFilter.addEventListener('input', () => renderDevicePicker(deviceFilter.value));
deviceFilter.addEventListener('keydown', (e) => {
  if (e.key === 'Enter')  modalConfirm.click();
  if (e.key === 'Escape') closeAddModal();
});

multiselectToggle.addEventListener('change', () => {
  isMultiselectMode = multiselectToggle.checked;
  if (isMultiselectMode) {
    // Convert single selection to multiselect
    if (pendingPickerDeviceId) {
      selectedDeviceIds.add(pendingPickerDeviceId);
      pendingPickerDeviceId = null;
    }
  } else {
    // Clear multiselect when turning off
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

  if (activeModalTab === 'netbox' && config.netbox_enabled) {
    if (isMultiselectMode) {
      // Place multiple devices in a grid pattern
      if (selectedDeviceIds.size === 0) { deviceFilter.focus(); return; }
      const ids = Array.from(selectedDeviceIds);
      const baseX = pendingCoords.x;
      const baseY = pendingCoords.y;

      // Calculate grid dimensions
      const cols = Math.ceil(Math.sqrt(ids.length));
      const spacing = 8; // percentage spacing

      for (let i = 0; i < ids.length; i++) {
        const row = Math.floor(i / cols);
        const col = i % cols;
        const offsetX = (col - (cols - 1) / 2) * spacing;
        const offsetY = (row - (Math.ceil(ids.length / cols) - 1) / 2) * spacing;

        const newX = Math.max(0, Math.min(100, baseX + offsetX));
        const newY = Math.max(0, Math.min(100, baseY + offsetY));

        await placeNetboxDevice(ids[i], newX, newY);
      }
      closeAddModal();
      setTool('select');
    } else {
      if (!pendingPickerDeviceId) { deviceFilter.focus(); return; }
      await placeNetboxDevice(pendingPickerDeviceId, pendingCoords.x, pendingCoords.y);
      closeAddModal();
      setTool('select');
    }
  } else {
    const name = switchNameInput.value.trim();
    if (!name) { switchNameInput.focus(); return; }
    const sw = await api('POST', '/api/switches', { name, ...pendingCoords });
    switches.push(sw);
    renderAll();
    closeAddModal();
    setTool('select');
    selectSwitch(sw.id);
  }
});

async function placeNetboxDevice(id, x, y) {
  try {
    const sw = await api('PUT', `/api/switches/${id}`, { x, y });
    const idx = switches.findIndex(s => s.id === id);
    if (idx >= 0) switches[idx] = { ...switches[idx], ...sw };
    renderAll();
    // Only select if this is a single placement or the last one in multiselect
    if (!isMultiselectMode || !selectedDeviceIds.has(id)) {
      selectSwitch(id);
    }
  } catch (e) {
    alert('Failed to place device: ' + e.message);
  }
}

// ── Seat Block Modal ───────────────────────────────────────────────────────────
const blockBackdrop    = document.getElementById('block-backdrop');
const blockName        = document.getElementById('block-name');
const blockCols        = document.getElementById('block-cols');
const blockRows        = document.getElementById('block-rows');
const blockSpacingX    = document.getElementById('block-spacing-x');
const blockSpacingY    = document.getElementById('block-spacing-y');
const blockRotation    = document.getElementById('block-rotation');
const blockReverseNumbersModal = document.getElementById('block-reverse-numbers-modal');
const blockCancel      = document.getElementById('block-cancel');
const blockConfirm     = document.getElementById('block-confirm');

function openBlockModal() {
  blockName.value = '';
  blockCols.value = '8';
  blockRows.value = '1';
  blockSpacingX.value = '0.5';
  blockSpacingY.value = '1';
  blockRotation.value = '0';
  blockReverseNumbersModal.checked = false;
  blockBackdrop.classList.remove('hidden');
  blockName.focus();
}

function closeBlockModal() {
  blockBackdrop.classList.add('hidden');
  pendingCoords = null;
}

blockCancel.addEventListener('click', closeBlockModal);
blockBackdrop.addEventListener('click', (e) => { if (e.target === blockBackdrop) closeBlockModal(); });
blockConfirm.addEventListener('click', async () => {
  if (!pendingCoords) return;

  const block = await api('POST', '/api/seat-blocks', {
    name: blockName.value.trim(),
    cols: parseInt(blockCols.value) || 1,
    rows: parseInt(blockRows.value) || 1,
    seat_width: 1.5,
    seat_height: 1.5,
    spacing_x: parseFloat(blockSpacingX.value) || 0.5,
    spacing_y: parseFloat(blockSpacingY.value) || 1,
    numbering_pattern: 'blockname_number',
    reverse_numbers: blockReverseNumbersModal.checked,
    rotation: parseInt(blockRotation.value) || 0,
    ...pendingCoords,
  });
  seatBlocks.push(block);
  renderAll();
  closeBlockModal();
  setTool('select');
  selectBlock(block.id);
});

// ── Rendering ────────────────────────────────────────────────────────────────
function renderAll() {
  renderOverlay();
  renderSeats();
  renderBlocks();
  renderSidebar();
  updateHeroStats();
  if (heatmapVisible) renderHeatmap();
  // Seat heatmap is rendered inside renderBlocks() with delay for DOM settling
}

function renderOverlay() {
  overlay.innerHTML = '';
  for (const sw of switches) {
    if (sw.placed !== false) overlay.appendChild(createMarker(sw));
  }
}

function renderSeats() {
  seatsOverlay.innerHTML = '';
  for (const seat of seats) {
    seatsOverlay.appendChild(createSeatMarker(seat));
  }
}

function renderBlocks() {
  blocksOverlay.innerHTML = '';
  for (const block of seatBlocks) {
    blocksOverlay.appendChild(createBlockMarker(block));
  }
}

function renderSidebar() {
  const placed = switches.filter(s => s.placed !== false);

  switchCount.textContent = placed.length;

  // Apply search filter
  const searchTerm = switchSearch.value.trim().toLowerCase();
  const filtered = placed.filter(s =>
    s.name.toLowerCase().includes(searchTerm)
  );

  if (filtered.length === 0) {
    if (placed.length === 0) {
      switchList.innerHTML = '<p class="empty-hint">No switches placed yet.</p>';
    } else {
      switchList.innerHTML = '<p class="empty-hint">No switches match your search.</p>';
    }
  } else {
    switchList.innerHTML = '';
    for (const sw of filtered) {
      const item = document.createElement('div');
      item.className = 'switch-item' + (sw.id === selectedId ? ' active' : '');
      item.dataset.id = sw.id;

      // Get traffic stats for display
      const stats = portStats[sw.id];
      let trafficText = sw.status;
      if (stats && stats.total_traffic_bps != null) {
        const rate = fmtBps(stats.total_traffic_bps);
        trafficText = sw.status + ' · ' + rate;
      }
      if (stats && stats.temperature != null) {
        trafficText += ' · ' + stats.temperature + '°C';
      }

      item.innerHTML = `
        <span class="switch-item-dot status-${sw.status}" style="background:currentColor"></span>
        <span class="switch-item-name">${escHtml(sw.name)}</span>
        <span class="switch-item-status">${trafficText}</span>
      `;
      item.addEventListener('click', () => selectSwitch(sw.id));
      switchList.appendChild(item);
    }
  }
}

function createMarker(sw) {
  const el = document.createElement('div');
  const isSelected = sw.id === selectedId;
  el.className = 'switch-marker' + (isSelected ? ' selected' : '');
  el.dataset.id = sw.id;
  el.style.left = sw.x + '%';
  el.style.top  = sw.y + '%';
  const hideLabel = getDeviceSetting(sw.id, 'hideLabel');
  // Show label when selected or on hover
  el.innerHTML = `
    <div class="switch-pin status-${sw.status}">${pinSVG()}</div>
    ${hideLabel ? '' : `<div class="switch-label" style="opacity:${isSelected ? '1' : '0'}; transition: opacity 0.2s">${escHtml(sw.name)}</div>`}
  `;
  el.addEventListener('mousedown', onMarkerMouseDown);
  el.addEventListener('contextmenu', onMarkerContextMenu);

  // Show label on hover (unless already shown due to selection)
  el.addEventListener('mouseenter', () => {
    if (!isSelected) {
      const label = el.querySelector('.switch-label');
      if (label) label.style.opacity = '1';
    }
  });
  el.addEventListener('mouseleave', () => {
    if (!isSelected) {
      const label = el.querySelector('.switch-label');
      if (label) label.style.opacity = '0';
    }
  });

  return el;
}

function createSeatMarker(seat) {
  const el = document.createElement('div');
  const isSelected = selectedId === seat.id && selectedType === 'seat';
  el.className = 'seat-marker' + (isSelected ? ' selected' : '');
  el.dataset.id = seat.id;
  el.dataset.type = 'seat';
  // Add data-seat-number attribute for heatmap rendering
  if (seat.number) {
    el.dataset.seatNumber = seat.number;
  }
  el.style.left = seat.x + '%';
  el.style.top = seat.y + '%';
  el.style.transform = `translate(-50%, -50%) rotate(${seat.rotation || 0}deg)`;

  const typeChar = {
    chair: '☐',
    desk: '▭',
    booth: '▢',
    vip: '★'
  }[seat.type] || '☐';

  el.innerHTML = `
    <div class="seat-icon seat-status-${seat.status}">
      ${typeChar}
    </div>
    ${seat.number ? `<div class="seat-number">${escHtml(seat.number)}</div>` : ''}
  `;
  el.addEventListener('mousedown', onSeatMouseDown);
  el.addEventListener('contextmenu', onSeatContextMenu);

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
  el.style.transform = `translate(-50%, -50%) rotate(${block.rotation || 0}deg)`;

  // Calculate total height
  const totalHeight = block.rows * block.seat_height + (block.rows - 1) * block.spacing_y;

  let html = '';
  if (block.name) {
    html += `<div class="seat-block-label">${escHtml(block.name)}</div>`;
  }

  // Generate seat numbers using "Block Name-Number" scheme with rotation support
  let seatNum = 1;
  const totalSeats = block.cols * block.rows;
  // Use block name as prefix (format: "A-1", "B-2", etc.)
  const blockPrefix = block.name ? block.name.toUpperCase() + '-' : '';

  // Calculate rotation offset (90°, 180°, 270° rotations change numbering direction)
  const rotation = (block.rotation || 0) % 360;
  let seatNumbers = [];
  for (let i = 0; i < totalSeats; i++) {
    seatNumbers.push(seatNum++);
  }

  // Apply rotation offset - different rotation directions change number order
  let rotatedNumbers = [];
  if (rotation >= 0 && rotation < 90) {
    // 0°: left to right, top to bottom (normal order)
    rotatedNumbers = [...seatNumbers];
  } else if (rotation >= 90 && rotation < 180) {
    // 90°: top to bottom, right to left (reverse columns)
    for (let row = 0; row < block.rows; row++) {
      const rowStart = row * block.cols;
      const rowEnd = rowStart + block.cols;
      const rowNumbers = seatNumbers.slice(rowStart, rowEnd).reverse();
      rotatedNumbers.push(...rowNumbers);
    }
  } else if (rotation >= 180 && rotation < 270) {
    // 180°: right to left, bottom to top (reverse all)
    rotatedNumbers = [...seatNumbers].reverse();
  } else {
    // 270°: bottom to top, left to right (reverse rows)
    for (let row = block.rows - 1; row >= 0; row--) {
      const rowStart = row * block.cols;
      const rowEnd = rowStart + block.cols;
      const rowNumbers = seatNumbers.slice(rowStart, rowEnd);
      rotatedNumbers.push(...rowNumbers);
    }
  }

  // Handle reverse numbers after rotation
  if (block.reverse_numbers) {
    rotatedNumbers.reverse();
  }

  let numIndex = 0;
  for (let row = 0; row < block.rows; row++) {
    html += '<div class="seat-block-row">';
    for (let col = 0; col < block.cols; col++) {
      const number = `${blockPrefix}${rotatedNumbers[numIndex]}`;
      const displayNum = rotatedNumbers[numIndex];
      const counterRotation = rotation ? `transform: rotate(${-rotation}deg);` : '';

      html += `<div class="seat-block-seat status-available" style="${counterRotation}" data-seat-number="${escHtml(number)}" title="${escHtml(number)}">${escHtml(displayNum)}</div>`;
      numIndex++;
    }
    html += '</div>';
  }

  el.innerHTML = html;
  el.style.height = totalHeight + '%';
  el.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;

  el.addEventListener('mousedown', onBlockMouseDown);
  el.addEventListener('contextmenu', onBlockContextMenu);

  return el;
}

// ── Selection & detail panel ──────────────────────────────────────────────────
function selectSwitch(id) {
  selectedId = id;

  // Update marker selection state and label visibility
  for (const m of overlay.querySelectorAll('.switch-marker')) {
    const isSelected = m.dataset.id === id;
    m.classList.toggle('selected', isSelected);
    // Show/hide label based on selection
    const label = m.querySelector('.switch-label');
    if (label && !getDeviceSetting(m.dataset.id, 'hideLabel')) {
      label.style.opacity = isSelected ? '1' : '0';
    }
  }

  for (const item of switchList.querySelectorAll('.switch-item'))
    item.classList.toggle('active', item.dataset.id === id);

  if (!id) { detailPanel.classList.add('hidden'); return; }

  const sw = switches.find(s => s.id === id);
  if (!sw) { detailPanel.classList.add('hidden'); return; }

  // Populate
  detailName.textContent = sw.name;
  detailStatusBadge.textContent = sw.status;
  detailStatusBadge.className = `detail-status-badge status-${sw.status}`;

  ddSource.textContent   = sw.source === 'manual' ? 'Manual' : 'NetBox';
  ddPosition.textContent = sw.x != null ? `${sw.x.toFixed(1)}% / ${sw.y.toFixed(1)}%` : '—';

  if (sw.netbox_status !== undefined) {
    dtNetboxStatus.classList.remove('hidden');
    ddNetboxStatus.classList.remove('hidden');
    ddNetboxStatus.textContent = sw.netbox_status;
  } else {
    dtNetboxStatus.classList.add('hidden');
    ddNetboxStatus.classList.add('hidden');
  }

  detailLibrenms.style.display = config.librenms_enabled ? '' : 'none';

  // Check if we have cached stats, otherwise show loading state
  const cachedStats = portStats[id];
  if (cachedStats) {
    populateLnmsFields({ hostname: sw.name, status: sw.status, ...cachedStats });
  } else {
    populateLnmsFields({ hostname: sw.name, status: sw.status });
  }

  // Fetch fresh status data immediately
  if (config.librenms_enabled) {
    fetchSwitchStatus(id);
  }

  // Device settings
  settingExcludeHeatmap.checked = getDeviceSetting(id, 'excludeHeatmap');
  settingHideLabel.checked      = getDeviceSetting(id, 'hideLabel');

  detailPanel.classList.remove('hidden');
}

async function fetchSwitchStatus(id) {
  try {
    const data = await api('GET', `/api/switches/${id}/status`);
    const sw = switches.find(s => s.id === id);
    if (sw) sw.status = data.status;
    if (data.up_ports != null) {
      portStats[id] = {
        up_ports:          data.up_ports,
        total_ports:       data.total_ports,
        traffic_util:      data.traffic_util      ?? null,
        total_traffic_bps: data.total_traffic_bps ?? null,
        temperature:       data.temperature       ?? null,
      };
    }
    // Update detail panel if this switch is still selected
    if (selectedId === id) {
      detailStatusBadge.textContent = data.status;
      detailStatusBadge.className = `detail-status-badge status-${data.status}`;
      populateLnmsFields(data);
    }
    // Update sidebar items
    renderAll();

    // Save to cache
    saveStatusCache();
  } catch (e) {
    console.error('Failed to fetch switch status:', e);
  }
}

function deselectSwitch() { selectSwitch(null); }

function selectSeat(id) {
  deselectAll();
  selectedId = id;
  selectedType = 'seat';

  const seat = seats.find(s => s.id === id);
  if (!seat) return;

  const marker = seatsOverlay.querySelector(`[data-id="${id}"]`);
  if (marker) marker.classList.add('selected');

  // For individual seats, we could show a detail panel similar to switches
  // For now, we'll just highlight the marker
}
function deselectAll() {
  selectedId = null;
  selectedType = null;
  currentBlockSeatNumber = null;
  currentBlockSeatResolution = null;
  // Update switch markers
  for (const m of overlay.querySelectorAll('.switch-marker')) {
    m.classList.remove('selected');
    const label = m.querySelector('.switch-label');
    if (label && !getDeviceSetting(m.dataset.id, 'hideLabel')) {
      label.style.opacity = '0';
    }
  }
  for (const item of switchList.querySelectorAll('.switch-item'))
    item.classList.remove('active');

  // Hide detail panels
  detailPanel.classList.add('hidden');
  blockDetailPanel.classList.add('hidden');
  blockSeatDetailPanel.classList.add('hidden');

  // Update block markers
  for (const m of blocksOverlay.querySelectorAll('.seat-block'))
    m.classList.remove('selected');

  detailPanel.classList.add('hidden');
  blockDetailPanel.classList.add('hidden');
}

// ── Block seat detail panel ─────────────────────────────────────────────────────
let currentBlockSeatNumber = null;
let currentBlockSeatResolution = null;

async function showBlockSeatDetail(seatNumber) {
  deselectAll();
  currentBlockSeatNumber = seatNumber;
  currentBlockSeatResolution = null;

  const seatData = seatMappings[seatNumber];
  if (!seatData) {
    blockSeatDetailNumber.textContent = seatNumber;
    blockSeatDdUsername.textContent = '—';
    blockSeatDdPosition.textContent = '—';
    blockSeatDdIp.textContent = '—';
    blockSeatDdMac.textContent = '—';
    blockSeatDdSwitch.textContent = '—';
    blockSeatDdPort.textContent = '—';
    blockSeatDdVlan.textContent = '—';
    blockSeatResolutionStatus.textContent = 'No seat mapping found in seats.json';
    blockSeatResolutionStatus.style.color = 'var(--warning)';
    blockSeatDetailPanel.classList.remove('hidden');
    return;
  }

  blockSeatDetailNumber.textContent = seatNumber;
  blockSeatDdUsername.textContent = seatData.username || '—';
  blockSeatDdIp.textContent = seatData.ip_address || '—';
  blockSeatDdPosition.textContent = seatNumber;
  blockSeatDdMac.textContent = '—';
  blockSeatDdSwitch.textContent = '—';
  blockSeatDdPort.textContent = '—';
  blockSeatDdVlan.textContent = '—';
  blockSeatDdPortStatus.textContent = '—';
  blockSeatDdTotalTraffic.textContent = '—';
  blockSeatDdDownload.textContent = '—';
  blockSeatDdUpload.textContent = '—';
  blockSeatDdPortSpeed.textContent = '—';
  blockSeatResolutionStatus.textContent = 'Resolving...';
  blockSeatResolutionStatus.style.color = 'var(--text-tertiary)';

  blockSeatDetailPanel.classList.remove('hidden');

  // Resolve IP to get MAC, switch, and port info
  if (seatData.ip_address) {
    try {
      const result = await api('GET', `/api/resolve/${seatData.ip_address}`);
      currentBlockSeatResolution = result;
      blockSeatDdMac.textContent = result.mac || '—';
      blockSeatDdSwitch.textContent = result.device_name || result.hostname || '—';
      blockSeatDdPort.textContent = result.port || '—';
      blockSeatDdVlan.textContent = result.vlan || '—';

      // Populate port usage statistics
      if (result.stats) {
        const stats = result.stats;
        blockSeatDdPortStatus.textContent = stats.ifOperStatus || '—';
        blockSeatDdPortStatus.style.color = stats.ifOperStatus === 'up' ? 'var(--success)' : 'var(--danger)';

        const inRate = (parseFloat(stats.ifInOctets_rate) || 0) * 8;
        const outRate = (parseFloat(stats.ifOutOctets_rate) || 0) * 8;
        const totalBps = inRate + outRate;
        const speedBps = parseFloat(stats.ifSpeed) || 0;

        blockSeatDdTotalTraffic.textContent = fmtBps(totalBps);
        blockSeatDdDownload.textContent = fmtBps(inRate);
        blockSeatDdUpload.textContent = fmtBps(outRate);
        blockSeatDdPortSpeed.textContent = fmtBps(speedBps);
      }

      blockSeatResolutionStatus.textContent = `Resolved via ${result.arp_source || 'LibreNMS ARP table'}`;
      blockSeatResolutionStatus.style.color = 'var(--success)';

      // Update seat heatmap with this resolved data
      if (seatHeatmapVisible) {
        seatHeatmapData.seats = seatHeatmapData.seats || {};
        seatHeatmapData.seats[seatNumber] = {
          'username': seatData.username,
          'ip_address': seatData.ip_address,
          'resolved': true,
          'port_usage': result.stats ? {
            'total_bps': ((parseFloat(result.stats.ifInOctets_rate) || 0) + (parseFloat(result.stats.ifOutOctets_rate) || 0)) * 8,
            'in_rate_bps': (parseFloat(result.stats.ifInOctets_rate) || 0) * 8,
            'out_rate_bps': (parseFloat(result.stats.ifOutOctets_rate) || 0) * 8,
            'status': result.stats.ifOperStatus,
            'speed_bps': parseFloat(result.stats.ifSpeed) || 0,
          } : null,
          'device_name': result.device_name,
          'port': result.port,
          'vlan': result.vlan,
          'mac': result.mac,
        };
        renderSeatHeatmap();
      }
    } catch (e) {
      blockSeatDdMac.textContent = '—';
      blockSeatDdSwitch.textContent = '—';
      blockSeatDdPort.textContent = '—';
      blockSeatDdVlan.textContent = '—';
      blockSeatDdPortStatus.textContent = '—';
      blockSeatDdTotalTraffic.textContent = '—';
      blockSeatDdDownload.textContent = '—';
      blockSeatDdUpload.textContent = '—';
      blockSeatDdPortSpeed.textContent = '—';
      blockSeatResolutionStatus.textContent = `Failed to resolve: ${e.message}`;
      blockSeatResolutionStatus.style.color = 'var(--danger)';

      // Update seat heatmap with unresolved state
      if (seatHeatmapVisible) {
        seatHeatmapData.seats = seatHeatmapData.seats || {};
        seatHeatmapData.seats[seatNumber] = {
          'username': seatData.username,
          'ip_address': seatData.ip_address,
          'resolved': false,
          'port_usage': null,
          'error': e.message || 'Could not resolve',
        };
        renderSeatHeatmap();
      }
    }
  } else {
    blockSeatResolutionStatus.textContent = 'No IP address configured';
    blockSeatResolutionStatus.style.color = 'var(--warning)';
  }
}

function selectBlock(id) {
  deselectAll();
  selectedId = id;
  selectedType = 'block';

  for (const m of blocksOverlay.querySelectorAll('.seat-block')) {
    m.classList.toggle('selected', m.dataset.id === id);
  }

  if (!id) { blockDetailPanel.classList.add('hidden'); return; }

  const block = seatBlocks.find(b => b.id === id);
  if (!block) { blockDetailPanel.classList.add('hidden'); return; }

  blockDetailName.textContent = block.name || 'Unnamed Block';
  blockDdName.textContent = block.name || '—';
  blockDdPosition.textContent = `${block.x.toFixed(1)}% / ${block.y.toFixed(1)}%`;
  blockDdSize.textContent = `${block.cols}×${block.rows}`;
  blockDdRotation.textContent = `${block.rotation || 0}°`;

  blockEditName.value = block.name || '';
  blockEditRotation.value = block.rotation || 0;
  blockReverseNumbers.checked = block.reverse_numbers || false;

  blockDetailPanel.classList.remove('hidden');
}

function setBar(barEl, valueEl, pct) {
  const p = pct != null ? Math.min(100, Math.max(0, pct)) : null;
  if (p == null) {
    barEl.style.width = '0%';
    barEl.className   = 'resource-bar';
    valueEl.textContent = '—';
    return;
  }
  barEl.style.width   = p + '%';
  barEl.className     = 'resource-bar' + (p >= 90 ? ' crit' : p >= 70 ? ' warn' : '');
  valueEl.textContent = p + '%';
}

function fmtBps(bps) {
  if (bps == null) return null;
  if (bps >= 1e9)  return (bps / 1e9).toFixed(1) + ' Gbps';
  if (bps >= 1e6)  return (bps / 1e6).toFixed(1) + ' Mbps';
  if (bps >= 1e3)  return (bps / 1e3).toFixed(1) + ' Kbps';
  return bps + ' bps';
}

function populateLnmsFields(data) {
  ddHostname.textContent   = data.hostname  || '—';
  ddLnmsStatus.textContent = data.status    || '—';
  ddIp.textContent         = data.ip        || '—';

  let portsText = '—';
  if (data.up_ports != null) {
    portsText = `${data.up_ports} / ${data.total_ports ?? '?'}`;
    const rate = fmtBps(data.total_traffic_bps);
    if (rate) {
      portsText += ` · ${rate}`;
    }
  }
  ddPorts.textContent = portsText;

  ddTemperature.textContent = data.temperature != null ? `${data.temperature}°C` : '—';

  setBar(barCpu, ddCpu, data.cpu_load    != null ? data.cpu_load    : null);
  setBar(barMem, ddMem, data.mem_percent != null ? data.mem_percent : null);
}

// Detail panel wiring
detailClose.addEventListener('click', deselectSwitch);

settingExcludeHeatmap.addEventListener('change', () => {
  if (!selectedId) return;
  setDeviceSetting(selectedId, 'excludeHeatmap', settingExcludeHeatmap.checked);
  if (heatmapVisible) renderHeatmap();
});

settingHideLabel.addEventListener('change', () => {
  if (!selectedId) return;
  setDeviceSetting(selectedId, 'hideLabel', settingHideLabel.checked);
  renderOverlay();
});

detailBtnRename.addEventListener('click', () => {
  if (selectedId) { contextId = selectedId; openRenameModal(selectedId); }
});

detailBtnDelete.addEventListener('click', async () => {
  if (selectedId) await doDelete(selectedId);
});

detailBtnRefresh.addEventListener('click', async () => {
  if (!selectedId) return;
  detailBtnRefresh.disabled = true;
  try {
    const data = await api('GET', `/api/switches/${selectedId}/status`);
    const sw = switches.find(s => s.id === selectedId);
    if (sw) sw.status = data.status;
    if (data.up_ports != null) {
      portStats[selectedId] = {
        up_ports:          data.up_ports,
        total_ports:       data.total_ports,
        traffic_util:      data.traffic_util      ?? null,
        total_traffic_bps: data.total_traffic_bps ?? null,
        temperature:       data.temperature       ?? null,
      };
    }
    detailStatusBadge.textContent = data.status;
    detailStatusBadge.className   = `detail-status-badge status-${data.status}`;
    populateLnmsFields(data);
    renderAll();
  } finally {
    detailBtnRefresh.disabled = false;
  }
});

// ── Drag ─────────────────────────────────────────────────────────────────────
function onMarkerMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();

  const marker = e.currentTarget;
  const id = marker.dataset.id;
  const sw = switches.find(s => s.id === id);
  if (!sw) return;

  selectSwitch(id);

  dragState = {
    id,
    type: 'switch',
    startX: e.clientX,
    startY: e.clientY,
    origX:  sw.x,
    origY:  sw.y,
    wrapperRect: wrapper.getBoundingClientRect(),
    moved: false,
  };
  marker.classList.add('dragging');
  document.addEventListener('mousemove', onDocMouseMove);
  document.addEventListener('mouseup',   onDocMouseUp);
}

function onDocMouseMove(e) {
  if (!dragState) return;
  const { id, type, startX, startY, origX, origY, wrapperRect } = dragState;
  const dx = e.clientX - startX;
  const dy = e.clientY - startY;
  if (!dragState.moved && Math.hypot(dx, dy) < 3) return;
  dragState.moved = true;

  // Always use wrapperRect for coordinate calculation
  const rect = wrapperRect || wrapper.getBoundingClientRect();
  const newX = Math.min(100, Math.max(0, snapToGrid(origX + (dx / rect.width * 100))));
  const newY = Math.min(100, Math.max(0, snapToGrid(origY + (dy / rect.height * 100))));

  if (type === 'seat') {
    const marker = seatsOverlay.querySelector(`[data-id="${id}"]`);
    if (marker) { marker.style.left = newX + '%'; marker.style.top = newY + '%'; }
    const seat = seats.find(s => s.id === id);
    if (seat) { seat.x = newX; seat.y = newY; }
  } else if (type === 'block') {
    const marker = blocksOverlay.querySelector(`[data-id="${id}"]`);
    if (marker) { marker.style.left = newX + '%'; marker.style.top = newY + '%'; }
    const block = seatBlocks.find(b => b.id === id);
    if (block) { block.x = newX; block.y = newY; }
  } else {
    // Switch handling
    const marker = overlay.querySelector(`[data-id="${id}"]`);
    if (marker) { marker.style.left = newX + '%'; marker.style.top = newY + '%'; }
    const sw = switches.find(s => s.id === id);
    if (sw) { sw.x = newX; sw.y = newY; }
  }

  // Update position display during drag
  updatePositionDisplay(newX, newY);

  if (heatmapVisible) renderHeatmap();
}

async function onDocMouseUp() {
  if (!dragState) return;
  document.removeEventListener('mousemove', onDocMouseMove);
  document.removeEventListener('mouseup', onDocMouseUp);

  const { id, type, moved } = dragState;

  if (type === 'seat') {
    const marker = seatsOverlay.querySelector(`[data-id="${id}"]`);
    if (marker) marker.classList.remove('dragging');
    if (moved) {
      const seat = seats.find(s => s.id === id);
      if (seat) await api('PUT', `/api/seats/${id}`, { x: seat.x, y: seat.y }).catch(console.error);
    }
  } else if (type === 'block') {
    const marker = blocksOverlay.querySelector(`[data-id="${id}"]`);
    if (marker) marker.classList.remove('dragging');
    if (moved) {
      const block = seatBlocks.find(b => b.id === id);
      if (block) await api('PUT', `/api/seat-blocks/${id}`, { x: block.x, y: block.y }).catch(console.error);
    }
  } else {
    // Switch handling (original behavior)
    const marker = overlay.querySelector(`[data-id="${id}"]`);
    if (marker) marker.classList.remove('dragging');
    if (moved) {
      const sw = switches.find(s => s.id === id);
      if (sw) await api('PUT', `/api/switches/${id}`, { x: sw.x, y: sw.y }).catch(console.error);
    }
  }
  dragState = null;
}

// ── Seat Drag Handlers ───────────────────────────────────────────────────────
function onSeatMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();

  const marker = e.currentTarget;
  const id = marker.dataset.id;
  const seat = seats.find(s => s.id === id);
  if (!seat) return;

  selectSeat(id);

  const wrapperRect = wrapper.getBoundingClientRect();
  dragState = {
    id,
    type: 'seat',
    startX: e.clientX,
    startY: e.clientY,
    origX: seat.x,
    origY: seat.y,
    wrapperRect: wrapperRect,
    moved: false,
  };
  marker.classList.add('dragging');
  document.addEventListener('mousemove', onDocMouseMove);
  document.addEventListener('mouseup',   onDocMouseUp);
}

function onSeatContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  selectSeat(id);
}

function onBlockMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();

  const marker = e.currentTarget;
  const id = marker.dataset.id;
  const block = seatBlocks.find(b => b.id === id);
  if (!block) return;

  selectBlock(id);

  dragState = {
    id,
    type: 'block',
    startX: e.clientX,
    startY: e.clientY,
    origX: block.x,
    origY: block.y,
    wrapperRect: wrapper.getBoundingClientRect(),
    moved: false,
  };
  marker.classList.add('dragging');
  document.addEventListener('mousemove', onDocMouseMove);
  document.addEventListener('mouseup', onDocMouseUp);
}

function onBlockContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  selectBlock(id);
}


// ── Context menu ─────────────────────────────────────────────────────────────
function onMarkerContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  contextId = e.currentTarget.dataset.id;
  selectSwitch(contextId);
  contextMenu.style.left = e.clientX + 'px';
  contextMenu.style.top  = e.clientY  + 'px';
  contextMenu.classList.remove('hidden');
}

document.addEventListener('click', () => contextMenu.classList.add('hidden'));

ctxRename.addEventListener('click', (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  openRenameModal(contextId);
});

ctxDelete.addEventListener('click', async (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  if (contextId) await doDelete(contextId);
});

// ── Rename Modal ─────────────────────────────────────────────────────────────
function openRenameModal(id) {
  const sw = switches.find(s => s.id === id);
  if (!sw) return;
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
  if (!name || !contextId) { renameInput.focus(); return; }
  const updated = await api('PUT', `/api/switches/${contextId}`, { name });
  const sw = switches.find(s => s.id === contextId);
  if (sw) sw.name = updated.name;
  renderAll();
  renameBackdrop.classList.add('hidden');
});

// ── Seat block detail panel handlers ───────────────────────────────────────
blockDetailClose.addEventListener('click', deselectAll);
blockSeatDetailClose.addEventListener('click', deselectAll);

blockDetailSave.addEventListener('click', async () => {
  if (!selectedId || selectedType !== 'block') return;
  const updated = await api('PUT', `/api/seat-blocks/${selectedId}`, {
    name: blockEditName.value.trim(),
    rotation: parseInt(blockEditRotation.value) || 0,
    reverse_numbers: blockReverseNumbers.checked,
  });
  const block = seatBlocks.find(b => b.id === selectedId);
  if (block) {
    block.name = updated.name;
    block.rotation = updated.rotation;
    block.reverse_numbers = updated.reverse_numbers;
  }
  selectBlock(selectedId);
  renderAll();
});

blockDetailDuplicate.addEventListener('click', async () => {
  if (!selectedId || selectedType !== 'block') return;
  const originalBlock = seatBlocks.find(b => b.id === selectedId);
  if (!originalBlock) return;

  // Calculate new position (offset by 10% to the right)
  const newX = Math.min(90, originalBlock.x + 10);
  const newY = Math.min(90, originalBlock.y + 10);

  // Create duplicate with modified name
  const duplicate = await api('POST', '/api/seat-blocks', {
    name: `${originalBlock.name || 'Block'} (Copy)`,
    cols: originalBlock.cols,
    rows: originalBlock.rows,
    seat_width: originalBlock.seat_width,
    seat_height: originalBlock.seat_height,
    spacing_x: originalBlock.spacing_x,
    spacing_y: originalBlock.spacing_y,
    numbering_pattern: 'blockname_number',
    rotation: originalBlock.rotation,
    x: newX,
    y: newY,
  });
  seatBlocks.push(duplicate);
  renderAll();
  selectBlock(duplicate.id);
});

blockDetailDelete.addEventListener('click', async () => {
  if (!selectedId || selectedType !== 'block') return;
  if (confirm('Delete this seat block?')) {
    await api('DELETE', `/api/seat-blocks/${selectedId}`);
    seatBlocks = seatBlocks.filter(b => b.id !== selectedId);
    deselectAll();
    renderAll();
  }
});

// ── Delete ────────────────────────────────────────────────────────────────────
async function doDelete(id) {
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
  if (selectedId === id) selectedId = null;
  if (contextId  === id) contextId  = null;
  renderAll();
}

document.addEventListener('keydown', async (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
    if (selectedType === 'seat') {
      // Handle seat deletion
      if (confirm('Delete this seat?')) {
        await api('DELETE', `/api/seats/${selectedId}`);
        seats = seats.filter(s => s.id !== selectedId);
        deselectAll();
        renderAll();
      }
    } else if (selectedType === 'block') {
      // Handle seat block deletion
      if (confirm('Delete this seat block?')) {
        await api('DELETE', `/api/seat-blocks/${selectedId}`);
        seatBlocks = seatBlocks.filter(b => b.id !== selectedId);
        deselectAll();
        renderAll();
      }
    } else {
      await doDelete(selectedId);
    }
  }
  if (e.key === 'Escape') { deselectAll(); setTool('select'); }
});

// ── Switch search ─────────────────────────────────────────────────────────────
switchSearch.addEventListener('input', () => renderSidebar());

// ── Refresh status ───────────────────────────────────────────────────────────
async function doRefreshAll() {
  if (isRefreshing) return;
  isRefreshing = true;
  try {
    const placed = switches.filter(s => s.placed !== false);
    await Promise.all(placed.map(async (sw) => {
      const data = await api('GET', `/api/switches/${sw.id}/status`).catch(() => null);
      if (data) {
        sw.status = data.status;
        if (data.up_ports != null) {
          portStats[sw.id] = {
            up_ports:          data.up_ports,
            total_ports:       data.total_ports,
            traffic_util:      data.traffic_util      ?? null,
            total_traffic_bps: data.total_traffic_bps ?? null,
            temperature:       data.temperature       ?? null,
          };
        }
      }
    }));
    renderAll();

    // Save to cache after successful refresh
    saveStatusCache();

    // Also refresh seat heatmap data if visible
    if (seatHeatmapVisible) {
      await fetchSeatHeatmapData();
      renderSeatHeatmap();
    }
  } finally {
    isRefreshing = false;
  }
}

function saveStatusCache() {
  const cacheData = {
    portStats: { ...portStats },
    statuses: {}
  };

  // Store current status for each switch
  for (const sw of switches) {
    if (sw.status) {
      cacheData.statuses[sw.id] = sw.status;
    }
  }

  setCache(cacheData);
}

btnRefreshAll.addEventListener('click', async () => {
  if (isRefreshing) return;
  btnRefreshAll.disabled = true;
  try { await doRefreshAll(); } finally { btnRefreshAll.disabled = false; }
});

// Auto-refresh every 10 seconds
setInterval(() => doRefreshAll().catch(console.error), 10_000);

// ── Zoom ──────────────────────────────────────────────────────────────────────
function applyZoom() {
  wrapper.style.transform = zoom === 1 ? '' : `scale(${zoom})`;
  zoomLevelEl.textContent = Math.round(zoom * 100) + '%';
}

function changeZoom(delta) {
  zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom + delta));
  applyZoom();
}

btnZoomIn.addEventListener('click',    () => changeZoom(+ZOOM_STEP));
btnZoomOut.addEventListener('click',   () => changeZoom(-ZOOM_STEP));
btnZoomReset.addEventListener('click', () => { zoom = 1; applyZoom(); });

// Mouse wheel zoom (Ctrl optional – works either way)
document.getElementById('canvas-area').addEventListener('wheel', (e) => {
  e.preventDefault();
  changeZoom(e.deltaY < 0 ? +ZOOM_STEP : -ZOOM_STEP);
}, { passive: false });

// ── Center map ───────────────────────────────────────────────────────────
btnCenter.addEventListener('click', () => {
  const canvasArea = document.getElementById('canvas-area');
  canvasArea.scrollTo({
    left: (canvasArea.scrollWidth - canvasArea.clientWidth) / 2,
    top:  (canvasArea.scrollHeight - canvasArea.clientHeight) / 2,
    behavior: 'smooth',
  });
});

// ── Hero stats ───────────────────────────────────────────────────────────
function updateHeroStats() {
  const placed  = switches.filter(s => s.placed !== false);
  const online  = placed.filter(s => s.status === 'online').length;
  const offline = placed.filter(s => s.status === 'offline').length;
  heroTotal.textContent   = placed.length;
  heroOnline.textContent  = online;
  heroOffline.textContent = offline;
  heroUnknown.textContent = placed.length - online - offline;
}

// ── Heatmap ──────────────────────────────────────────────────────────────
btnHeatmap.addEventListener('click', () => {
  heatmapVisible = !heatmapVisible;
  btnHeatmap.classList.toggle('heatmap-on', heatmapVisible);
  heatCanvas.style.display = heatmapVisible ? 'block' : 'none';
  heatLegend.classList.toggle('hidden', !heatmapVisible);
  if (heatmapVisible) renderHeatmap();
});

// ── Seat Heatmap ───────────────────────────────────────────────────────
btnSeatHeatmap.addEventListener('click', async () => {
  seatHeatmapVisible = !seatHeatmapVisible;
  btnSeatHeatmap.classList.toggle('heatmap-on', seatHeatmapVisible);
  seatHeatCanvas.style.display = seatHeatmapVisible ? 'block' : 'none';
  seatHeatLegend.classList.toggle('hidden', !seatHeatmapVisible);
  if (seatHeatmapVisible) {
    await fetchSeatHeatmapData();
    renderSeatHeatmap();
  } else {
    // Clear seat heatmap canvas
    const ctx = seatHeatCanvas.getContext('2d');
    ctx.clearRect(0, 0, seatHeatCanvas.width, seatHeatCanvas.height);
  }
});

async function fetchSeatHeatmapData() {
  try {
    const data = await api('GET', '/api/seats/heatmap');
    console.log('Seat heatmap API response status:', data.status ? data.status : 'No status field');
    console.log('Seat heatmap data keys:', Object.keys(data));
    console.log('Seats count:', data.seats ? Object.keys(data.seats).length : 0);
    seatHeatmapData.seats = data.seats || {};
  } catch (e) {
    console.error('Failed to fetch seat heatmap data:', e);
    console.error('Error details:', e.message);
    seatHeatmapData.seats = {};
  }
}

function renderSeatHeatmap() {
  console.log('renderSeatHeatmap called');
  console.log('seatHeatmapData.seats:', seatHeatmapData.seats);

  if (!seatHeatmapData.seats) {
    console.log('No seat heatmap data, returning');
    return;
  }

  // Check if canvas exists and has dimensions
  if (!seatHeatCanvas) {
    console.error('Seat heatmap canvas not found');
    return;
  }

  // Set canvas size to match wrapper
  const cw = seatHeatCanvas.offsetWidth || wrapper.offsetWidth;
  const ch = seatHeatCanvas.offsetHeight || wrapper.offsetHeight;

  console.log('Canvas dimensions:', { cw, ch });

  if (cw === 0 || ch === 0) {
    console.log('Canvas has zero dimensions, returning');
    return;
  }

  seatHeatCanvas.width = cw;
  seatHeatCanvas.height = ch;

  const ctx = seatHeatCanvas.getContext('2d');
  if (!ctx) return;

  ctx.clearRect(0, 0, cw, ch);

  // Count how many seat elements actually exist in the DOM
  const seatElements = document.querySelectorAll('[data-seat-number]');
  console.log(`Found ${seatElements.length} seat elements for heatmap rendering`);
  console.log('Seat elements:', Array.from(seatElements).map(el => ({
    number: el.dataset.seatNumber,
    rect: el.getBoundingClientRect()
  })));

  if (seatElements.length === 0) {
    console.log('No seat elements found, skipping heatmap render');
    return;
  }

  // Convert from visual (screen) pixels → canvas buffer pixels
  const canvasRect = seatHeatCanvas.getBoundingClientRect();
  const scale = canvasRect.width > 0 ? cw / canvasRect.width : 1;

  console.log('Canvas rect:', canvasRect);
  console.log('Scale factor:', scale);

  // Get canvas rect for proper coordinate mapping
  const wrapperRect = wrapper.getBoundingClientRect();
  if (!wrapperRect) return;

  console.log('Wrapper rect:', wrapperRect);
  console.log('Total seats in heatmap data:', Object.keys(seatHeatmapData.seats).length);

  // Draw heat map for each seat
  for (const [seatNumber, seatData] of Object.entries(seatHeatmapData.seats)) {
    const seatEl = document.querySelector(`[data-seat-number="${seatNumber}"]`);
    if (!seatEl) {
      console.log(`Seat element not found for: ${seatNumber}`);
      continue;
    }

    // Get seat position on canvas
    const seatRect = seatEl.getBoundingClientRect();
    const cx = (seatRect.left + seatRect.width / 2 - wrapperRect.left) * scale;
    const cy = (seatRect.top + seatRect.height / 2 - wrapperRect.top) * scale;

    // Determine color based on resolution status and port usage
    let rgb;
    if (!seatData.resolved || !seatData.port_usage) {
      // Unresolved or no port stats - show as gray (unknown)
      rgb = [110, 118, 129]; // Gray - unknown/unresolved
    } else {
      const usage = seatData.port_usage;
      const totalBps = usage.total_bps || 0;
      const status = usage.status;

      // Color based on throughput
      const mbps = totalBps / 1e6;

      if (!status || status !== 'up') {
        rgb = [110, 118, 129]; // Gray - unknown/offline
      } else if (mbps >= 500) {
        rgb = [248, 81, 73]; // Red - high usage (500+ Mbps)
      } else if (mbps >= 100) {
        rgb = [210, 153, 34]; // Orange - medium-high (100-500 Mbps)
      } else if (mbps >= 10) {
        rgb = [63, 185, 80]; // Green - medium (10-100 Mbps)
      } else {
        rgb = [56, 139, 253]; // Blue - low (<10 Mbps)
      }
    }

    // Draw filled circle for seat
    console.log(`Drawing seat ${seatNumber} with color: rgb(${rgb.join(',')})`);
    const radius = Math.min(seatRect.width, seatRect.height) / 2 * scale * 0.9;

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    grad.addColorStop(0,   `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.9)`);
    grad.addColorStop(0.6, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.7)`);
    grad.addColorStop(1,   `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.3)`);

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  console.log('Finished drawing seat heatmap, total circles drawn:', Object.keys(seatHeatmapData.seats).length);
  }

function renderHeatmap() {
  if (!wrapper.offsetWidth) return;

  const cw = heatCanvas.offsetWidth  || wrapper.offsetWidth;
  const ch = heatCanvas.offsetHeight || wrapper.offsetHeight;
  heatCanvas.width  = cw;
  heatCanvas.height = ch;

  const ctx = heatCanvas.getContext('2d');
  ctx.clearRect(0, 0, cw, ch);

  // Convert from visual (screen) pixels → canvas buffer pixels.
  // getBoundingClientRect reflects the zoom transform; dividing by it
  // gives us the ratio between CSS pixels and visual pixels.
  const canvasRect = heatCanvas.getBoundingClientRect();
  const scale = canvasRect.width > 0 ? cw / canvasRect.width : 1;

  const baseR = Math.min(cw, ch) * 0.18;

  // Find maximum throughput for normalizing the color scale
  let maxThroughput = 0;
  for (const sw of switches) {
    if (sw.placed === false || sw.x == null) continue;
    if (getDeviceSetting(sw.id, 'excludeHeatmap')) continue;
    const stats = portStats[sw.id];
    if (stats && stats.total_traffic_bps != null) {
      maxThroughput = Math.max(maxThroughput, stats.total_traffic_bps);
    }
  }

  for (const sw of switches) {
    if (sw.placed === false || sw.x == null) continue;
    if (getDeviceSetting(sw.id, 'excludeHeatmap')) continue;

    // Skip heatmap for offline devices or devices with no data
    if (sw.status === 'offline') continue;

    const stats = portStats[sw.id];
    if (!stats || stats.total_traffic_bps == null) continue;

    // Measure the actual DOM position of the pin so the blob tracks the
    // pin head exactly regardless of label size or zoom level.
    let cx, cy;
    const marker = overlay.querySelector(`[data-id="${sw.id}"]`);
    if (marker) {
      const pin = marker.querySelector('.switch-pin');
      if (pin) {
        const pr = pin.getBoundingClientRect();
        cx = (pr.left + pr.width / 2 - canvasRect.left) * scale;
        // SVG glass circle is at cy=5 out of viewBox height 18 → 5/18 from top
        cy = (pr.top  + pr.height * 5 / 18 - canvasRect.top) * scale;
      }
    }
    if (cx == null) {
      // Fallback: coordinate-based (used during initial render before DOM settles)
      cx = (sw.x / 100) * cw;
      cy = (sw.y / 100) * ch;
    }

    let rgb, r = baseR;

    // Color based on absolute throughput normalized to max
    const throughput = stats.total_traffic_bps;
    const normalized = throughput / maxThroughput;

    // Radius scales with throughput (more traffic = larger circle)
    r = baseR * Math.min(1.8, 0.6 + normalized * 1.2);

    // Color scale: blue (low) → green → orange → red (high throughput)
    // Using absolute throughput thresholds based on typical network speeds
    const gbps = throughput / 1e9;
    if      (gbps >= 10)   rgb = [200,  30,  30];   // 10+ Gbps - red
    else if (gbps >= 5)    rgb = [248,  81,  73];   // 5-10 Gbps - orange-red
    else if (gbps >= 1)    rgb = [210, 153,  34];   // 1-5 Gbps - orange
    else if (gbps >= 0.1)  rgb = [ 63, 185,  80];   // 100 Mbps-1 Gbps - green
    else                    rgb = [ 56, 139, 253];   // <100 Mbps - blue

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0,   `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.95)`);
    grad.addColorStop(0.5, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.7)`);
    grad.addColorStop(0.75,`rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.3)`);
    grad.addColorStop(1,   `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0)`);

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ── Utils ────────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Bootstrap ────────────────────────────────────────────────────────────────
init();
