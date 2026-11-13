// Floor plan editor: Selection and the inspector panels (switch, seat, block, multi-selection).
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Selection & inspector ────────────────────────────────────────────────────────────────
function hideInspectors() {
  detailPanel.classList.add('hidden');
  blockDetailPanel.classList.add('hidden');
  blockSeatDetailPanel.classList.add('hidden');
  multiDetailPanel.classList.add('hidden');
}

function markSelection() {
  for (const m of overlay.querySelectorAll('.switch-marker'))
    m.classList.toggle('selected', inSelection('switch', m.dataset.id));
  for (const m of blocksOverlay.querySelectorAll('.seat-block'))
    m.classList.toggle('selected', inSelection('block', m.dataset.id));
  for (const s of blocksOverlay.querySelectorAll('.seat-block-seat'))
    s.classList.toggle('selected', selectedType === 'seat' && s.dataset.seatNumber === currentBlockSeatNumber);
  for (const item of switchList.querySelectorAll('.switch-item'))
    item.classList.toggle('active', inSelection('switch', item.dataset.id));
}

function selectSwitch(id) {
  if (!id) { deselectAll(); return; }
  const sw = switches.find(s => s.id === id);
  if (!sw) { deselectAll(); return; }

  selectedId = id;
  selectedType = 'switch';
  selection.clear();
  selection.add(selKey('switch', id));
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
  selection.clear();
  currentBlockSeatNumber = null;
  currentBlockSeatResolution = null;
  hideInspectors();
  markSelection();
}
// ── Multi-selection ──────────────────────────────────────────────────────────────────
// `selection` holds every selected switch and seat block. With one item the
// normal inspector is shown; with two or more, the selection inspector.
function selKey(type, id) { return `${type}:${id}`; }
function parseSelKey(key) {
  const i = key.indexOf(':');
  return { type: key.slice(0, i), id: key.slice(i + 1) };
}
function inSelection(type, id) { return selection.has(selKey(type, id)); }
function findItem(type, id) {
  if (type === 'block') return seatBlocks.find(b => b.id === id);
  return switches.find(s => s.id === id && s.placed !== false && s.x != null);
}
function itemName(type, item) {
  return type === 'block' ? (item.name || 'Unnamed block') : item.name;
}
function selectedItems() {
  const out = [];
  for (const key of selection) {
    const { type, id } = parseSelKey(key);
    const item = findItem(type, id);
    if (item) out.push({ type, id, item });
  }
  return out;
}
function describeCounts(items) {
  const nSwitches = items.filter(i => i.type === 'switch').length;
  const nBlocks = items.length - nSwitches;
  const parts = [];
  if (nSwitches) parts.push(`${nSwitches} switch${nSwitches === 1 ? '' : 'es'}`);
  if (nBlocks) parts.push(`${nBlocks} seat block${nBlocks === 1 ? '' : 's'}`);
  return parts.join(' and ');
}

function applySelection() {
  for (const key of [...selection]) {
    const { type, id } = parseSelKey(key);
    if (!findItem(type, id)) selection.delete(key);
  }
  if (selection.size === 0) { deselectAll(); return; }
  if (selection.size === 1) {
    const { type, id } = parseSelKey([...selection][0]);
    if (type === 'block') selectBlock(id); else selectSwitch(id);
    return;
  }
  selectedId = null;
  selectedType = 'multi';
  currentBlockSeatNumber = null;
  currentBlockSeatResolution = null;
  hideInspectors();
  fillMultiInspector();
  multiDetailPanel.classList.remove('hidden');
  markSelection();
}

function fillMultiInspector() {
  const items = selectedItems().sort((a, b) =>
    a.type.localeCompare(b.type) || itemName(a.type, a.item).localeCompare(itemName(b.type, b.item)));
  multiDetailName.textContent = `${items.length} items`;
  multiDetailSummary.textContent = describeCounts(items);
  multiList.innerHTML = items.map(({ type, id, item }) => `
    <li><button class="multi-item" data-type="${type}" data-id="${escHtml(id)}">
      ${type === 'switch'
        ? `<span class="switch-item-glyph status-${escHtml(statusBucket(item.status))}">${statusGlyph(item.status)}</span>`
        : '<span class="multi-item-kind" aria-hidden="true">▦</span>'}
      <span class="multi-item-name">${escHtml(itemName(type, item))}</span>
      <span class="multi-item-pos">${Number(item.x).toFixed(1)} / ${Number(item.y).toFixed(1)}</span>
    </button></li>`).join('');
}

