// Floor plan editor: groups of seat blocks and merging blocks. A group (the block's `group` field)
// keeps several blocks together: a click selects all of them, and they move, turn and copy as one,
// while each keeps its own seat names. Merging (floorbit/block_merge.py) makes one block of blocks
// next to each other: rows or seat numbers carry on, space between them becomes a gap.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

function newGroupId() {
  return 'g-' + Math.random().toString(36).slice(2, 10);
}
function groupBlocks(group) {
  return group ? seatBlocks.filter(b => b.group === group) : [];
}
function selectedBlocks() {
  return selectedItems().filter(i => i.type === 'block').map(i => i.item);
}

// A click on a grouped block selects its whole group.
function selectGroup(group) {
  selection.clear();
  for (const b of groupBlocks(group)) selection.add(selKey('block', b.id));
  applySelection();
}
// True when the selection is exactly one group.
function selectionIsGroup(group) {
  const members = groupBlocks(group);
  return members.length > 1 && selection.size === members.length && members.every(b => inSelection('block', b.id));
}

async function setGroups(changes, label) {
  // changes: [{ id, from, to }] with the group before and after.
  const apply = (which) => Promise.all(changes.map(c => updateBlock(resolveId(c.id), { group: c[which] || '' })));
  await apply('to');
  pushHistory({ label, undo: () => apply('from'), redo: () => apply('to') });
  renderAll();
  markSelection();
}

async function groupSelection() {
  const blocks = selectedBlocks();
  if (blocks.length < 2) { toast('Select two or more seat blocks to group them'); return; }
  const group = newGroupId();
  try {
    await setGroups(blocks.map(b => ({ id: b.id, from: b.group || null, to: group })), `group ${blocks.length} seat blocks`);
    toast(`Grouped ${blocks.length} seat blocks · Ctrl+Shift+G ungroups`);
  } catch (e) { toastError('Could not group the seat blocks', e); }
}

async function ungroupSelection() {
  let blocks = selectedBlocks().filter(b => b.group);
  if (selectedType === 'block' && selectedId) {
    const one = seatBlocks.find(b => b.id === selectedId);
    if (one && one.group) blocks = groupBlocks(one.group);
  }
  if (!blocks.length) return;
  try {
    await setGroups(blocks.map(b => ({ id: b.id, from: b.group, to: null })), 'ungroup seat blocks');
    toast(`Ungrouped ${blocks.length} seat blocks`);
  } catch (e) { toastError('Could not ungroup the seat blocks', e); }
}

// R and Shift+R with several items: the whole selection turns a quarter around its middle.
async function rotateSelection(step) {
  const items = selectedItems();
  if (items.length < 2) return;
  const w = wrapper.offsetWidth, h = wrapper.offsetHeight;
  const pts = items.map(i => ({ ...i, px: i.item.x / 100 * w, py: i.item.y / 100 * h }));
  const cx = (Math.min(...pts.map(p => p.px)) + Math.max(...pts.map(p => p.px))) / 2;
  const cy = (Math.min(...pts.map(p => p.py)) + Math.max(...pts.map(p => p.py))) / 2;
  const a = step * Math.PI / 180;
  const round = v => Math.round(v * 100) / 100;
  const changes = pts.map(p => {
    const dx = p.px - cx, dy = p.py - cy;
    const to = { x: round((cx + dx * Math.cos(a) - dy * Math.sin(a)) / w * 100), y: round((cy + dx * Math.sin(a) + dy * Math.cos(a)) / h * 100) };
    const from = { x: p.item.x, y: p.item.y };
    if (p.type === 'block') {
      from.rotation = p.item.rotation || 0;
      to.rotation = (((from.rotation + step) % 360) + 360) % 360;
    }
    return { type: p.type, id: p.id, from, to };
  });
  const apply = (which) => Promise.all(changes.map(c => c.type === 'block'
    ? updateBlock(resolveId(c.id), c[which]) : updateSwitch(resolveId(c.id), c[which])));
  try {
    await apply('to');
    pushHistory({ label: `turn ${items.length} items`, undo: async () => { await apply('from'); renderAll(); }, redo: async () => { await apply('to'); renderAll(); } });
    renderAll();
  } catch (e) {
    toastError('Could not turn the selection', e);
    renderAll();
  }
}

