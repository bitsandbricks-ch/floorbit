'use strict';
/*
 * Live updates: listens on /api/events (Server-Sent Events) and keeps the
 * floor plan in sync without a page reload.
 *
 *  - switch.status  → updates the switch's status dot and the hero counts
 *  - data.changed   → reloads switches / seat blocks changed in another browser
 *
 * Every event is also re-dispatched as a DOM event, `lal:live`, with
 * {type, data} in `detail`, so a reworked frontend can listen without
 * depending on this file's internals.
 *
 * This file only touches app.js through its global functions/state
 * (switches, renderAll, loadSwitches, loadSeatBlocks, dragState) and checks
 * each one exists first, so it degrades to "events only" if they change.
 */
(function () {
  if (!window.EventSource || !window.fetch) return;

  // Tag our own writes so we don't reload on echoes of them.
  const CLIENT_ID = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(16).slice(2);
  const origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.startsWith('/api/')) {
      init = Object.assign({}, init);
      const headers = new Headers(init.headers || {});
      headers.set('X-Client-Id', CLIENT_ID);
      init.headers = headers;
    }
    return origFetch(input, init);
  };

  function emit(type, data) {
    window.dispatchEvent(new CustomEvent('lal:live', { detail: { type, data } }));
  }

  function setIndicator(state) {
    document.documentElement.dataset.live = state;   // 'on' | 'off'
  }

  // ── switch.status ─────────────────────────────────────────────────────────
  function applyStatuses(map) {
    if (typeof switches === 'undefined' || !Array.isArray(switches)) return;
    let changed = false;
    for (const sw of switches) {
      const st = map[sw.id];
      if (st && sw.status !== st) { sw.status = st; changed = true; }
    }
    if (changed && typeof renderAll !== 'undefined') renderAll();
  }

  // ── data.changed (debounced, waits while dragging) ────────────────────────
  const pending = new Set();
  let reloadTimer = null;
  function scheduleReload(resource) {
    pending.add(resource);
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(runReload, 400);
  }
  async function runReload() {
    if (typeof dragState !== 'undefined' && dragState) { reloadTimer = setTimeout(runReload, 500); return; }
    const todo = Array.from(pending); pending.clear();
    try {
      if ((todo.includes('switches') || todo.includes('all')) && typeof loadSwitches !== 'undefined') {
        // keep statuses we already know across the reload
        const known = {};
        if (typeof switches !== 'undefined') for (const s of switches) known[s.id] = s.status;
        await loadSwitches();
        applyStatuses(known);
      }
      if ((todo.includes('seat-blocks') || todo.includes('all')) && typeof loadSeatBlocks !== 'undefined') await loadSeatBlocks();
      // app.js's load* functions only fetch, so draw the new data
      if (typeof renderAll !== 'undefined') renderAll();
    } catch (e) {
      console.warn('[live] reload failed', e);
    }
  }

  // ── connection ────────────────────────────────────────────────────────────
  function connect() {
    const es = new EventSource('/api/events');
    es.onopen = () => setIndicator('on');
    es.onerror = () => setIndicator('off');   // EventSource reconnects on its own

    es.addEventListener('hello', (e) => {
      const ev = JSON.parse(e.data);
      if (ev.data && ev.data.statuses) applyStatuses(ev.data.statuses);
      emit('hello', ev.data);
    });

    es.addEventListener('switch.status', (e) => {
      const ev = JSON.parse(e.data);
      applyStatuses({ [ev.data.id]: ev.data.status });
      emit('switch.status', ev.data);
    });

    es.addEventListener('data.changed', (e) => {
      const ev = JSON.parse(e.data);
      emit('data.changed', ev.data);
      if (ev.origin && ev.origin === CLIENT_ID) return;
      scheduleReload(ev.data.resource);
    });

    for (const type of ['monitor.poll', 'checkin', 'checkin.removed', 'checkin.refreshed', 'incident.changed',
                        'security.finding', 'power.changed', 'power.alert', 'alerts.changed']) {
      es.addEventListener(type, (e) => emit(type, JSON.parse(e.data).data));
    }
  }

  setIndicator('off');
  connect();
})();
