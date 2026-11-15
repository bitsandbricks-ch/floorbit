// Floor plan editor: muted switches get a small bell-off badge and say until when (issue #268),
// so a red pin someone is already working on doesn't send a second tech running.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
// problems.js fetches /api/problems anyway and hands the mutes over through setMutes().
'use strict';

let switchMutes = {};   // switch id -> unix time the mute ends

const BELL_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
  + 'stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 19a2.5 2.5 0 0 0 5 0"/>'
  + '<path d="M18 13V9a6 6 0 0 0-9.2-5M6.3 6.3A6 6 0 0 0 6 9v4l-2 3h12"/><path d="m3 3 18 18"/></svg>';

function setMutes(list) {
  switchMutes = {};
  for (const m of list || []) {
    if (m.kind !== 'health') switchMutes[m.switch_id] = m.until;
  }
  markMutes();
}

function markMutes() {
  document.querySelectorAll('.switch-marker.is-muted').forEach((el) => {
    el.classList.remove('is-muted');
    el.querySelector('.switch-muted')?.remove();
    if (el.dataset.titleBase) el.title = el.dataset.titleBase;
  });
  for (const [id, until] of Object.entries(switchMutes)) {
    const el = document.querySelector(`.switch-marker[data-id="${CSS.escape(id)}"]`);
    const pin = el && el.querySelector('.switch-pin');
    if (!pin) continue;
    const time = new Date(until * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    el.classList.add('is-muted');
    el.dataset.titleBase = el.title;
    el.title = `${el.title} · alerts muted until ${time}`;
    const badge = document.createElement('span');
    badge.className = 'switch-muted';
    badge.setAttribute('aria-hidden', 'true');
    badge.innerHTML = BELL_OFF;
    pin.appendChild(badge);
  }
}
