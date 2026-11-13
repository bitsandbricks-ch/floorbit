// Floor plan editor: The floor plan surface: coordinates, placing items, pan and zoom, box select.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

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
  updateGrid();
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

// Drag on empty space pans (left button in Select, middle button or Space anywhere).
// Shift+drag on empty space draws a selection box instead.
let spaceHeld = false;
canvasArea.addEventListener('mousedown', (e) => {
  if (e.target.closest('.toolbar, .zoom-bar, .switch-marker, .seat-marker, .seat-block')) return;
  if (e.button === 0 && e.shiftKey && currentTool === 'select' && !spaceHeld) {
    e.preventDefault();
    startMarquee(e);
    return;
  }
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
// ── Box select ───────────────────────────────────────────────────────────────────────
// Shift+drag on empty space: everything the box touches is added to the selection.
function startMarquee(e) {
  const el = document.createElement('div');
  el.className = 'marquee';
  canvasArea.appendChild(el);
  marqueeState = { x0: e.clientX, y0: e.clientY, el, hits: [], moved: false };
  document.addEventListener('mousemove', onMarqueeMove);
  document.addEventListener('mouseup', onMarqueeUp);
}
function onMarqueeMove(e) {
  const s = marqueeState;
  if (!s) return;
  if (!s.moved && Math.hypot(e.clientX - s.x0, e.clientY - s.y0) < 3) return;
  s.moved = true;

  const left = Math.min(s.x0, e.clientX), right  = Math.max(s.x0, e.clientX);
  const top  = Math.min(s.y0, e.clientY), bottom = Math.max(s.y0, e.clientY);
  const area = canvasArea.getBoundingClientRect();
  s.el.style.left   = (left - area.left) + 'px';
  s.el.style.top    = (top - area.top) + 'px';
  s.el.style.width  = (right - left) + 'px';
  s.el.style.height = (bottom - top) + 'px';

  s.hits = [];
  const test = (marker, type, hitEl) => {
    const r = hitEl.getBoundingClientRect();
    const hit = r.right >= left && r.left <= right && r.bottom >= top && r.top <= bottom;
    marker.classList.toggle('marquee-hit', hit);
    if (hit) s.hits.push(selKey(type, marker.dataset.id));
  };
  // Switches are hit-tested on the pin only: the hidden label still takes up space
  for (const m of overlay.querySelectorAll('.switch-marker')) test(m, 'switch', m.querySelector('.switch-pin') || m);
  for (const m of blocksOverlay.querySelectorAll('.seat-block')) test(m, 'block', m);
}
function onMarqueeUp() {
  document.removeEventListener('mousemove', onMarqueeMove);
  document.removeEventListener('mouseup', onMarqueeUp);
  const s = marqueeState;
  marqueeState = null;
  if (!s) return;
  s.el.remove();
  for (const m of document.querySelectorAll('.marquee-hit')) m.classList.remove('marquee-hit');
  if (!s.moved) return;
  suppressNextClick = true;
  setTimeout(() => { suppressNextClick = false; }, 0);
  if (!s.hits.length) return;
  for (const key of s.hits) selection.add(key);
  applySelection();
}

window.addEventListener('resize', () => {
  if (heatmapVisible) renderHeatmap();
  if (seatHeatmapVisible) renderSeatHeatmap();
});
