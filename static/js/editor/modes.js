// Floor plan editor: the mode switch in the top bar. The editor is the Edit mode of the plan
// workspace (/plan, React); the other modes open there on the same hall. Classic script, see README.
'use strict';

(function planModes() {
  const nav = $('plan-modes');
  if (!nav) return;
  const DE = { Live: 'Live', 'Check-in': 'Check-in', Network: 'Netzwerk', Edit: 'Bearbeiten', Mode: 'Modus' };
  if (UI.lang() === 'de') {
    nav.setAttribute('aria-label', DE.Mode);
    for (const a of nav.querySelectorAll('a')) a.textContent = DE[a.textContent.trim()] || a.textContent;
  }
  // The hall can change without a reload of this script's state, so build the links on click.
  nav.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-mode]');
    if (!a || a.dataset.mode === 'edit') return;
    const url = new URL('/plan', location.origin);
    if (a.dataset.mode !== 'live') url.searchParams.set('mode', a.dataset.mode);
    const hall = $('hall-select')?.value;
    if (hall) url.searchParams.set('hall', hall);
    a.href = url.pathname + url.search;
  });
})();
