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

// Plugin entries (a plugin's context_menu:), only those this account may run. Loaded once.
let pluginMenuEntries = [];
async function loadPluginMenu() {
  try {
    pluginMenuEntries = (await api('GET', '/api/plugins/menu')).entries || [];
  } catch {
    pluginMenuEntries = [];   // plugins are extra; the menu works without them
  }
}
loadPluginMenu();

async function runPluginEntry(entry, params) {
  const what = params.seat ? `seat ${params.seat}` : params.switch;
  if (entry.danger && !(await confirmDialog({ title: entry.label, text: `Run "${entry.label}" (${entry.plugin_name}) on ${what}?`,
                                              okLabel: entry.label }))) return;
  try {
    const result = await api('POST', entry.url, params);
    toast(`${entry.label}: ${result.message || 'Done'}`, { type: 'success' });
  } catch (e) {
    toastError(entry.label, e);
  }
}

function pluginEntries(target) {
  const on = target.type === 'seat' ? 'seat' : target.type === 'switch' ? 'switch' : null;
  if (!on) return [];
  const sw = on === 'switch' ? switches.find(s => s.id === target.id) : null;
  if (on === 'switch' && !sw) return [];
  const params = on === 'seat' ? { seat: target.seat } : { switch: sw.name };
  return pluginMenuEntries.filter(e => e.targets.includes(on)).map(e => ({
    label: e.label, title: e.plugin_name, danger: e.danger, run: () => runPluginEntry(e, params),
  }));
}

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
    if (menuCanEdit()) {
      const gaps = gapMenuEntries(n);
      if (gaps.length) { sep(); items.push(...gaps); }
    }
  } else if (target.type === 'switch') {
    const sw = switches.find(s => s.id === target.id);
    add('Show ports', () => selectSwitch(target.id));
    if (sw) add('Show in inventory', () => { window.location.href = `/inventory?q=${encodeURIComponent(sw.name)}`; });
    if (typeof muteEntries === 'function') {
      const mutes = muteEntries(sw);
      if (mutes.length) { sep(); items.push(...mutes); }
    }
    if (menuCanEdit()) {
      sep();
      add('Rename…', () => openRenameModal(target.id));
      add('Delete', () => actionDeleteSwitch(target.id), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'block') {
    if (menuCanEdit()) {
      add('Edit…', () => { selectBlock(target.id); blockEditName.focus(); blockEditName.select(); });
      const grp = seatBlocks.find(b => b.id === target.id)?.group;
      if (grp && groupBlocks(grp).length > 1) {
        add('Select the group', () => selectGroup(grp));
        add('Ungroup', () => { selectGroup(grp); ungroupSelection(); }, { key: 'Ctrl+Shift+G' });
      }
      sep();
      items.push(...stackMenuEntries({ kind: 'block', ids: new Set([target.id]) }));
      sep();
      add('Delete', () => actionDeleteBlock(target.id), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'multi') {
    if (menuCanEdit()) {
      const blocks = selectedBlocks();
      if (blocks.length > 1) {
        const groups = new Set(blocks.map(b => b.group).filter(Boolean));
        if (!(groups.size === 1 && selectionIsGroup([...groups][0]))) add('Group', () => groupSelection(), { key: 'Ctrl+G' });
        if (groups.size) add('Ungroup', () => ungroupSelection(), { key: 'Ctrl+Shift+G' });
        add('Merge into one block', () => mergeSelection());
      }
      add('Turn a quarter', () => rotateSelection(90), { key: 'R' });
      if (blocks.length) add('Copy', () => duplicateSelection(), { key: 'Ctrl+D' });
      if (blocks.length) { sep(); items.push(...stackMenuEntries({ kind: 'block', ids: new Set(blocks.map(b => b.id)) })); }
      sep();
      add(`Delete ${selection.size} items`, () => actionDeleteSelection(), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'mark') {
    if (menuCanEdit()) {
      items.push(...stackMenuEntries({ kind: 'mark', ids: new Set([target.id]) }));
      sep();
      add('Delete', () => removeMark(target.id), { danger: true, key: 'Del' });
    }
  } else if (target.type === 'cable') {
    items.push(...cableMenuEntries(target.key));
  } else if (target.type === 'panel') {
    if (menuCanEdit()) add('Take off the plan', () => removePanel(target.name), { danger: true });
  } else if (target.type === 'floor') {
    if (menuCanEdit() && target.at) {
      const here = (open) => () => { pendingCoords = target.at; open(); };
      add('Add a switch here…', here(openAddModal));
      add('Add a seat block here…', here(openBlockModal));
      const panels = typeof panelMenuEntries === 'function' ? panelMenuEntries(target.at) : [];
      if (panels.length) { sep(); items.push(...panels); }
      sep();
    }
    add('Fit to screen', () => fitToContent());
    add('Reset zoom', () => resetView());
  }
  const fromPlugins = pluginEntries(target);
  if (fromPlugins.length) { sep(); items.push(...fromPlugins); }
  if (items.length && items[items.length - 1].sep) items.pop();
  return items;
}

function menuTitle(target) {
  if (target.type === 'seat') return `Seat ${target.seat}`;
  if (target.type === 'switch') return switches.find(s => s.id === target.id)?.name || 'Switch';
  if (target.type === 'block') return seatBlocks.find(b => b.id === target.id)?.name || 'Seat block';
  if (target.type === 'multi') return `${selection.size} selected`;
  if (target.type === 'cable') return cableMenuTitle(target.key);
  if (target.type === 'panel') return `Patch panel ${target.name}`;
  if (target.type === 'mark') {
    const m = planMarks.find(x => x.id === target.id);
    return m ? ({ text: m.text, icon: 'Icon', wall: 'Wall', zone: m.label || 'Zone' })[m.kind] || 'Mark' : 'Mark';
  }
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
    if (item.title) btn.title = item.title;   // the plugin it comes from
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
  const markEl = el.closest('[data-mark]');
  const cableEl = el.closest('[data-cable]');
  if (cableEl) return { type: 'cable', key: cableEl.dataset.cable };
  const panelEl = el.closest('[data-patch-panel]');
  if (panelEl && panelEl.closest('#cables-svg')) return { type: 'panel', name: panelEl.dataset.patchPanel };
  if (markEl && !switchEl && !blockEl) return { type: 'mark', id: markEl.dataset.mark };
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
  const at = p ? { x: snapToGrid(p.x), y: snapToGrid(p.y) } : null;
  return { type: 'floor', at };
}

canvasArea.addEventListener('contextmenu', (e) => {
  if (e.target.closest('.tool-rail, .zoom-bar')) return;   // real buttons keep the browser's menu
  e.preventDefault();
  const target = contextTargetOf(e.target, e.clientX, e.clientY);
  // Right-clicking something selects it, like a click, so the inspector matches the menu.
  if (target.type === 'switch') selectSwitch(target.id);
  else if (target.type === 'block') selectBlock(target.id);
  else if (target.type === 'mark') selectMark(target.id);
  else if (target.type === 'cable') selectCable(target.key);
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
