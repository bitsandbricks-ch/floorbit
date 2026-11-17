// Floor plan editor: which seat block or mark is drawn over which (`z`, floorbit/stacking.py).
// Bring to front / Send to back (Ctrl+Shift+] / Ctrl+Shift+[) and one step up or down (Ctrl+] / Ctrl+[),
// from the keyboard or the right-click menu. Blocks are ordered among blocks, marks among marks;
// switches always stay on top of both.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

const zOf = (item) => (Number.isInteger(item.z) ? item.z : 0);
// Bottom up; the same z keeps the list order (the order they were added in).
function byZ(list) {
  return list.map((item, i) => ({ item, i })).sort((a, b) => zOf(a.item) - zOf(b.item) || a.i - b.i).map(e => e.item);
}

// The new order of `list` with the items in `moving` (a Set of ids) moved: 'front', 'back', 'up', 'down'.
function restack(list, moving, how) {
  const order = byZ(list);
  const picked = order.filter(i => moving.has(i.id));
  const rest = order.filter(i => !moving.has(i.id));
  if (how === 'front') return [...rest, ...picked];
  if (how === 'back') return [...picked, ...rest];
  const out = [...order];
  if (how === 'up') {
    for (let i = out.length - 2; i >= 0; i--) {
      if (moving.has(out[i].id) && !moving.has(out[i + 1].id)) [out[i], out[i + 1]] = [out[i + 1], out[i]];
    }
  } else {
    for (let i = 1; i < out.length; i++) {
      if (moving.has(out[i].id) && !moving.has(out[i - 1].id)) [out[i], out[i - 1]] = [out[i - 1], out[i]];
    }
  }
  return out;
}

const STACK_LABEL = { front: 'bring to front', back: 'send to back', up: 'bring forward', down: 'send backward' };

// What the stacking keys act on: the selected mark, else the selected seat blocks.
function stackTarget() {
  if (typeof selectedMark !== 'undefined' && selectedMark) return { kind: 'mark', ids: new Set([selectedMark]) };
  const ids = new Set(selectedItems().filter(i => i.type === 'block').map(i => i.id));
  return ids.size ? { kind: 'block', ids } : null;
}

async function restackSelection(how, target = stackTarget()) {
  if (!target) return;
  const list = target.kind === 'mark' ? planMarks : seatBlocks;
  const order = restack(list, target.ids, how);
  // z = position from the bottom; only the items whose z changes are saved.
  const changes = order.map((item, z) => ({ id: item.id, from: zOf(item), to: z })).filter(c => c.from !== c.to);
  if (!changes.length) return;
  const save = async (which) => {
    for (const c of changes) {   // one at a time: the server keeps one change at a time anyway
      if (target.kind === 'mark') await saveMark(c.id, { z: c[which] });
      else await updateBlock(resolveId(c.id), { z: c[which] });
    }
    if (target.kind === 'mark') renderMarks(); else { renderAll(); markSelection(); }
  };
  try {
    await save('to');
    pushHistory({ label: STACK_LABEL[how], undo: () => save('from'), redo: () => save('to') });
  } catch (e) {
    toastError('Could not change the order', e);
  }
}

// Right-click entries for a seat block, a selection of blocks or a mark (menus.js).
function stackMenuEntries(target) {
  const run = (how) => () => restackSelection(how, target);
  return [
    { label: 'Bring to front', run: run('front'), key: 'Ctrl+Shift+]' },
    { label: 'Bring forward', run: run('up'), key: 'Ctrl+]' },
    { label: 'Send backward', run: run('down'), key: 'Ctrl+[' },
    { label: 'Send to back', run: run('back'), key: 'Ctrl+Shift+[' },
  ];
}
