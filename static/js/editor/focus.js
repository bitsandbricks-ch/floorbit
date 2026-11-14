// Floor plan editor: open the floor plan on one switch or seat from a link, e.g. a problem in the
// Problems list (/?switch=<id> or /?seat=<seat>). Classic script sharing one global scope with
// the other editor/*.js files; the load order is in templates/index.html.
'use strict';

function focusFromUrl() {
  const params = new URLSearchParams(location.search);
  const switchId = params.get('switch');
  const seat = params.get('seat');
  if (!switchId && !seat) return;
  if (seat && blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(seat)}"]`)) {
    showBlockSeatDetail(seat);
    focusOnItem(blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(seat)}"]`));
  } else if (switchId && switches.some(s => s.id === switchId)) {
    selectSwitch(switchId);
    focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(switchId)}"]`));
  }
  flashSwitch(switchId);
  // Drop the parameters so a reload doesn't jump again. window.: the editor's `history` is undo.
  window.history.replaceState(null, '', location.pathname + location.hash);
}
