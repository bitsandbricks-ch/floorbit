// Floor plan editor: match seats (tournament awareness, issue #31) get a gold outline.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

let matchSeats = {};   // seat -> zone name

async function loadMatchSeats() {
  try {
    matchSeats = await api('GET', '/api/tournament/seats');
  } catch {
    return;   // the marks are extra; the floor plan works without them
  }
  markMatchSeats();
}

function markMatchSeats() {
  document.querySelectorAll('.match-seat').forEach((el) => {
    el.classList.remove('match-seat');
    el.removeAttribute('data-match');
  });
  for (const [number, zone] of Object.entries(matchSeats)) {
    for (const el of document.querySelectorAll(`[data-seat-number="${CSS.escape(number)}"]`)) {
      el.classList.add('match-seat');
      el.dataset.match = zone;
    }
  }
}

window.addEventListener('lal:live', (e) => {
  if (e.detail && e.detail.type === 'tournament.changed') loadMatchSeats();
});
