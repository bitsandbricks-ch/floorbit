// Floor plan editor: Dragging one item or a group of selected items.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

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

// Shift+click toggles an item in the selection without starting a drag
function suppressClickAfterMouseUp() {
  suppressNextClick = true;
  document.addEventListener('mouseup', () => setTimeout(() => { suppressNextClick = false; }, 0), { once: true });
}

function onMarkerMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();
  const marker = e.currentTarget;
  const sw = switches.find(s => s.id === marker.dataset.id);
  if (!sw) return;
  if (e.shiftKey) { toggleInSelection('switch', sw.id); suppressClickAfterMouseUp(); return; }
  if (selection.size > 1 && inSelection('switch', sw.id)) { startGroupDrag(e, 'switch', sw.id); return; }
  selectSwitch(sw.id);
  startDrag(e, 'switch', sw, marker);
}

function onBlockMouseDown(e) {
  if (e.button !== 0 || currentTool !== 'select') return;
  e.stopPropagation();
  const marker = e.currentTarget;
  const block = seatBlocks.find(b => b.id === marker.dataset.id);
  if (!block) return;
  if (e.shiftKey) { toggleInSelection('block', block.id); suppressClickAfterMouseUp(); return; }
  if (selection.size > 1 && inSelection('block', block.id)) { startGroupDrag(e, 'block', block.id); return; }
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
  scheduleHeatRender();
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
// ── Group drag (several selected items) ──────────────────────────────────────────────
function markerFor(type, id) {
  const container = type === 'block' ? blocksOverlay : overlay;
  return container.querySelector(`[data-id="${CSS.escape(id)}"]`);
}

// Moves every item in `list` ({ type, id, origX, origY }) by the same offset,
// clamped so that none of them leaves the floor plan.
function offsetItems(list, dx, dy) {
  const xs = list.map(i => i.origX), ys = list.map(i => i.origY);
  dx = Math.min(100 - Math.max(...xs), Math.max(-Math.min(...xs), dx));
  dy = Math.min(100 - Math.max(...ys), Math.max(-Math.min(...ys), dy));
  for (const it of list) {
    const item = findItem(it.type, it.id);
    if (!item) continue;
    item.x = Math.round((it.origX + dx) * 100) / 100;
    item.y = Math.round((it.origY + dy) * 100) / 100;
    const m = markerFor(it.type, it.id);
    if (m) { m.style.left = item.x + '%'; m.style.top = item.y + '%'; }
  }
  if (heatmapVisible) renderHeatmap();
}

function movesFrom(list) {
  const moves = [];
  for (const it of list) {
    const item = findItem(it.type, it.id);
    if (!item || (item.x === it.origX && item.y === it.origY)) continue;
    moves.push({ type: it.type, id: it.id, from: { x: it.origX, y: it.origY }, to: { x: item.x, y: item.y } });
  }
  return moves;
}

function startGroupDrag(e, type, id) {
  dragState = {
    type: 'group',
    clicked: { type, id },
    startX: e.clientX,
    startY: e.clientY,
    wrapperRect: wrapper.getBoundingClientRect(),
    moved: false,
    items: selectedItems().map(({ type: t, id: i, item }) => ({ type: t, id: i, origX: item.x, origY: item.y })),
  };
  document.addEventListener('mousemove', onGroupMouseMove);
  document.addEventListener('mouseup', onGroupMouseUp);
}

function onGroupMouseMove(e) {
  const s = dragState;
  if (!s || s.type !== 'group') return;
  const dxPx = e.clientX - s.startX;
  const dyPx = e.clientY - s.startY;
  if (!s.moved && Math.hypot(dxPx, dyPx) < 3) return;
  if (!s.moved) for (const it of s.items) markerFor(it.type, it.id)?.classList.add('dragging');
  s.moved = true;

  // Snap the item under the cursor; the others keep their relative positions
  const anchor = s.items.find(i => i.type === s.clicked.type && i.id === s.clicked.id) || s.items[0];
  const dx = snapToGrid(anchor.origX + dxPx / s.wrapperRect.width * 100) - anchor.origX;
  const dy = snapToGrid(anchor.origY + dyPx / s.wrapperRect.height * 100) - anchor.origY;
  offsetItems(s.items, dx, dy);
  const a = findItem(anchor.type, anchor.id);
  if (a) updatePositionDisplay(a.x, a.y);
}

async function onGroupMouseUp() {
  document.removeEventListener('mousemove', onGroupMouseMove);
  document.removeEventListener('mouseup', onGroupMouseUp);
  const s = dragState;
  dragState = null;
  if (!s || s.type !== 'group') return;
  for (const it of s.items) markerFor(it.type, it.id)?.classList.remove('dragging');

  if (!s.moved) {
    // A plain click on one of the selected items selects just that item
    if (s.clicked.type === 'block') selectBlock(s.clicked.id); else selectSwitch(s.clicked.id);
    return;
  }
  suppressNextClick = true;
  setTimeout(() => { suppressNextClick = false; }, 0);

  const moves = movesFrom(s.items);
  if (!moves.length) return;
  refreshSelectionPositions();
  moveQueue = moveQueue.then(() => commitMoves(moves, { label: moveLabel(moves) }));
}
