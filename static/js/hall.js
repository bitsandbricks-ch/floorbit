// The public attendee view (templates/hall.html, docs/kiosk.md): reloads which seats are online
// every minute from /api/public/seats. Seat numbers and true/false only.
'use strict';

(function () {
  const EVERY = 60_000;
  const count = document.getElementById('hall-count');
  const unknown = document.getElementById('hall-unknown');
  const updated = document.getElementById('hall-updated');
  const cells = [...document.querySelectorAll('.cell[data-seat]')];

  function showUpdated(at) {
    updated.textContent = at ? updated.dataset.text.replace('{time}',
      new Date(at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })) : '';
  }

  async function refresh() {
    let data;
    try {
      const hall = updated.dataset.hall;
      const res = await fetch('/api/public/seats' + (hall ? `?hall=${encodeURIComponent(hall)}` : ''),
        { cache: 'no-store' });
      if (!res.ok) return;
      data = await res.json();
    } catch { return; }   // keep what is shown; the next round tries again
    const seats = data.seats || {};
    cells.forEach((c) => c.classList.toggle('on', seats[c.dataset.seat] === true));
    const known = data.online !== null && data.online !== undefined;
    unknown.hidden = known;
    count.textContent = known
      ? count.dataset.text.replace('{online}', data.online).replace('{total}', data.total) : '';
    showUpdated(data.updated);
  }

  showUpdated(Number(updated.dataset.at) || null);
  setInterval(refresh, EVERY);
})();
