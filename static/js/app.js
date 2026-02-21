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
let currentTool    = 'select';
let selectedId     = null;
let pendingCoords  = null;
let pendingPickerDeviceId = null;   // selected device in the NetBox picker tab
let selectedDeviceIds = new Set();   // selected device IDs in multiselect mode
let contextId      = null;
let dragState      = null;
let zoom           = 1;
let heatmapVisible = false;
let isRefreshing   = false;
const portStats    = {};             // { switchId: { up_ports, total_ports } }
const deviceSettings = JSON.parse(localStorage.getItem('deviceSettings') || '{}');
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.15;

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
const floorplanUpload  = document.getElementById('floorplan-upload');
const uploadLabel      = document.getElementById('upload-label');
const uploadLabelText  = document.getElementById('upload-label-text');
const floorplanImg     = document.getElementById('floorplan-img');
const emptyState       = document.getElementById('empty-state');
const wrapper          = document.getElementById('floorplan-wrapper');
const overlay          = document.getElementById('switches-overlay');
const switchList       = document.getElementById('switch-list');
const switchSearch     = document.getElementById('switch-search');
const switchCount      = document.getElementById('switch-count');
const addCursor        = document.getElementById('add-cursor');

const toolSelect       = document.getElementById('tool-select');
const toolAdd          = document.getElementById('tool-add');
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
const heatCanvas   = document.getElementById('heatmap-canvas');
const heatLegend   = document.getElementById('heatmap-legend');

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

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  const [cfg] = await Promise.all([
    api('GET', '/api/config'),
    loadFloorplan(),
    loadSwitches(),
  ]);
  config = cfg;
  applyConfig();

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
  if (data.url) applyFloorplan(data.url);
}

async function loadSwitches() {
  switches = await api('GET', '/api/switches');
  renderAll();
}

// ── Floorplan ────────────────────────────────────────────────────────────────
function applyFloorplan(url) {
  floorplanImg.src = url;
  floorplanImg.style.display = 'block';
  emptyState.style.display   = 'none';
  uploadLabel.classList.add('has-file');
  uploadLabelText.textContent = 'Replace Floor Plan';
}

floorplanUpload.addEventListener('change', async () => {
  const file = floorplanUpload.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/floorplan', { method: 'POST', body: form });
    const data = await res.json();
    if (data.url) applyFloorplan(data.url);
    else alert('Upload failed: ' + (data.error || 'Unknown error'));
  } catch (e) {
    alert('Upload error: ' + e.message);
  }
  floorplanUpload.value = '';
});

// ── Tool selection ───────────────────────────────────────────────────────────
function setTool(tool) {
  currentTool = tool;
  toolSelect.classList.toggle('active', tool === 'select');
  toolAdd.classList.toggle('active',    tool === 'add');
  wrapper.classList.toggle('tool-add',  tool === 'add');
  if (tool !== 'select') deselectSwitch();
}

toolSelect.addEventListener('click', () => setTool('select'));
toolAdd.addEventListener('click',    () => setTool('add'));

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

// ── Floor plan click (place switch) ─────────────────────────────────────────
wrapper.addEventListener('click', (e) => {
  if (currentTool !== 'add') return;
  if (e.target.closest('.switch-marker')) return;

  if (!floorplanImg.naturalWidth) {
    alert('Upload a floor plan first.');
    return;
  }

  const imgRect = floorplanImg.getBoundingClientRect();
  if (!imgRect.width || !imgRect.height) return;

  const x = parseFloat(((e.clientX - imgRect.left) / imgRect.width  * 100).toFixed(2));
  const y = parseFloat(((e.clientY - imgRect.top)  / imgRect.height * 100).toFixed(2));
  if (!isFinite(x) || !isFinite(y)) return;

  pendingCoords = { x, y };

  openAddModal();
});

