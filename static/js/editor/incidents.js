// Floor plan editor: open incidents as red rings on their seats and switches (issue #27).
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// Only for accounts that can see the incident board; the server marks the page for them.
const incidentsOn = document.body.dataset.incidents === 'on';
let incidentMarkers = { seats: {}, switches: {} };

async function loadIncidentMarkers() {
  if (!incidentsOn) return;
  try {
    incidentMarkers = await api('GET', '/api/incidents/markers');
  } catch {
    return;   // the markers are extra; the floor plan works without them
  }
  markIncidents();
}

function markIncidents() {
  if (!incidentsOn) return;
  const { seats: seatCounts, switches: switchCounts } = incidentMarkers;
  document.querySelectorAll('.has-incident').forEach((el) => {
    el.classList.remove('has-incident');
    el.removeAttribute('data-incidents');
  });
  for (const [number, count] of Object.entries(seatCounts)) {
    for (const el of document.querySelectorAll(`[data-seat-number="${CSS.escape(number)}"]`)) {
      el.classList.add('has-incident');
      el.dataset.incidents = String(count);
    }
  }
  for (const [id, count] of Object.entries(switchCounts)) {
    const el = document.querySelector(`.switch-marker[data-id="${CSS.escape(id)}"]`);
    if (el) { el.classList.add('has-incident'); el.dataset.incidents = String(count); }
  }
  const total = Object.values(seatCounts).concat(Object.values(switchCounts)).reduce((a, b) => a + b, 0);
  const badge = document.getElementById('incident-count');
  if (badge) { badge.textContent = String(total); badge.hidden = total === 0; }
}

if (incidentsOn) {
  // live.js re-dispatches every server event; a changed incident redraws the rings.
  window.addEventListener('lal:live', (e) => {
    if (e.detail && e.detail.type === 'incident.changed') loadIncidentMarkers();
  });
  setInterval(() => { if (!document.hidden) loadIncidentMarkers(); }, 60000);
}
