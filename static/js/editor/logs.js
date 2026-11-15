// Floor plan editor: seats and switches with syslog warnings in the last 10 minutes get a cyan
// underline (issue #92); the Logs page has the lines. Classic script sharing one global scope with
// the other editor/*.js files (see README.md).
'use strict';

// Only for accounts that may read logs (seats.view) while the receiver runs.
const logsOn = document.body.dataset.logs === 'on';
let logMarkers = { seats: {}, switches: {} };

async function loadLogMarkers() {
  if (!logsOn) return;
  try {
    logMarkers = await api('GET', '/api/logs/markers');
  } catch {
    return;   // extra information; the floor plan works without it
  }
  markLogLines();
}

function markLogLines() {
  if (!logsOn) return;
  document.querySelectorAll('.has-log').forEach((el) => el.classList.remove('has-log'));
  for (const number of Object.keys(logMarkers.seats)) {
    for (const el of document.querySelectorAll(`[data-seat-number="${CSS.escape(number)}"]`)) el.classList.add('has-log');
  }
  for (const id of Object.keys(logMarkers.switches)) {
    const el = document.querySelector(`.switch-marker[data-id="${CSS.escape(id)}"]`);
    if (el) el.classList.add('has-log');
  }
}

if (logsOn) {
  window.addEventListener('lal:live', (e) => {
    if (e.detail && e.detail.type === 'logs.alert') loadLogMarkers();
  });
  // Most lines send no event, and markers age out: look again every 30 seconds.
  setInterval(() => { if (!document.hidden) loadLogMarkers(); }, 30000);
}