function toggleInSelection(type, id) {
  const key = selKey(type, id);
  if (selection.has(key)) selection.delete(key);
  else selection.add(key);
  applySelection();
}

function selectAllItems() {
  selection.clear();
  for (const sw of switches) if (sw.placed !== false && sw.x != null) selection.add(selKey('switch', sw.id));
  for (const b of seatBlocks) selection.add(selKey('block', b.id));
  applySelection();
}

multiList.addEventListener('click', (e) => {
  const btn = e.target.closest('.multi-item');
  if (!btn) return;
  const { type, id } = btn.dataset;
  if (type === 'block') selectBlock(id); else selectSwitch(id);
  focusOnItem(markerFor(type, id));
});
multiDetailClose.addEventListener('click', deselectAll);
multiDetailClear.addEventListener('click', deselectAll);
multiDetailDelete.addEventListener('click', () => actionDeleteSelection());

// Arrow keys move the selection by one grid step (Shift: five steps)
function nudgeSelection(dirX, dirY, big) {
  const items = selectedItems();
  if (!items.length) return;
  const step = (snapEnabled ? GRID_SNAP : 0.1) * (big ? 5 : 1);
  const list = items.map(({ type, id, item }) => ({ type, id, origX: item.x, origY: item.y }));
  offsetItems(list, dirX * step, dirY * step);
  const moves = movesFrom(list);
  if (!moves.length) return;
  refreshSelectionPositions();
  moveQueue = moveQueue.then(() => commitMoves(moves, { label: moveLabel(moves), nudge: true }));
}

function refreshSelectionPositions() {
  if (selectedType === 'multi') { fillMultiInspector(); return; }
  const item = selectedId && findItem(selectedType, selectedId);
  if (!item) return;
  if (selectedType === 'block') fillBlockInspector(item);
  else ddPosition.textContent = `${Number(item.x).toFixed(1)}% / ${Number(item.y).toFixed(1)}%`;
}
// ── Seat inspector ───────────────────────────────────────────────────────────────────
let currentBlockSeatNumber = null;
let currentBlockSeatResolution = null;
const SEAT_PORT_REFRESH = 60_000;   // LibreNMS polls every 5 min, so a minute is plenty
const PORT_STATE_LABEL = { up: 'Up', down: 'Down', disabled: 'Disabled', errors: 'Errors', unknown: 'Unknown' };

function setPortState(state) {
  const s = PORT_STATE_LABEL[state] ? state : 'unknown';
  seatPortState.dataset.state = s;
  seatPortState.textContent = PORT_STATE_LABEL[s];
}

function resetSeatNetworkFields() {
  for (const el of [blockSeatDdMac, blockSeatDdSwitch, blockSeatDdPort, blockSeatDdVlan,
                    blockSeatDdDownload, blockSeatDdUpload, blockSeatDdPortSpeed, seatPortErrors]) {
    el.textContent = '—';
    el.className = '';
  }
  setPortState('unknown');
  setBar(barSeatPort, seatPortLoad, null);
  seatPortDesc.classList.add('hidden');
  seatPortLibrenms.classList.add('hidden');
  seatPortPolled.classList.add('hidden');
  seatPortRefresh.classList.remove('is-busy');
}
function setResolution(text, tone) {
  blockSeatResolutionStatus.textContent = text;
  blockSeatResolutionStatus.style.color = tone ? `var(--${tone})` : '';
}

// "1 Gbps" rather than fmtBps's "1.0 Gbps" for round link speeds
function fmtLinkSpeed(bps) {
  if (!bps) return null;
  if (bps >= 1e9 && bps % 1e9 === 0) return `${bps / 1e9} Gbps`;
  if (bps >= 1e6 && bps % 1e6 === 0) return `${bps / 1e6} Mbps`;
  return fmtBps(bps);
}

function fmtAgo(unixSeconds) {
  const secs = Math.max(0, Math.round(Date.now() / 1000 - unixSeconds));
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  return `${Math.round(secs / 3600)} h ago`;
}

