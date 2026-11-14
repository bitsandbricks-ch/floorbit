// Floor plan editor on phones and tablets (issue #11). One finger works like the mouse (pan the
// plan, drag a switch or block, tap to select), two fingers pinch to zoom and pan, and on a narrow
// screen the sidebar is a drawer behind the ☰ button. The rest of the editor only knows mouse
// events, so one finger is passed on as mouse events instead of teaching every file about touch.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
'use strict';

const TAP_SLOP = 8;          // px a finger may wander and still count as a tap
const LONG_PRESS_MS = 550;   // holding still this long opens the context menu (menus.js)
let longPress = null;
let touchOne = null;         // {target, x, y, tap}
let pinch = null;            // {dist, cx, cy}

function sendMouse(type, target, x, y) {
  target.dispatchEvent(new MouseEvent(type, {
    bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: type === 'mouseup' ? 0 : 1,
  }));
}

function pinchOf(touches) {
  const [a, b] = [touches[0], touches[1]];
  return { dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1,
           cx: (a.clientX + b.clientX) / 2, cy: (a.clientY + b.clientY) / 2 };
}

function cancelLongPress() {
  clearTimeout(longPress);
  longPress = null;
}

function endOneFinger(x, y) {
  if (!touchOne) return;
  sendMouse('mouseup', document, x, y);
  touchOne = null;
}

canvasArea.addEventListener('touchstart', (e) => {
  if (e.target.closest('.toolbar, .zoom-bar')) return;   // real buttons: let the browser tap them
  e.preventDefault();                                    // no scrolling, no emulated mouse events
  if (e.touches.length === 1) {
    const t = e.touches[0];
    touchOne = { target: e.target, x: t.clientX, y: t.clientY, tap: true };
    sendMouse('mousedown', e.target, t.clientX, t.clientY);
    cancelLongPress();
    longPress = setTimeout(() => {
      longPress = null;
      if (!touchOne || !touchOne.tap) return;
      const { x, y } = touchOne;
      touchOne.tap = false;          // lifting the finger now is not a tap
      endOneFinger(x, y);
      // Ending the press may redraw the plan, so ask again what is under the finger.
      const target = document.elementFromPoint(x, y) || canvasArea;
      target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, view: window,
                                                           clientX: x, clientY: y, button: 2 }));
    }, LONG_PRESS_MS);
  } else if (e.touches.length === 2) {
    // A second finger turns whatever the first one started into a pinch, without a click.
    cancelLongPress();
    if (touchOne) { touchOne.tap = false; endOneFinger(touchOne.x, touchOne.y); }
    pinch = pinchOf(e.touches);
  }
}, { passive: false });

canvasArea.addEventListener('touchmove', (e) => {
  if (!touchOne && !pinch) return;
  e.preventDefault();
  if (pinch && e.touches.length >= 2) {
    const now = pinchOf(e.touches);
    zoomAt(now.cx, now.cy, now.dist / pinch.dist);
    setView(view.x + now.cx - pinch.cx, view.y + now.cy - pinch.cy, view.k);
    pinch = now;
    return;
  }
  if (touchOne && e.touches.length === 1) {
    const t = e.touches[0];
    if (Math.hypot(t.clientX - touchOne.x, t.clientY - touchOne.y) > TAP_SLOP) { touchOne.tap = false; cancelLongPress(); }
    sendMouse('mousemove', document, t.clientX, t.clientY);
  }
}, { passive: false });

function onTouchEnd(e) {
  cancelLongPress();
  if (pinch && e.touches.length < 2) pinch = null;
  if (!touchOne || e.touches.length) return;
  const t = e.changedTouches[0];
  const { target, tap } = touchOne;
  endOneFinger(t.clientX, t.clientY);
  if (tap) sendMouse('click', target, t.clientX, t.clientY);
}
canvasArea.addEventListener('touchend', onTouchEnd);
canvasArea.addEventListener('touchcancel', onTouchEnd);

// ── The sidebar as a drawer on narrow screens ───────────────────────────────────────
const btnSidebar = document.getElementById('btn-sidebar');
const narrow = window.matchMedia('(max-width: 760px)');

function setSidebarOpen(open) {
  document.body.classList.toggle('sidebar-open', open);
  if (btnSidebar) btnSidebar.setAttribute('aria-expanded', String(open));
}

if (btnSidebar) {
  btnSidebar.addEventListener('click', () => setSidebarOpen(!document.body.classList.contains('sidebar-open')));
  // Picking a search result or a switch closes the drawer, so the plan shows what was picked.
  document.getElementById('sidebar').addEventListener('click', (e) => {
    if (narrow.matches && e.target.closest('.search-result-item, .switch-item')) setSidebarOpen(false);
  });
  canvasArea.addEventListener('touchstart', () => { if (narrow.matches) setSidebarOpen(false); }, { capture: true });
  canvasArea.addEventListener('mousedown', () => { if (narrow.matches) setSidebarOpen(false); }, { capture: true });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setSidebarOpen(false); });
  narrow.addEventListener('change', () => setSidebarOpen(false));
}
