// Floor plan editor: Context menu and the rename dialog.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Context menu ───────────────────────────────────────────────────────────────────────
function openContextMenu(e, target) {
  contextTarget = target;
  ctxRename.textContent = target.type === 'block' ? 'Edit…' : 'Rename…';
  ctxRename.classList.toggle('hidden', target.type === 'multi');
  ctxDelete.firstChild.textContent = target.type === 'multi' ? `Delete ${selection.size} items ` : 'Delete ';
  contextMenu.classList.remove('hidden');
  const { innerWidth, innerHeight } = window;
  const w = contextMenu.offsetWidth, h = contextMenu.offsetHeight;
  contextMenu.style.left = Math.min(e.clientX, innerWidth - w - 8) + 'px';
  contextMenu.style.top  = Math.min(e.clientY, innerHeight - h - 8) + 'px';
}
function onMarkerContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  if (selection.size > 1 && inSelection('switch', id)) { openContextMenu(e, { type: 'multi' }); return; }
  selectSwitch(id);
  openContextMenu(e, { type: 'switch', id });
}
function onBlockContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  const id = e.currentTarget.dataset.id;
  if (selection.size > 1 && inSelection('block', id)) { openContextMenu(e, { type: 'multi' }); return; }
  selectBlock(id);
  openContextMenu(e, { type: 'block', id });
}

document.addEventListener('click', () => contextMenu.classList.add('hidden'));
document.addEventListener('scroll', () => contextMenu.classList.add('hidden'), true);

ctxRename.addEventListener('click', (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  if (!contextTarget) return;
  if (contextTarget.type === 'switch') openRenameModal(contextTarget.id);
  else { selectBlock(contextTarget.id); blockEditName.focus(); blockEditName.select(); }
});
ctxDelete.addEventListener('click', (e) => {
  e.stopPropagation();
  contextMenu.classList.add('hidden');
  if (!contextTarget) return;
  if (contextTarget.type === 'multi') actionDeleteSelection();
  else if (contextTarget.type === 'switch') actionDeleteSwitch(contextTarget.id);
  else actionDeleteBlock(contextTarget.id);
});
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
