'use strict';
/*
 * Read-only kiosk view (/kiosk): the floor plan scaled to fit the screen,
 * switch status and seat occupancy, no editing.
 *
 * Data:
 *  - Layout from /api/switches, /api/seat-blocks, /api/seats; occupancy from
 *    /api/seats/info. Reloaded every minute, or right away on a live event.
 *  - Switch status: if the server has live updates (/api/events, MR !4) the
 *    page listens for pushes and only polls as a safety net. Otherwise it polls
 *    /api/status/snapshot (!4) or, without it, /api/switches/<id>/status.
 *
 * Nothing here writes to the server.
 */
(function () {
  // ── Options ────────────────────────────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  function intParam(name, def, min, max) {
    const v = parseInt(params.get(name), 10);
    return Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : def;
  }
  const OPT = {
    title:        params.get('title') || '',
    labels:       params.get('labels') !== '0',
    statusEvery:  intParam('refresh', 15, 5, 300) * 1000,
    reloadEvery:  intParam('reload', 360, 0, 10080) * 60_000,   // minutes → ms, 0 = never
  };
  const LAYOUT_EVERY      = 60_000;
  const LIVE_STATUS_EVERY = 60_000;          // safety-net poll while live updates are on
  const LIVE_RETRY        = 5 * 60_000;      // retry /api/events after it failed for good
  const STALE_AFTER       = Math.max(90_000, OPT.statusEvery * 4);
  const MAX_ALERTS        = 12;

  // ── State ──────────────────────────────────────────────────────────────────
  let config     = { netbox_enabled: false, librenms_enabled: false };
  let switches   = [];
  let seats      = [];
  let seatBlocks = [];
  let seatInfo   = {};               // seat number → { username, ip_address }
  let live       = false;
  let snapshotSupported = null;      // null = not tried yet
  let lastOkAt   = null;
  let lastError  = null;
  let layoutSig  = '';
  const downSince = {};              // switch id → time first seen offline
  let prevTaken  = null;             // Set of seat numbers taken at the last render

  const $ = (id) => document.getElementById(id);
  const mapEl    = $('k-map');
  const planEl   = $('k-plan');
  const blocksEl = $('k-blocks');
  const seatsEl  = $('k-seats-layer');
  const swEl     = $('k-switches');

  // ── HTTP ───────────────────────────────────────────────────────────────────
  async function getJSON(path) {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) {
      const err = new Error(`${path} returned ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  // ── Helpers shared with app.js (keep in sync) ──────────────────────────────
  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Same as pinSVG() in app.js
  function pinSVG(status) {
    let glyph;
    if (status === 'offline') {
      glyph = '<path d="M5.4 3.4l3.2 3.2M8.6 3.4L5.4 6.6" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>';
    } else if (status === 'online') {
      glyph = '<circle cx="7" cy="5" r="2.2" fill="rgba(255,255,255,0.85)"/>';
    } else {
      glyph = '<circle cx="7" cy="5" r="2.2" fill="rgba(255,255,255,0.30)"/>';
    }
    return `<svg viewBox="0 0 14 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M7 0C4.24 0 2 2.24 2 5c0 4.5 5 13 5 13s5-8.5 5-13C12 2.24 9.76 0 7 0z"
            fill="currentColor" stroke="rgba(0,0,0,0.4)" stroke-width="0.6"/>
      ${glyph}
    </svg>`;
  }

  // Same numbering as blockSeatNumbers() in app.js, so seat numbers match the editor
  function blockSeatNumbers(block) {
    const totalSeats = block.cols * block.rows;
    const prefix = block.name ? block.name.toUpperCase() + '-' : '';
    const rotation = (block.rotation || 0) % 360;
    const base = Array.from({ length: totalSeats }, (_, i) => i + 1);
    let ordered = [];
    if (rotation >= 0 && rotation < 90) {
      ordered = [...base];
    } else if (rotation >= 90 && rotation < 180) {
      for (let row = 0; row < block.rows; row++) {
        ordered.push(...base.slice(row * block.cols, (row + 1) * block.cols).reverse());
      }
    } else if (rotation >= 180 && rotation < 270) {
      ordered = [...base].reverse();
    } else {
      for (let row = block.rows - 1; row >= 0; row--) {
        ordered.push(...base.slice(row * block.cols, (row + 1) * block.cols));
      }
    }
    if (block.reverse_numbers) ordered.reverse();
    return ordered.map(n => ({ number: `${prefix}${n}`, display: n }));
  }

  function bucket(status) {
    return status === 'online' || status === 'offline' ? status : 'unknown';
  }
  function placedSwitches() {
    return switches.filter(s => s.placed !== false && s.x != null);
  }

  // ── Rendering ──────────────────────────────────────────────────────────────
  function renderSwitches() {
    const html = [];
    for (const sw of placedSwitches()) {
      const st = sw.status || 'unknown';
      html.push(
        `<div class="switch-marker${st === 'offline' ? ' is-offline' : ''}" data-id="${escHtml(sw.id)}"
              style="left:${Number(sw.x)}%;top:${Number(sw.y)}%" title="${escHtml(sw.name)} · ${escHtml(st)}">
           <div class="switch-pin status-${escHtml(st)}">${pinSVG(st)}</div>
           ${OPT.labels ? `<div class="switch-label">${escHtml(sw.name)}</div>` : ''}
         </div>`);
    }
    swEl.innerHTML = html.join('');
  }

  function renderBlocks() {
    const taken = new Set();
    const html = [];
    for (const block of seatBlocks) {
      const rotation = (block.rotation || 0) % 360;
      const counter = rotation ? `transform: rotate(${-rotation}deg);` : '';
      const numbers = blockSeatNumbers(block);
      let inner = block.name ? `<div class="seat-block-label">${escHtml(block.name)}</div>` : '';
      let i = 0;
      for (let row = 0; row < block.rows; row++) {
        inner += '<div class="seat-block-row">';
        for (let col = 0; col < block.cols; col++) {
          const { number, display } = numbers[i++];
          const user = seatInfo[number]?.username;
          let cls = 'seat-block-seat';
          if (user) {
            taken.add(number);
            cls += ' has-user';
            if (prevTaken && !prevTaken.has(number)) cls += ' just-taken';
          }
          inner += `<div class="${cls}" style="${counter}" data-seat-number="${escHtml(number)}">${escHtml(display)}</div>`;
        }
        inner += '</div>';
      }
      html.push(
        `<div class="seat-block" data-id="${escHtml(block.id)}"
              style="left:${Number(block.x)}%;top:${Number(block.y)}%;transform:translate(-50%,-50%) rotate(${rotation}deg)">${inner}</div>`);
    }
    blocksEl.innerHTML = html.join('');

    seatsEl.innerHTML = seats.map(seat =>
      `<div class="seat-marker" style="left:${Number(seat.x)}%;top:${Number(seat.y)}%;transform:translate(-50%,-50%) rotate(${Number(seat.rotation) || 0}deg)">${escHtml(seat.number || '')}</div>`
    ).join('');

    const total = seatBlocks.reduce((n, b) => n + b.cols * b.rows, 0);
    $('k-seats').textContent = total ? `${taken.size} / ${total}` : '–';
    $('k-seats-stat').classList.toggle('hidden', !total);
    prevTaken = taken;
  }

  function renderStats() {
    const placed = placedSwitches();
    const online  = placed.filter(s => s.status === 'online').length;
    const offline = placed.filter(s => s.status === 'offline').length;
    const unknown = placed.length - online - offline;
    $('k-online').textContent  = placed.length ? `${online} / ${placed.length}` : '0';
    $('k-offline').textContent = offline;
    $('k-unknown').textContent = unknown;
    $('k-offline-stat').classList.toggle('has-items', offline > 0);
    $('k-unknown-stat').classList.toggle('hidden', unknown === 0 || !config.librenms_enabled);
    $('k-offline-stat').classList.toggle('hidden', !config.librenms_enabled);
  }

  function fmtSince(ts) {
    const mins = Math.floor((Date.now() - ts) / 60_000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min`;
    const h = Math.floor(mins / 60);
    return `${h} h ${mins % 60} min`;
  }

  function renderAlerts() {
    const down = placedSwitches()
      .filter(s => s.status === 'offline')
      .sort((a, b) => (downSince[a.id] || 0) - (downSince[b.id] || 0) || a.name.localeCompare(b.name));
    $('k-alerts').classList.toggle('hidden', down.length === 0);
    $('k-alerts-count').textContent = down.length ? `(${down.length})` : '';
    const shown = down.slice(0, MAX_ALERTS);
    let html = shown.map(sw =>
      `<li class="k-alert"><span class="k-alert-name">${escHtml(sw.name)}</span>` +
      `<span class="k-alert-since">${downSince[sw.id] ? fmtSince(downSince[sw.id]) : ''}</span></li>`).join('');
    if (down.length > shown.length) html += `<li class="k-alert-more">+ ${down.length - shown.length} more</li>`;
    $('k-alerts-list').innerHTML = html;
  }

  function trackDowntime() {
    for (const sw of switches) {
      if (sw.status === 'offline') { if (!downSince[sw.id]) downSince[sw.id] = Date.now(); }
      else delete downSince[sw.id];
    }
  }

  function updateEmpty() {
    const empty = !placedSwitches().length && !seatBlocks.length && !seats.length;
    $('k-empty').classList.toggle('hidden', !empty);
  }

  function renderAll() {
    const alertsWereHidden = $('k-alerts').classList.contains('hidden');
    trackDowntime();
    renderSwitches();
    renderBlocks();
    renderStats();
    renderAlerts();
    updateEmpty();
    // The alert column changes the map width, so refit when it appears or goes
    const sig = computeLayoutSig();
    if (sig !== layoutSig || alertsWereHidden !== $('k-alerts').classList.contains('hidden')) {
      layoutSig = sig;
      fitToContent(true);
    }
  }

  function renderStatusOnly() {
    trackDowntime();
    const alertsWereHidden = $('k-alerts').classList.contains('hidden');
    renderSwitches();
    renderStats();
    renderAlerts();
    if (alertsWereHidden !== $('k-alerts').classList.contains('hidden')) fitToContent(true);
  }

  function computeLayoutSig() {
    return JSON.stringify([
      placedSwitches().map(s => [s.id, s.x, s.y, s.name]),
      seatBlocks.map(b => [b.id, b.x, b.y, b.cols, b.rows, b.rotation, b.name]),
      seats.map(s => [s.id, s.x, s.y]),
    ]);
  }

  // ── Fit to screen ──────────────────────────────────────────────────────────
  let fitK = 1;
  function fitToContent(animate) {
    // Measure at scale 1 so the bounding box is in plan pixels
    planEl.classList.remove('animate');
    planEl.style.transform = 'none';
    const els = planEl.querySelectorAll('.switch-marker, .seat-block, .seat-marker');
    const area = mapEl.getBoundingClientRect();
    if (!els.length || !area.width || !area.height) return;
    const pr = planEl.getBoundingClientRect();
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      minX = Math.min(minX, r.left - pr.left);
      minY = Math.min(minY, r.top - pr.top);
      maxX = Math.max(maxX, r.right - pr.left);
      maxY = Math.max(maxY, r.bottom - pr.top);
    }
    const pad = Math.max(24, Math.min(area.width, area.height) * 0.05);
    const w = Math.max(maxX - minX, 40);
    const h = Math.max(maxY - minY, 40);
    const k = Math.min(8, Math.max(0.2, Math.min((area.width - pad * 2) / w, (area.height - pad * 2) / h)));
    const tx = area.width / 2 - (minX + maxX) / 2 * k;
    const ty = area.height / 2 - (minY + maxY) / 2 * k;
    // Re-apply the old transform first so the transition starts from it
    if (animate) {
      planEl.style.transform = planEl.dataset.transform || 'none';
      void planEl.offsetWidth;
      planEl.classList.add('animate');
    }
    const t = `translate(${tx}px, ${ty}px) scale(${k})`;
    planEl.style.transform = t;
    planEl.dataset.transform = t;
    fitK = k;
  }
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => fitToContent(false), 150);
  });

  // ── Loading ────────────────────────────────────────────────────────────────
  function markOk() { lastOkAt = Date.now(); lastError = null; updateSyncLine(); }
  function markError(e) { lastError = e; updateSyncLine(); }

  async function loadConfig() {
    try { config = await getJSON('/api/config'); } catch { /* keep defaults */ }
    $('k-title').textContent = OPT.title || $('k-title').dataset.default || 'Floor plan';
    document.title = `${$('k-title').textContent} · Kiosk`;
  }

  async function loadSeatInfo() {
    try {
      const data = await getJSON('/api/seats/info');
      seatInfo = data.seats || {};
    } catch {
      seatInfo = {};   // no seats.json / no source: everything shows as free
    }
  }

  async function loadLayout() {
    const known = Object.fromEntries(switches.map(s => [s.id, s.status]));
    const [sw, blocks, legacy] = await Promise.all([
      getJSON('/api/switches'),
      getJSON('/api/seat-blocks'),
      getJSON('/api/seats').catch(() => []),
      loadSeatInfo(),
    ]);
    switches = sw.map(s => ({ ...s, status: known[s.id] || s.status }));
    seatBlocks = blocks;
    seats = legacy;
  }

  function applyStatuses(map) {
    let changed = false;
    for (const sw of switches) {
      const st = map[sw.id];
      if (st && sw.status !== st) { sw.status = st; changed = true; }
    }
    return changed;
  }

  async function loadStatuses() {
    if (!config.librenms_enabled) return;
    if (snapshotSupported !== false) {
      try {
        const snap = await getJSON('/api/status/snapshot');
        snapshotSupported = true;
        // An empty snapshot means the monitor is off; fall back to per-switch lookups
        if (snap.last_poll && snap.statuses && Object.keys(snap.statuses).length) {
          applyStatuses(snap.statuses);
          return;
        }
      } catch (e) {
        if (e.status === 404) snapshotSupported = false;
      }
    }
    const placed = placedSwitches();
    let failures = 0;
    await Promise.all(placed.map(async (sw) => {
      try {
        const data = await getJSON(`/api/switches/${encodeURIComponent(sw.id)}/status`);
        sw.status = data.status;
      } catch { failures++; }
    }));
    if (placed.length && failures === placed.length) throw new Error('Status lookups failed');
  }

  // ── Schedulers ─────────────────────────────────────────────────────────────
  let statusTimer = null;
  let layoutTimer = null;

  async function statusTick() {
    clearTimeout(statusTimer);
    try {
      await loadStatuses();
      renderStatusOnly();
      markOk();
    } catch (e) {
      markError(e);
    }
    statusTimer = setTimeout(statusTick, live ? LIVE_STATUS_EVERY : OPT.statusEvery);
  }

  async function layoutTick() {
    clearTimeout(layoutTimer);
    try {
      await loadLayout();
      renderAll();
      markOk();
    } catch (e) {
      markError(e);
    }
    layoutTimer = setTimeout(layoutTick, LAYOUT_EVERY);
  }

  let layoutSoon = null;
  function scheduleLayout() {
    clearTimeout(layoutSoon);
    layoutSoon = setTimeout(layoutTick, 400);
  }
  let seatsSoon = null;
  function scheduleSeatInfo() {
    clearTimeout(seatsSoon);
    seatsSoon = setTimeout(async () => {
      await loadSeatInfo();
      renderBlocks();
    }, 400);
  }

  // ── Live updates (/api/events, MR !4) ──────────────────────────────────────
  function setLive(on) {
    if (live === on) return;
    live = on;
    updateSyncLine();
    // Switching back to polling: poll now instead of waiting for the slow timer
    if (!on) statusTick();
  }

  function connectLive() {
    if (!window.EventSource) return;
    const es = new EventSource('/api/events');
    const parse = (e) => { try { return JSON.parse(e.data).data || {}; } catch { return {}; } };

    es.onopen = () => setLive(true);
    es.onerror = () => {
      setLive(false);
      // 404 (no !4 / live updates off) closes the stream for good; try again later
      if (es.readyState === EventSource.CLOSED) {
        es.close();
        setTimeout(connectLive, LIVE_RETRY);
      }
    };
    es.addEventListener('hello', (e) => {
      const data = parse(e);
      if (data.statuses && applyStatuses(data.statuses)) renderStatusOnly();
      markOk();
    });
    es.addEventListener('switch.status', (e) => {
      const data = parse(e);
      if (data.id && applyStatuses({ [data.id]: data.status })) renderStatusOnly();
      markOk();
    });
    es.addEventListener('monitor.poll', () => markOk());
    es.addEventListener('data.changed', (e) => {
      const data = parse(e);
      if (data.resource === 'switches' || data.resource === 'seat-blocks') scheduleLayout();
      else if (data.resource === 'settings') loadConfig();
      else if (data.resource === 'all') { loadConfig(); scheduleLayout(); }   // a restored backup
    });
    for (const type of ['checkin', 'checkin.removed', 'checkin.refreshed']) {
      es.addEventListener(type, scheduleSeatInfo);
    }
  }

  // ── Header: clock, sync line, stale banner ─────────────────────────────────
  function pad2(n) { return String(n).padStart(2, '0'); }
  function updateClock() {
    const d = new Date();
    $('k-clock').textContent = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  function updateSyncLine() {
    const dot = $('k-live-dot');
    const text = $('k-sync-text');
    const age = lastOkAt ? Math.round((Date.now() - lastOkAt) / 1000) : null;
    const ageText = age == null ? '' : age < 5 ? 'updated just now'
      : age < 60 ? `updated ${age}s ago` : `updated ${Math.round(age / 60)} min ago`;

    dot.className = 'k-live-dot' + (lastError && (!lastOkAt || age * 1000 > STALE_AFTER) ? ' error' : live ? ' live' : ' polling');
    if (!config.librenms_enabled && lastOkAt) {
      text.textContent = `No switch status (LibreNMS not set up) · ${ageText}`;
    } else if (live) {
      text.textContent = `Live · ${ageText || 'waiting for data'}`;
    } else {
      text.textContent = `Every ${Math.round(OPT.statusEvery / 1000)}s · ${ageText || 'loading'}`;
    }

    const stale = $('k-stale');
    const isStale = lastOkAt ? Date.now() - lastOkAt > STALE_AFTER : !!lastError;
    stale.classList.toggle('hidden', !isStale);
    if (isStale) {
      const when = lastOkAt ? new Date(lastOkAt) : null;
      stale.textContent = when
        ? `No fresh data since ${pad2(when.getHours())}:${pad2(when.getMinutes())}. Status shown may be out of date.`
        : 'Cannot reach the server. Retrying…';
    }
  }

  setInterval(() => {
    updateClock();
    updateSyncLine();
    if (Object.keys(downSince).length) renderAlerts();   // "down for" counters
  }, 1000);

  // ── Kiosk niceties ─────────────────────────────────────────────────────────
  // Hide the mouse pointer when it's idle
  let cursorTimer = null;
  document.addEventListener('mousemove', () => {
    document.body.classList.remove('cursor-hidden');
    clearTimeout(cursorTimer);
    cursorTimer = setTimeout(() => document.body.classList.add('cursor-hidden'), 3000);
  });
  cursorTimer = setTimeout(() => document.body.classList.add('cursor-hidden'), 3000);

  // Double-click (or F) toggles full screen
  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  }
  document.addEventListener('dblclick', toggleFullscreen);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'f' || e.key === 'F') toggleFullscreen();
  });
  setTimeout(() => { $('k-fs-hint').style.opacity = '0'; }, 15_000);

  // Keep the screen awake where the browser allows it
  async function keepAwake() {
    try { if (navigator.wakeLock) await navigator.wakeLock.request('screen'); } catch { /* not allowed */ }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) keepAwake(); });
  keepAwake();

  // Reload the page now and then to pick up new deployments (only if the server answers)
  if (OPT.reloadEvery) {
    setInterval(async () => {
      try { await getJSON('/api/config'); location.reload(); } catch { /* try next time */ }
    }, OPT.reloadEvery);
  }

  // ── Start ───────────────────────────────────────────────────────────────────
  async function start() {
    updateClock();
    await loadConfig();
    await layoutTick();
    statusTick();
    connectLive();
  }
  start();
})();
