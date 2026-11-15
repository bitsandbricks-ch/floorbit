// Floor plan editor: Context menu and the rename dialog.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Context menu (issue #54) ──────────────────────────────────────────────────────────
// Right-click (long press on a touch screen, the Menu key or Shift+F10 on a keyboard) opens a
// menu for what is under the pointer: a seat, a switch, a seat block, a group, or empty floor.
// Entries only show when the account may use them; the server checks every request anyway.
const menuCanEdit = () => !document.body.classList.contains('read-only');
const menuCanEditSeats = () => document.body.dataset.seatEdit === 'on';
const menuIncidentsOn = () => document.body.dataset.incidents === 'on';

function menuEntries(target) {
  const items = [];
  const add = (label, run, opts = {}) => items.push({ label, run, ...opts });
  const sep = () => { if (items.length && !items[items.length - 1].sep) items.push({ sep: true }); };
  if (target.type === 'seat') {
    const n = target.seat;
    add('Seat details and port', () => showBlockSeatDetail(n));
    if (menuCanEditSeats()) add('Edit seat mapping…', () => { window.location.href = `/seat-mapping?q=${encodeURIComponent(n)}`; });
    sep();
    if (menuIncidentsOn()) add('Report an incident…', () => openPortDialog('flag', n));
    if (portInfo?.available) add('Bounce the port…', () => openPortDialog('bounce', n), { danger: true });
  } else if (target.type === 'switch') {
    const sw = switches.find(s => s.id === target.id);
    add('Show ports', () => selectSwitch(target.id));
    if (sw) add('Show in inventory', () => { window.location.href = `/inventory?q=${encodeURIComponent(sw.name)}`; });
    if (menuCanEdit()) {
      sep();
      add('Rename…', () => openRenameModal(target.id));
      add('Delete', () => actionDeleteSwitch(target.id), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'block') {
    if (menuCanEdit()) {
      add('Edit…', () => { selectBlock(target.id); blockEditName.focus(); blockEditName.select(); });
      add('Delete', () => actionDeleteBlock(target.id), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'multi') {
    if (menuCanEdit()) add(`Delete ${selection.size} items`, () => actionDeleteSelection(), { danger: true, key: 'Del' });
  } else if (target.type === 'floor') {
    if (menuCanEdit() && target.at) {
      const here = (open) => () => { pendingCoords = target.at; open(); };
      add('Add a switch here…', here(openAddModal));
      add('Add a seat block here…', here(openBlockModal));
      sep();
    }
    add('Fit to screen', () => fitToContent());
    add('Reset zoom', () => resetView());
  }
  if (items.length && items[items.length - 1].sep) items.pop();
  return items;
}

function menuTitle(target) {
  if (target.type === 'seat') return `Seat ${target.seat}`;
  if (target.type === 'switch') return switches.find(s => s.id === target.id)?.name || 'Switch';
  if (target.type === 'block') return seatBlocks.find(b => b.id === target.id)?.name || 'Seat block';
  if (target.type === 'multi') return `${selection.size} selected`;
  return '';
}

function closeContextMenu({ refocus = false } = {}) {
  if (contextMenu.classList.contains('hidden')) return;
  contextMenu.classList.add('hidden');
  if (refocus && contextMenu._opener && document.contains(contextMenu._opener)) contextMenu._opener.focus();
}

function openContextMenu(x, y, target, { keyboard = false } = {}) {
  const items = menuEntries(target);
  if (!items.length) return false;
  contextTarget = target;
  contextMenu._opener = document.activeElement;
  contextMenu.innerHTML = '';
  const title = menuTitle(target);
  if (title) {
    const head = document.createElement('div');
    head.className = 'context-title';
    head.textContent = title;
    contextMenu.appendChild(head);
    contextMenu.setAttribute('aria-label', title);
  } else {
    contextMenu.setAttribute('aria-label', 'Floor plan');
  }
  for (const item of items) {
    if (item.sep) {
      const line = document.createElement('div');
      line.className = 'context-sep';
      line.setAttribute('role', 'separator');
      contextMenu.appendChild(line);
      continue;
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'context-item' + (item.danger ? ' danger' : '');
    btn.setAttribute('role', 'menuitem');
    btn.tabIndex = -1;
    btn.textContent = item.label;
    if (item.key) {
      const kbd = document.createElement('kbd');
      kbd.textContent = item.key;
      btn.appendChild(kbd);
    }
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeContextMenu();
      item.run();
    });
    contextMenu.appendChild(btn);
  }
  contextMenu.classList.remove('hidden');
  const { innerWidth, innerHeight } = window;
  const w = contextMenu.offsetWidth, h = contextMenu.offsetHeight;
  contextMenu.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + 'px';
  contextMenu.style.top  = Math.max(8, Math.min(y, innerHeight - h - 8)) + 'px';
  // Focus goes into the menu, so the arrow keys work whichever way it was opened.
  const first = contextMenu.querySelector('.context-item');
  if (first) first.focus({ preventScroll: true });
  contextMenu.dataset.keyboard = keyboard ? 'on' : '';
  return true;
}

/** What a right-click at this element means. */
function contextTargetOf(el, clientX, clientY) {
  const seatEl = el.closest('.seat-block-seat');
  const blockEl = el.closest('.seat-block');
  const switchEl = el.closest('.switch-marker');
  if (switchEl) {
    const id = switchEl.dataset.id;
    if (selection.size > 1 && inSelection('switch', id)) return { type: 'multi' };
    return { type: 'switch', id };
  }
  if (blockEl) {
    const id = blockEl.dataset.id;
    if (selection.size > 1 && inSelection('block', id)) return { type: 'multi' };
    if (seatEl && seatEl.dataset.seatNumber) return { type: 'seat', seat: seatEl.dataset.seatNumber, block: id };
    return { type: 'block', id };
  }
  const p = clientToPercent(clientX, clientY);
  const at = p ? { x: Math.min(100, Math.max(0, snapToGrid(p.x))), y: Math.min(100, Math.max(0, snapToGrid(p.y))) } : null;
  return { type: 'floor', at };
}

canvasArea.addEventListener('contextmenu', (e) => {
  if (e.target.closest('.toolbar, .zoom-bar')) return;   // real buttons keep the browser's menu
  e.preventDefault();
  const target = contextTargetOf(e.target, e.clientX, e.clientY);
  // Right-clicking something selects it, like a click, so the inspector matches the menu.
  if (target.type === 'switch') selectSwitch(target.id);
  else if (target.type === 'block') selectBlock(target.id);
  openContextMenu(e.clientX, e.clientY, target);
});

/** The Menu key or Shift+F10: a menu for what is selected, else for the floor plan. */
function openContextMenuFromKeyboard() {
  let target = { type: 'floor', at: null };
  let el = null;
  if (selection.size > 1) {
    target = { type: 'multi' };
  } else if (selectedType === 'seat' && currentBlockSeatNumber) {
    target = { type: 'seat', seat: currentBlockSeatNumber };
    el = wrapper.querySelector(`.seat-block-seat[data-seat-number="${CSS.escape(currentBlockSeatNumber)}"]`);
  } else if (selectedType === 'switch' && selectedId) {
    target = { type: 'switch', id: selectedId };
    el = wrapper.querySelector(`.switch-marker[data-id="${CSS.escape(selectedId)}"]`);
  } else if (selectedType === 'block' && selectedId) {
    target = { type: 'block', id: selectedId };
    el = wrapper.querySelector(`.seat-block[data-id="${CSS.escape(selectedId)}"]`);
  }
  const box = (el || canvasArea).getBoundingClientRect();
  return openContextMenu(box.left + box.width / 2, box.top + box.height / 2, target, { keyboard: true });
}

contextMenu.addEventListener('keydown', (e) => {
  const entries = [...contextMenu.querySelectorAll('.context-item')];
  const i = entries.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const step = e.key === 'ArrowDown' ? 1 : -1;
    entries[(i + step + entries.length) % entries.length]?.focus();
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault();
    (e.key === 'Home' ? entries[0] : entries[entries.length - 1])?.focus();
  } else if (e.key === 'Escape' || e.key === 'Tab') {
    e.preventDefault();
    e.stopPropagation();
    closeContextMenu({ refocus: true });
  }
});

// The Menu key also fires the browser's own menu on whatever has focus, which is now our menu.
contextMenu.addEventListener('contextmenu', (e) => e.preventDefault());
document.addEventListener('click', (e) => { if (!contextMenu.contains(e.target)) closeContextMenu(); });
document.addEventListener('scroll', () => closeContextMenu(), true);
window.addEventListener('resize', () => closeContextMenu());

// ── Rename modal ───────────────────────────────────────────────────────────────────────
let renameTargetId = null;

function openRenameModal(id) {
  const sw = switches.find(s => s.id === id);
  if (!sw) return;
  renameTargetId = id;
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
  if (!name || !renameTargetId) { renameInput.focus(); return; }
  const id = renameTargetId;
  const sw = switches.find(s => s.id === id);
  const oldName = sw ? sw.name : '';
  if (name === oldName) { renameBackdrop.classList.add('hidden'); return; }
  try {
    await updateSwitch(id, { name });
    renameBackdrop.classList.add('hidden');
    pushHistory({
      label: `rename ${oldName}`,
      undo: () => updateSwitch(resolveId(id), { name: oldName }),
      redo: () => updateSwitch(resolveId(id), { name }),
    });
    renderAll();
    if (selectedId === id) selectSwitch(id);
  } catch (e) {
    toastError('Could not rename switch', e);
  }
});
