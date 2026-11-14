// Floor plan editor: the count of problems next to Problems in the top bar (issue #10): offline
// switches that aren't muted, red services, high security findings and red power circuits.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
'use strict';

async function loadProblemCount() {
  const badge = document.getElementById('problems-count');
  if (!badge) return;
  let body;
  try {
    body = await api('GET', '/api/problems');
  } catch {
    return;   // extra information; the floor plan works without it
  }
  const down = (body.counts && body.counts.down) || 0;
  badge.textContent = String(down);
  badge.hidden = down === 0;
}

window.addEventListener('lal:live', (e) => {
  const type = e.detail && e.detail.type;
  if (['monitor.poll', 'security.finding', 'power.alert', 'power.changed', 'alerts.changed'].includes(type)) loadProblemCount();
});
setInterval(() => { if (!document.hidden) loadProblemCount(); }, 60000);
