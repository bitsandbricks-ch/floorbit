// Floor plan editor: Creating, changing and deleting switches and seat blocks (server and local state), group actions, loading.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Data operations (server + local state) ──────────────────────────────────────
async function createManualSwitch(data) {
  const sw = await api('POST', '/api/switches', { ...data, hall_id: currentHall });
  switches.push(sw);
  return sw;
}
async function updateSwitch(id, patch) {
  // Placing a switch puts it in the hall on screen.
  if ('x' in patch) patch = { ...patch, hall_id: currentHall };
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
  const block = await api('POST', '/api/seat-blocks', { ...data, hall_id: currentHall });
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
  if (selectedType === 'multi') { await actionDeleteSelection(); return; }
  if (!selectedId) return;
  if (selectedType === 'block') await actionDeleteBlock(selectedId);
  else if (selectedType === 'switch') await actionDeleteSwitch(selectedId);
}
// ── Group actions (box-select, Shift+click, Ctrl+A) ────────────────────────────────
// moves: [{ type, id, from: {x, y}, to: {x, y} }] – one undo step for all of them.
function saveMoves(moves, which) {
  return Promise.all(moves.map((m) => {
    const rid = resolveId(m.id);
    return m.type === 'block' ? updateBlock(rid, m[which]) : updateSwitch(rid, m[which]);
  }));
}

let moveQueue = Promise.resolve();   // keeps position saves in order (fast arrow-key nudges)
const NUDGE_MERGE_MS = 1500;

async function commitMoves(moves, { label, nudge = false }) {
  try {
    await saveMoves(moves, 'to');
  } catch (e) {
    for (const m of moves) {
      const item = findItem(m.type, resolveId(m.id));
      if (item) { item.x = m.from.x; item.y = m.from.y; }
    }
    renderAll();
    toastError('Could not save the new positions', e);
    return;
  }
  // Repeated arrow-key nudges of the same items become one undo step
  const sig = moves.map(m => selKey(m.type, m.id)).sort().join(',');
  const last = history[history.length - 1];
  if (nudge && last && last.nudgeSig === sig && Date.now() - last.at < NUDGE_MERGE_MS && !future.length) {
    for (const m of moves) {
      const prev = last.moves.find(p => p.type === m.type && p.id === m.id);
      if (prev) prev.to = m.to;
    }
    last.at = Date.now();
    return;
  }
  const entry = {
    label,
    moves,
    undo: () => saveMoves(entry.moves, 'from'),
    redo: () => saveMoves(entry.moves, 'to'),
  };
  if (nudge) { entry.nudgeSig = sig; entry.at = Date.now(); }
  pushHistory(entry);
}

function moveLabel(moves) {
  if (moves.length > 1) return `move ${moves.length} items`;
  return moves[0].type === 'block' ? 'move seat block' : 'move switch';
}

function removeRecord(rec) {
  const id = resolveId(rec.ref.id);
  return rec.type === 'block' ? deleteBlock(id) : deleteSwitch(id);
}
async function restoreRecord(rec) {
  const { snapshot } = rec;
  if (rec.type === 'block') {
    const created = await createBlock(snapshot);
    aliasId(resolveId(rec.ref.id), created.id);
    rec.ref.id = created.id;
  } else if (snapshot.source === 'manual') {
    const created = await createManualSwitch({ name: snapshot.name, x: snapshot.x, y: snapshot.y });
    aliasId(resolveId(rec.ref.id), created.id);
    rec.ref.id = created.id;
  } else {
    await updateSwitch(resolveId(rec.ref.id), { x: snapshot.x, y: snapshot.y });
  }
}

async function actionDeleteSelection() {
  const items = selectedItems();
  if (!items.length) return;
  const netbox = items.some(i => i.type === 'switch' && i.item.source !== 'manual');
  const ok = await confirmDialog({
    title: `Delete ${items.length} items?`,
    text: `${describeCounts(items)} will be removed from the map` +
          (netbox ? ' (NetBox switches go back to the list of devices to place)' : '') +
          '. You can undo this.',
  });
  if (!ok) return;
  const records = [];
  for (const { type, id, item } of items) {
    const rec = {
      type,
      ref: { id },
      snapshot: type === 'block' ? blockPayload(item)
                                 : { name: item.name, x: item.x, y: item.y, source: item.source },
    };
    try {
      await removeRecord(rec);
      records.push(rec);
    } catch (e) {
      toastError(`Could not delete ${itemName(type, item)}`, e);
    }
  }
  deselectAll();
  renderAll();
  if (!records.length) return;
  pushHistory({
    label: `delete ${records.length} items`,
    undo: async () => { for (const r of records) await restoreRecord(r); },
    redo: async () => { for (const r of records) await removeRecord(r); },
  });
  undoToast(`Deleted ${records.length} items`);
}
// ── Load data ──────────────────────────────────────────────────────────────────────
async function loadSeatMappings() {
  try {
    const data = await api('GET', '/api/seats/info');
    seatMappings = data.seats || {};
  } catch (e) {
    // Roles without seats.view (viewers, kiosks) only learn which seats are taken.
    try {
      const data = await api('GET', '/api/seats/occupancy');
      seatMappings = Object.fromEntries((data.taken || []).map(s => [s, { taken: true }]));
    } catch {
      seatMappings = {};
    }
  }
}
async function loadSwitches()   { switches   = inHall(await api('GET', '/api/switches')); }
async function loadSeats()      { seats      = await api('GET', '/api/seats'); }
async function loadSeatBlocks() { seatBlocks = inHall(await api('GET', '/api/seat-blocks')); }
