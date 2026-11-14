// Floor plan editor: active security findings as dashed amber rings on their seats and switches
// (issue #29), and the count next to Security in the top bar. Classic script sharing one global
// scope with the other editor/*.js files (see README.md).
'use strict';

// Only for accounts that may see findings (seats.view: they name MACs and IPs).
const securityOn = document.body.dataset.security === 'on';
let securityMarkers = { seats: {}, switches: {} };

async function loadSecurityMarkers() {
  if (!securityOn) return;
  try {
    securityMarkers = await api('GET', '/api/security/markers');
  } catch {
    return;   // extra information; the floor plan works without it
  }
  markFindings();
}

function markFindings() {
  if (!securityOn) return;
  document.querySelectorAll('.has-finding').forEach((el) => el.classList.remove('has-finding'));
  for (const number of Object.keys(securityMarkers.seats)) {
    for (const el of document.querySelectorAll(`[data-seat-number="${CSS.escape(number)}"]`)) el.classList.add('has-finding');
  }
  for (const id of Object.keys(securityMarkers.switches)) {
    const el = document.querySelector(`.switch-marker[data-id="${CSS.escape(id)}"]`);
    if (el) el.classList.add('has-finding');
  }
  const total = Object.values(securityMarkers.seats).concat(Object.values(securityMarkers.switches))
    .reduce((a, b) => a + b, 0);
  const badge = document.getElementById('security-count');
  if (badge) { badge.textContent = String(total); badge.hidden = total === 0; }
}

if (securityOn) {
  window.addEventListener('lal:live', (e) => {
    if (e.detail && e.detail.type === 'security.finding') loadSecurityMarkers();
  });
  // Findings also clear on their own, which sends no event: look again every minute.
  setInterval(() => { if (!document.hidden) loadSecurityMarkers(); }, 60000);
}
