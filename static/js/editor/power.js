// Floor plan editor: the power layer (issue #45). Seats and switches take the colour of their
// circuit's load, distribution boards show where they hang, and the top bar counts circuits that
// are red or tripped. Classic script sharing one global scope with the other editor/*.js files
// (see README.md).
'use strict';

const powerOn = document.body.dataset.power === 'on';
let powerMarkers = { seats: {}, switches: {}, boards: [], counts: {} };
let powerLayer = false;
const POWER_STATES = ['ok', 'warn', 'crit', 'tripped', 'unknown'];

async function loadPowerMarkers() {
  if (!powerOn) return;
  try {
    powerMarkers = await api('GET', '/api/power/markers');
  } catch {
    return;   // extra information; the floor plan works without it
  }
  markPower();
}

function powerTitle(mark) {
  const load = mark.state === 'tripped' ? 'tripped' : mark.pct == null ? 'no reading' : `${mark.pct} %`;
  return `Circuit ${mark.circuit}: ${load}`;
}

function markPower() {
  if (!powerOn) return;
  const classes = POWER_STATES.map((s) => `power-${s}`);
  document.querySelectorAll('.power-tinted').forEach((el) => {
    el.classList.remove('power-tinted', ...classes);
    if (el.dataset.powerTitle) { el.title = el.dataset.powerTitle; delete el.dataset.powerTitle; }
  });
  const layer = document.getElementById('power-overlay');
  if (layer) layer.innerHTML = '';
  const counts = powerMarkers.counts || {};
  const bad = (counts.crit || 0) + (counts.tripped || 0);
  const badge = document.getElementById('power-count');
  if (badge) { badge.textContent = String(bad); badge.hidden = bad === 0; }
  if (!powerLayer) return;

  const tint = (el, mark) => {
    el.classList.add('power-tinted', `power-${mark.state}`);
    el.dataset.powerTitle = el.title || '';
    el.title = `${el.title ? el.title + ' · ' : ''}${powerTitle(mark)}`;
  };
  for (const [number, mark] of Object.entries(powerMarkers.seats || {})) {
    for (const el of blocksOverlay.querySelectorAll(`[data-seat-number="${CSS.escape(number)}"]`)) tint(el, mark);
  }
  for (const [id, mark] of Object.entries(powerMarkers.switches || {})) {
    const el = overlay.querySelector(`.switch-marker[data-id="${CSS.escape(id)}"]`);
    if (el) tint(el, mark);
  }
  if (layer) {
    for (const b of powerMarkers.boards || []) {
      const el = document.createElement('a');
      el.className = `power-board power-${b.state}`;
      el.href = '/power';
      el.style.left = b.x + '%';
      el.style.top = b.y + '%';
      el.title = `Distribution board ${b.name}`;
      el.innerHTML = `<span class="power-board-icon" aria-hidden="true">⚡</span><span class="power-board-name">${escHtml(b.name)}</span>`;
      layer.appendChild(el);
    }
  }
  const summary = document.getElementById('power-summary');
  if (summary) {
    const parts = [];
    if (counts.tripped) parts.push(`${counts.tripped} tripped`);
    if (counts.crit) parts.push(`${counts.crit} about to trip`);
    if (counts.warn) parts.push(`${counts.warn} getting close`);
    summary.textContent = parts.length ? parts.join(', ') : 'Every circuit with a reading is fine.';
  }
}

function setPowerLayer(on) {
  powerLayer = on;
  const btn = document.getElementById('btn-power');
  if (btn) setLayerButton(btn, on);
  document.getElementById('power-options')?.classList.toggle('hidden', !on);
  wrapper.classList.toggle('power-layer', on);
  writeJSON('layer-power', on);
  markPower();
  if (on) loadPowerMarkers();
}

if (powerOn) {
  document.getElementById('btn-power')?.addEventListener('click', () => setPowerLayer(!powerLayer));
  window.addEventListener('lal:live', (e) => {
    const type = e.detail && e.detail.type;
    if (type === 'power.changed' || type === 'power.alert') loadPowerMarkers();
  });
  // Meter readings change without an event for every one: look again every minute.
  setInterval(() => { if (!document.hidden) loadPowerMarkers(); }, 60000);
}