// Fills the "Switch port" section. Returns the port usage for the seat heatmap.
function renderSeatPort(result) {
  blockSeatDdSwitch.textContent = result.device_name || result.hostname || '—';
  blockSeatDdPort.textContent = result.port || '—';
  const s = result.stats || {};
  if (!s.ifOperStatus && !s.state) { setPortState('unknown'); return null; }

  // Older servers send only the raw counters; ifIn is what the player sends.
  const state = s.state || (s.ifOperStatus === 'up' ? 'up' : 'down');
  const download = s.download_bps ?? (parseFloat(s.ifOutOctets_rate) || 0) * 8;
  const upload = s.upload_bps ?? (parseFloat(s.ifInOctets_rate) || 0) * 8;
  const speed = s.speed_bps ?? (parseFloat(s.ifSpeed) || 0);
  const linked = state === 'up' || state === 'errors';

  setPortState(state);
  seatPortDesc.textContent = s.description || '';
  seatPortDesc.classList.toggle('hidden', !s.description);

  if (state === 'disabled') blockSeatDdPortSpeed.textContent = 'Shut down on the switch';
  else if (!linked) blockSeatDdPortSpeed.textContent = 'No link';
  else blockSeatDdPortSpeed.textContent = [fmtLinkSpeed(speed), s.duplex && `${s.duplex} duplex`].filter(Boolean).join(' · ') || '—';
  blockSeatDdPortSpeed.className = linked ? '' : 'tone-danger';
  if (s.duplex === 'half') blockSeatDdPortSpeed.className = 'tone-warning';   // usually a negotiation problem

  blockSeatDdDownload.textContent = linked ? fmtBps(download) : '—';
  blockSeatDdUpload.textContent = linked ? fmtBps(upload) : '—';

  if (s.errors_in == null && s.errors_out == null) {
    seatPortErrors.textContent = '—';
    seatPortErrors.className = '';
  } else {
    const total = (s.errors_in || 0) + (s.errors_out || 0);
    let text = total ? `${(s.errors_in || 0).toLocaleString()} in · ${(s.errors_out || 0).toLocaleString()} out` : 'None';
    if (s.error_rate) text += ` (${s.error_rate}/s now)`;
    seatPortErrors.textContent = text;
    seatPortErrors.className = s.error_rate ? 'tone-warning' : total ? '' : 'tone-success';
  }

  const pct = s.utilization != null ? s.utilization * 100 : null;
  setBar(barSeatPort, seatPortLoad, pct != null ? Math.round(pct) : null);
  if (pct > 0 && pct < 1) seatPortLoad.textContent = '<1%';

  seatPortLibrenms.classList.toggle('hidden', !s.librenms_url);
  if (s.librenms_url) seatPortLibrenms.href = s.librenms_url;
  seatPortPolled.classList.toggle('hidden', !s.polled_at);
  if (s.polled_at) seatPortPolled.textContent = `LibreNMS polled this port ${fmtAgo(s.polled_at)}.`;

  return { total_bps: download + upload, in_rate_bps: upload, out_rate_bps: download,
           status: s.ifOperStatus, speed_bps: speed };
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
  seatPortRefresh.disabled = !seatData?.ip_address;

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
  await lookupSeatPort(seatNumber);
}

// Resolves the seat's IP to its switch port and fills the inspector. Also used by Refresh
// and the once-a-minute update while the seat stays selected.
async function lookupSeatPort(seatNumber) {
  const seatData = seatMappings[seatNumber];
  if (!seatData || !seatData.ip_address) return;
  seatPortRefresh.disabled = true;
  seatPortRefresh.classList.add('is-busy');
  try {
    const result = await api('GET', `/api/resolve/${encodeURIComponent(seatData.ip_address)}`);
    if (currentBlockSeatNumber !== seatNumber) return; // user moved on
    currentBlockSeatResolution = result;
    blockSeatDdMac.textContent = result.mac || '—';
    blockSeatDdVlan.textContent = result.vlan || '—';
    const portUsage = renderSeatPort(result);
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
  } finally {
    if (currentBlockSeatNumber === seatNumber) {
      seatPortRefresh.disabled = false;
      seatPortRefresh.classList.remove('is-busy');
    }
  }
}

seatPortRefresh.addEventListener('click', () => {
  if (selectedType === 'seat' && currentBlockSeatNumber) lookupSeatPort(currentBlockSeatNumber);
});
setInterval(() => {
  if (!document.hidden && selectedType === 'seat' && currentBlockSeatNumber) {
    lookupSeatPort(currentBlockSeatNumber).catch(() => {});
  }
}, SEAT_PORT_REFRESH);
// ── Block inspector ──────────────────────────────────────────────────────────────────
function selectBlock(id) {
  if (!id) { deselectAll(); return; }
  const block = seatBlocks.find(b => b.id === id);
  if (!block) { deselectAll(); return; }

  selectedId = id;
  selectedType = 'block';
  selection.clear();
  selection.add(selKey('block', id));
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