// Ctrl+D: copies of the selected blocks next to them. Copies of a group are a new group.
async function duplicateSelection() {
  const blocks = selectedBlocks();
  if (!blocks.length) return;
  if (blocks.length === 1 && selectedType === 'block') { blockDetailDuplicate.click(); return; }
  await loadAllSeatRows();
  const groups = new Map();
  const made = [];
  try {
    for (const b of blocks) {
      if (b.group && !groups.has(b.group)) groups.set(b.group, newGroupId());
      const data = {
        ...blockPayload(b),
        ...(b.naming === 'rows' ? { row_start: nextFreeRow() } : { name: `${b.name || 'Block'} (copy)` }),
        x: b.x + 5, y: b.y + 5,
        group: b.group ? groups.get(b.group) : null,
      };
      const created = await createBlock(data);
      made.push({ ref: { id: created.id }, data });
    }
  } catch (e) {
    toastError('Could not copy all seat blocks', e);
  }
  if (!made.length) { renderAll(); return; }
  pushHistory({
    label: `copy ${made.length} seat blocks`,
    undo: async () => { for (const m of made) await deleteBlock(resolveId(m.ref.id)); },
    redo: async () => {
      for (const m of made) {
        const created = await createBlock(m.data);
        aliasId(resolveId(m.ref.id), created.id);
        m.ref.id = created.id;
      }
    },
  });
  renderAll();
  selection.clear();
  for (const m of made) selection.add(selKey('block', m.ref.id));
  applySelection();
}

// Merge the selected blocks into one (the server checks that they line up).
async function mergeSelection() {
  const blocks = selectedBlocks();
  if (blocks.length < 2) { toast('Select two or more seat blocks next to each other to merge them'); return; }
  const before = blocks.map(b => ({ ref: { id: b.id }, data: { ...blockPayload(b), hall_id: b.hall_id } }));
  const run = async () => {
    const res = await api('POST', '/api/seat-blocks/merge', { ids: before.map(b => resolveId(b.ref.id)) });
    seatBlocks = seatBlocks.filter(b => !res.removed.includes(b.id));
    const kept = seatBlocks.find(b => b.id === res.block.id);
    if (kept) Object.assign(kept, res.block); else seatBlocks.push(res.block);
    return res;
  };
  let res;
  try {
    res = await run();
  } catch (e) {
    toastError('Could not merge the seat blocks', e);
    return;
  }
  const keptId = res.block.id;
  pushHistory({
    label: `merge ${blocks.length} seat blocks`,
    undo: async () => {
      // The kept block gets its old size back, then the others come back as new blocks.
      for (const b of before) {
        if (resolveId(b.ref.id) === resolveId(keptId)) { await updateBlock(resolveId(keptId), b.data); continue; }
        const created = await createBlock(b.data);
        aliasId(resolveId(b.ref.id), created.id);
        b.ref.id = created.id;
      }
    },
    redo: run,
  });
  renderAll();
  selectBlock(keptId);
  toast(`Merged ${blocks.length} seat blocks into ${res.block.name || 'one block'}`);
}

// A dashed frame around each selected group, so it reads as one thing.
function drawGroupFrames() {
  let layer = $('group-frames');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'group-frames';
    layer.setAttribute('aria-hidden', 'true');
    blocksOverlay.parentNode.insertBefore(layer, blocksOverlay);
  }
  const groups = new Set(selectedBlocks().map(b => b.group).filter(Boolean));
  const wr = wrapper.getBoundingClientRect();
  const html = [];
  for (const g of groups) {
    const els = groupBlocks(g).map(b => markerFor('block', b.id)).filter(Boolean);
    if (els.length < 2) continue;
    const boxes = els.map(el => planBox(el.getBoundingClientRect(), wr));
    const l = Math.min(...boxes.map(b => b.l)), t = Math.min(...boxes.map(b => b.t));
    const r = Math.max(...boxes.map(b => b.r)), bt = Math.max(...boxes.map(b => b.b));
    html.push(`<div class="group-frame" style="left:${l - 6}px;top:${t - 6}px;width:${r - l + 12}px;height:${bt - t + 12}px"></div>`);
  }
  layer.innerHTML = html.join('');
}

// The selection inspector's Group section.
function fillGroupActions() {
  const box = $('multi-group-actions');
  if (!box) return;
  const blocks = selectedBlocks();
  const groups = new Set(blocks.map(b => b.group).filter(Boolean));
  const oneGroup = groups.size === 1 && selectionIsGroup([...groups][0]);
  box.classList.toggle('hidden', blocks.length < 2);
  $('multi-group').classList.toggle('hidden', oneGroup);
  $('multi-ungroup').classList.toggle('hidden', !groups.size);
  $('multi-detail-kind').textContent = oneGroup ? 'Group' : 'Selection';
}

if ($('multi-group-actions')) {
  $('multi-group').addEventListener('click', groupSelection);
  $('multi-ungroup').addEventListener('click', ungroupSelection);
  $('multi-merge').addEventListener('click', mergeSelection);
  $('multi-rotate').addEventListener('click', () => rotateSelection(90));
  $('multi-duplicate').addEventListener('click', duplicateSelection);
}
