// Floor plan editor: Keyboard shortcuts.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Keyboard shortcuts ─────────────────────────────────────────────────────────────────
function isTyping(e) {
  const t = e.target;
  return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable;
}

const ARROW_DIRS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (anyModalOpen()) { closeAllModals(); return; }
    if (!contextMenu.classList.contains('hidden')) { contextMenu.classList.add('hidden'); return; }
    if (isTyping(e)) { e.target.blur(); return; }
    deselectAll();
    setTool('select');
    return;
  }
  if (isTyping(e) || anyModalOpen()) return;

  const mod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (mod && key === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
  if (mod && key === 'y') { e.preventDefault(); redo(); return; }
  if (mod && key === 'a') { e.preventDefault(); setTool('select'); selectAllItems(); return; }
  if (mod) return;

  if (e.key === ' ' && !spaceHeld) { spaceHeld = true; canvasArea.classList.add('panning'); e.preventDefault(); return; }

  if (ARROW_DIRS[e.key] && selection.size && currentTool === 'select' && !dragState) {
    e.preventDefault();
    nudgeSelection(...ARROW_DIRS[e.key], e.shiftKey);
    return;
  }

  switch (e.key) {
    case 'Delete':
    case 'Backspace':
      if (selection.size) { e.preventDefault(); deleteSelection(); }
      break;
    case 'v': case 'V': setTool('select'); break;
    case 's': case 'S': setTool('add-switch'); break;
    case 'b': case 'B': setTool('add-block'); break;
    case 'g': case 'G': setSnap(!snapEnabled); break;
    case 'f': case 'F': fitToContent(); break;
    case 't': case 'T': window.floorTheme?.toggle(); break;
    case '+': case '=': zoomCentered(ZOOM_STEP); break;
    case '-': case '_': zoomCentered(1 / ZOOM_STEP); break;
    case '0': resetView(); break;
    case '/': e.preventDefault(); universalSearch.focus(); break;
    case '?': shortcutsBackdrop.classList.remove('hidden'); break;
  }
});
document.addEventListener('keyup', (e) => {
  if (e.key === ' ') { spaceHeld = false; canvasArea.classList.remove('panning'); }
});
