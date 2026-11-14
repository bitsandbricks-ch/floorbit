// Floor plan editor: Drawing switches, seat blocks and seats on the floor plan.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

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
  if (selectedType === 'multi') applySelection();
  if (typeof markIncidents === 'function') markIncidents();
  if (typeof markFindings === 'function') markFindings();
  if (typeof markPower === 'function') markPower();
  if (typeof markMatchSeats === 'function') markMatchSeats();
}

function matchesStatusFilter(sw) {
  return statusFilter === 'all' || statusBucket(sw.status) === statusFilter;
}

function renderOverlay() {
  overlay.innerHTML = '';
  for (const sw of switches) {
    if (sw.placed !== false && sw.x != null) overlay.appendChild(createMarker(sw));
  }
  scheduleHeatRender(); // re-tint the new switch cards
  if (typeof markIncidents === 'function') markIncidents();
  if (typeof markFindings === 'function') markFindings();
  if (typeof markPower === 'function') markPower();
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
    item.className = 'switch-item' + (inSelection('switch', sw.id) ? ' active' : '') + (sw.stale ? ' stale' : '');
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
    const activate = (e) => {
      if (e && e.shiftKey) { toggleInSelection('switch', sw.id); return; }
      selectSwitch(sw.id);
      focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(sw.id)}"]`));
    };
    item.addEventListener('click', activate);
    item.addEventListener('keydown', (e) => { if (e.key === 'Enter') activate(e); });
    frag.appendChild(item);
  }
  switchList.innerHTML = '';
  switchList.appendChild(frag);
}

function createMarker(sw) {
  const el = document.createElement('div');
  const isSelected = inSelection('switch', sw.id);
  el.className = 'switch-marker' + (isSelected ? ' selected' : '') + (matchesStatusFilter(sw) ? '' : ' dimmed') +
                 (sw.stale ? ' stale' : '');
  el.dataset.id = sw.id;
  el.style.left = sw.x + '%';
  el.style.top  = sw.y + '%';
  el.title = `${sw.name} · ${sw.status || 'unknown'}${sw.stale ? ' (last known, monitoring is down)' : ''}`;
  const hideLabel = getDeviceSetting(sw.id, 'hideLabel');
  el.innerHTML = `
    <div class="switch-pin status-${escHtml(sw.status || 'unknown')}">${pinSVG(sw.status)}</div>
    ${hideLabel ? '' : `<div class="switch-label">${escHtml(sw.name)}</div>`}
    <div class="switch-heat-card"><span class="switch-heat-name">${escHtml(sw.name)}</span><span class="switch-heat-rate"></span></div>`;
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
  const isSelected = inSelection('block', block.id);
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
      const cls = 'seat-block-seat' + (user || seatMappings[number]?.taken ? ' has-user' : '') +
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
