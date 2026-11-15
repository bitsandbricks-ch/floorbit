// Floor plan editor: muted switches get a small bell-off badge and say until when (issue #268),
// so a red pin someone is already working on doesn't send a second tech running.
// Classic script sharing one global scope with the other editor/*.js files (see README.md).
// problems.js fetches /api/problems anyway and hands the mutes over through setMutes().
// The right-click menu of a switch mutes, extends or unmutes it (issue #270), for crew with
// incidents.work: the server says so as can_mute.
'use strict';

let switchMutes = {};   // switch id -> unix time the mute ends
let canMute = false;
let muteTarget = null;  // the switch the dialog is for

const BELL_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
  + 'stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 19a2.5 2.5 0 0 0 5 0"/>'
  + '<path d="M18 13V9a6 6 0 0 0-9.2-5M6.3 6.3A6 6 0 0 0 6 9v4l-2 3h12"/><path d="m3 3 18 18"/></svg>';

function setMutes(list, can) {
  canMute = !!can;
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

// ── Muting from the floor plan (issue #270) ───────────────────────────────────────────
function muteEntries(sw) {
  if (!canMute || !sw) return [];
  if (!switchMutes[sw.id]) return [{ label: 'Mute alerts…', run: () => openMuteDialog(sw) }];
  return [
    { label: 'Mute 30 minutes longer', run: () => changeMute(sw, 'PATCH', { minutes: 30 }, 'Muted 30 minutes longer') },
    { label: 'Unmute', run: () => changeMute(sw, 'DELETE', null, 'Alerts are back on') },
  ];
}

async function changeMute(sw, method, body, done) {
  try {
    await api(method, `/api/alerts/mutes/${encodeURIComponent(sw.id)}`, body ?? undefined);
    toast(`${done}: ${sw.name}`);
    loadProblemCount();
  } catch (err) {
    toastError('Could not change the mute', err);
  }
}

function muteDialogOpen() {
  return !$('mute-backdrop').classList.contains('hidden');
}

function openMuteDialog(sw) {
  muteTarget = sw;
  $('mute-title').textContent = `Mute alerts for ${sw.name}`;
  $('mute-reason').value = '';
  $('mute-error').hidden = true;
  $('mute-backdrop').classList.remove('hidden');
  $('mute-minutes').focus();
}

function closeMuteDialog() {
  $('mute-backdrop').classList.add('hidden');
  muteTarget = null;
}

$('mute-cancel').addEventListener('click', closeMuteDialog);
$('mute-backdrop').addEventListener('click', (e) => { if (e.target === $('mute-backdrop')) closeMuteDialog(); });
$('mute-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const sw = muteTarget;
  if (!sw) return;
  $('mute-ok').disabled = true;
  try {
    await api('POST', '/api/alerts/mutes', {
      switch_id: sw.id, minutes: Number($('mute-minutes').value), reason: $('mute-reason').value });
    closeMuteDialog();
    toast(`Muted: ${sw.name}`);
    loadProblemCount();
  } catch (err) {
    $('mute-error').textContent = err.message;
    $('mute-error').hidden = false;
  } finally {
    $('mute-ok').disabled = false;
  }
});