// Cursor follow in add mode
wrapper.addEventListener('mousemove', (e) => {
  if (currentTool !== 'add') return;
  const rect = wrapper.getBoundingClientRect();
  addCursor.style.left = (e.clientX - rect.left) + 'px';
  addCursor.style.top  = (e.clientY - rect.top)  + 'px';
});

// Click on canvas background → deselect
wrapper.addEventListener('mousedown', (e) => {
  if (e.target === wrapper || e.target === floorplanImg) deselectSwitch();
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

// ── Rendering ────────────────────────────────────────────────────────────────
function renderAll() {
  renderOverlay();
  renderSidebar();
  updateHeroStats();
  if (heatmapVisible) renderHeatmap();
}

function renderOverlay() {
  overlay.innerHTML = '';
  for (const sw of switches) {
    if (sw.placed !== false) overlay.appendChild(createMarker(sw));
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
    startX: e.clientX,
    startY: e.clientY,
    origX:  sw.x,
    origY:  sw.y,
    imgRect: floorplanImg.getBoundingClientRect(),
    moved: false,
  };
  marker.classList.add('dragging');
  document.addEventListener('mousemove', onDocMouseMove);
  document.addEventListener('mouseup',   onDocMouseUp);
}

function onDocMouseMove(e) {
  if (!dragState) return;
  const { id, startX, startY, origX, origY, imgRect } = dragState;
  const dx = e.clientX - startX;
  const dy = e.clientY - startY;
  if (!dragState.moved && Math.hypot(dx, dy) < 3) return;
  dragState.moved = true;

  const newX = Math.min(100, Math.max(0, origX + (dx / imgRect.width  * 100)));
  const newY = Math.min(100, Math.max(0, origY + (dy / imgRect.height * 100)));

  const marker = overlay.querySelector(`[data-id="${id}"]`);
  if (marker) { marker.style.left = newX + '%'; marker.style.top = newY + '%'; }

  const sw = switches.find(s => s.id === id);
  if (sw) { sw.x = newX; sw.y = newY; }

  if (heatmapVisible) renderHeatmap();
}

async function onDocMouseUp() {
  if (!dragState) return;
  document.removeEventListener('mousemove', onDocMouseMove);
  document.removeEventListener('mouseup',   onDocMouseUp);

  const { id, moved } = dragState;
  const marker = overlay.querySelector(`[data-id="${id}"]`);
  if (marker) marker.classList.remove('dragging');

  if (moved) {
    const sw = switches.find(s => s.id === id);
    if (sw) await api('PUT', `/api/switches/${id}`, { x: sw.x, y: sw.y }).catch(console.error);
  }
  dragState = null;
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
  if (e.target.tagName === 'INPUT') return;
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) await doDelete(selectedId);
  if (e.key === 'Escape') { deselectSwitch(); setTool('select'); }
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
          };
        }
      }
    }));
    renderAll();

    // Save to cache after successful refresh
    saveStatusCache();
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
  if (!floorplanImg.naturalWidth) return;
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

floorplanImg.addEventListener('load', () => { if (heatmapVisible) renderHeatmap(); });

function renderHeatmap() {
  if (!floorplanImg.offsetWidth) return;

  const cw = heatCanvas.offsetWidth  || floorplanImg.offsetWidth;
  const ch = heatCanvas.offsetHeight || floorplanImg.offsetHeight;
  heatCanvas.width  = cw;
  heatCanvas.height = ch;

  const ctx = heatCanvas.getContext('2d');
  ctx.clearRect(0, 0, cw, ch);

  // Convert from visual (screen) pixels → canvas buffer pixels.
  // getBoundingClientRect reflects the zoom transform; dividing by it
  // gives us the ratio between CSS pixels and visual pixels.
  const canvasRect = heatCanvas.getBoundingClientRect();
  const scale = canvasRect.width > 0 ? cw / canvasRect.width : 1;

  const baseR = Math.min(cw, ch) * 0.12;

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
    grad.addColorStop(0,   `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.55)`);
    grad.addColorStop(0.45,`rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.25)`);
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
