// Floor plan editor: the seat states layer (issue #55). Seats are drawn the way the Seats view
// (/plan) draws them: online filled, offline hollow with a slash, unknown dashed, and a cyan
// corner when checked in, so a state never relies on colour alone. The states come from
// /api/plan, the same place the Seats view reads them.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

const SEAT_STATE_CLASSES = ['st-online', 'st-offline', 'st-unknown', 'st-checked'];
let seatStatesOn = readJSON('layer-seat-states', true) !== false;
let seatStates = {};   // seat -> {state, checked_in, ...}
let seatStatesTimer = null;

async function loadSeatStates() {
  if (!seatStatesOn) return;
  try {
    const hall = typeof currentHall === 'string' && currentHall ? `?hall=${encodeURIComponent(currentHall)}` : '';
    seatStates = (await api('GET', `/api/plan${hall}`)).seats || {};
  } catch {
    return;   // the marks are extra; the floor plan works without them
  }
  markSeatStates();
}

function markSeatStates() {
  for (const el of document.querySelectorAll('.seat-block-seat[data-seat-number]')) {
    el.classList.remove(...SEAT_STATE_CLASSES);
    if (!seatStatesOn) continue;
    const s = seatStates[el.dataset.seatNumber];
    if (!s) continue;
    el.classList.add(`st-${s.state}`);
    if (s.checked_in) el.classList.add('st-checked');
  }
}

function setSeatStatesLayer(on) {
  seatStatesOn = on;
  writeJSON('layer-seat-states', on);
  const btn = document.getElementById('btn-seat-states');
  if (btn) setLayerButton(btn, on);
  document.getElementById('seat-states-legend')?.classList.toggle('hidden', !on);
  clearInterval(seatStatesTimer);
  if (on) {
    seatStatesTimer = setInterval(loadSeatStates, 30000);
    loadSeatStates();
  } else {
    markSeatStates();
  }
}

function initSeatStates() {
  document.getElementById('btn-seat-states')?.addEventListener('click', () => setSeatStatesLayer(!seatStatesOn));
  setSeatStatesLayer(seatStatesOn);
}

window.addEventListener('lal:live', (e) => {
  const type = e.detail && e.detail.type;
  if (seatStatesOn && (type === 'stats.changed' || type === 'monitor.poll' || type === 'data.changed')) loadSeatStates();
});
