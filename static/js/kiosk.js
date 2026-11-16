'use strict';
/*
 * Read-only kiosk view (/kiosk): the floor plan scaled to fit the screen,
 * switch status and seat occupancy, no editing.
 *
 * Data:
 *  - Layout from /api/switches, /api/seat-blocks, /api/seats; occupancy from
 *    /api/seats/occupancy (taken or not, never who). Reloaded every minute, or right away on a live event.
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
    hall:         params.get('hall') || '',                      // which hall; the first by default
    heat:         params.get('view') === 'heat',                 // seats coloured by their traffic
    grid:         params.get('grid') !== '0',
    marks:        params.get('marks') !== '0',                   // labels, walls, zones and icons
  };
  // The big screen is often in a public place: only the marks attendee pages show (plan_marks.PUBLIC_LAYERS).
  const MARK_LAYERS = ['overview', 'safety'];
  const HEAT_EVERY        = 30_000;
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
  let seatInfo   = {};               // seat number → { taken: true }
  let live       = false;
  let snapshotSupported = null;      // null = not tried yet
  let lastOkAt   = null;
  let lastError  = null;
  let layoutSig  = '';
  const downSince = {};              // switch id → time first seen offline
  let prevTaken  = null;             // Set of seat numbers taken at the last render
  let heat       = {};               // seat number → traffic in bit/s (?view=heat)
  let marks      = [];
  let markIcons  = {};

  const $ = (id) => document.getElementById(id);
  const mapEl    = $('k-map');
  const planEl   = $('k-plan');
  const blocksEl = $('k-blocks');
  const seatsEl  = $('k-seats-layer');
  const swEl     = $('k-switches');
  const gridEl   = $('k-grid');

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

  // The server sends each block's seat names row by row (floorbit/seat_names.py), the same as the editor's.
  function blockSeatNumbers(block) {
    return (block.seat_rows || []).flat().map(number => ({ number, display: number.split('-').pop() }));
  }

  // A row's letter, beside seat 1 ("start"), after the last seat ("end"), both or none.
  function rowLabel(block, row, side) {
    const letter = (block.row_letters || [])[row];
    const where = block.row_labels || 'start';
    if (!letter || where === 'none') return '';
    const atFirstColumn = (side === 'first') === !!block.seat_one_first;
    const wanted = where === 'both' || (where === 'start') === atFirstColumn;
    const rotation = (block.rotation || 0) % 360;
    return wanted ? `<div class="seat-block-rowlabel" style="${rotation ? `transform: rotate(${-rotation}deg);` : ''}">${escHtml(letter)}</div>` : '';
  }

  // ── Labels, walls, zones and icons (as the editor draws them, static/js/editor/marks.js) ──
  function renderMarks() {
    const svg = [], html = [];
    for (const m of marks) {
      if (m.kind === 'zone') {
        svg.push(`<g class="mark-zone zone-${escHtml(m.color)}"><rect x="${+m.x}" y="${+m.y}" width="${+m.w}" height="${+m.h}" vector-effect="non-scaling-stroke"/></g>`);
        if (m.label) html.push(`<div class="mark-zone-label zone-${escHtml(m.color)}" style="left:${+m.x}%;top:${+m.y}%">${escHtml(m.label)}</div>`);
      } else if (m.kind === 'wall') {
        svg.push(`<g class="mark-wall${m.style === 'dashed' ? ' dashed' : ''}"><line x1="${+m.x}" y1="${+m.y}" x2="${+m.x2}" y2="${+m.y2}" vector-effect="non-scaling-stroke"/></g>`);
      } else if (m.kind === 'text' || m.kind === 'icon') {
        const turn = m.rotation ? ` rotate(${+m.rotation}deg)` : '';
        const inner = m.kind === 'text' ? escHtml(m.text)
          : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${
            (markIcons[m.icon] || []).map(d => `<path d="${escHtml(d)}"/>`).join('')}</svg>`;
        html.push(`<div class="mark-${m.kind} size-${escHtml(m.size || 'm')}" style="left:${+m.x}%;top:${+m.y}%;transform:translate(-50%,-50%)${turn}">${inner}</div>`);
      }
    }
    $('k-marks-svg').innerHTML = svg.join('');
    $('k-marks').innerHTML = html.join('');
  }

  // ── Grid ───────────────────────────────────────────────────────────────────
  // The editor's grid (static/js/editor/layers.js): steps in % of the plan, the finest one that
  // stays at least GRID_MIN_PX apart, a stronger line every few steps. Follows the fit.
  const GRID_STEPS = [0.5, 1, 2.5, 5, 10, 25, 50];
  const GRID_MIN_PX = 12;
  function updateGrid(tx, ty, k) {
    if (!gridEl) return;
    gridEl.hidden = !OPT.grid;
    if (!OPT.grid) return;
    const w = planEl.offsetWidth * k, h = planEl.offsetHeight * k;
    if (!w || !h) return;
    const pxPerPercent = Math.min(w, h) / 100;
    let i = GRID_STEPS.findIndex(step => step * pxPerPercent >= GRID_MIN_PX);
    if (i < 0) i = GRID_STEPS.length - 1;
    const minor = GRID_STEPS[i], major = GRID_STEPS[Math.min(i + 2, GRID_STEPS.length - 1)];
    const st = gridEl.style;
    st.setProperty('--grid-minor-w', `${minor * w / 100}px`);
    st.setProperty('--grid-minor-h', `${minor * h / 100}px`);
    st.setProperty('--grid-major-w', `${major * w / 100}px`);
    st.setProperty('--grid-major-h', `${major * h / 100}px`);
    st.setProperty('--grid-x', `${tx}px`);
    st.setProperty('--grid-y', `${ty}px`);
  }

  // ── Heat view ──────────────────────────────────────────────────────────────
  // Traffic per seat from /api/stats/seats (seat numbers and numbers only), on a log scale so
  // 1 Mbit/s and 500 Mbit/s both read: green for a little, amber, red for a lot.
  function heatStyle(bps) {
    if (!bps) return '';
    const level = Math.min(1, Math.max(0, (Math.log10(bps) - 5) / 4));   // 100 kbit/s … 1 Gbit/s
    const hue = Math.round(130 - 130 * level);
    return `background:hsl(${hue} 75% 45%);border-color:hsl(${hue} 75% 35%);color:#fff;`;
  }

  async function loadHeat() {
    try {
      heat = (await getJSON('/api/stats/seats')).seats || {};
    } catch {
      heat = {};
    }
    renderBlocks();
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

  // Gaps inside a block (floorbit/seat_gaps.py): room after a column in every row, a lane after a row.
  function gapAfter(gaps, after) {
    return (gaps || []).filter(g => Number(g.after) === after).reduce((n, g) => n + Number(g.size), 0);
  }
  function gapSpacer(size, dir) {
    const px = Math.max(0, size * 20 - 2);   // an 18 px seat plus the 2 px flex gap per seat
    return `<div class="seat-gap" style="flex:none;${dir === 'col' ? `width:${px}px` : `height:${px}px`}"></div>`;
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
        if (row && gapAfter(block.row_gaps, row)) inner += gapSpacer(gapAfter(block.row_gaps, row), 'row');
        inner += '<div class="seat-block-row">' + rowLabel(block, row, 'first');
        for (let col = 0; col < block.cols; col++) {
          if (col && gapAfter(block.col_gaps, col)) inner += gapSpacer(gapAfter(block.col_gaps, col), 'col');
          const { number, display } = numbers[i++];
          const user = seatInfo[number]?.taken;
          let cls = 'seat-block-seat';
          if (user) {
            taken.add(number);
            cls += ' has-user';
            if (prevTaken && !prevTaken.has(number)) cls += ' just-taken';
          }
          const style = counter + (OPT.heat ? heatStyle(heat[number]) : '');
          inner += `<div class="${cls}" style="${style}" data-seat-number="${escHtml(number)}">${escHtml(display)}</div>`;
        }
        inner += rowLabel(block, row, 'last') + '</div>';
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
    renderMarks();
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
      marks.map(m => [m.id, m.x, m.y, m.x2, m.y2, m.w, m.h]),
    ]);
  }

  // ── Fit to screen ──────────────────────────────────────────────────────────
  let fitK = 1;
  function fitToContent(animate) {
    // Measure at scale 1 so the bounding box is in plan pixels
    planEl.classList.remove('animate');
    planEl.style.transform = 'none';
    const els = planEl.querySelectorAll('.switch-marker, .seat-block, .seat-marker, #k-marks > *, #k-marks-svg > *');
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
    updateGrid(tx, ty, k);
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
      // Only which seats are taken: the kiosk never gets nicks or IPs.
      const data = await getJSON('/api/seats/occupancy');
      seatInfo = Object.fromEntries((data.taken || []).map(s => [s, { taken: true }]));
    } catch {
      seatInfo = {};   // no seats.json / no source: everything shows as free
    }
  }

  // One hall per screen (?hall=<id>); its background image goes under the plan.
  let hall = null;
  let hallCount = 1;
  function showHall(list) {
    hallCount = list.length || 1;
    hall = list.find(h => h.id === OPT.hall) || list[0] || null;
    const bg = $('k-plan-bg');
    if (!bg) return;
    bg.hidden = !(hall && hall.background);
    if (hall && hall.background && bg.getAttribute('src') !== hall.background) bg.src = hall.background;
  }

  async function loadLayout() {
    const known = Object.fromEntries(switches.map(s => [s.id, s.status]));
    const [sw, blocks, legacy, hallList] = await Promise.all([
      getJSON('/api/switches'),
      getJSON('/api/seat-blocks'),
      getJSON('/api/seats').catch(() => []),
      getJSON('/api/halls').then(r => r.halls).catch(() => []),
      loadSeatInfo(),
    ]);
    showHall(hallList);
    if (OPT.marks) {
      const body = await getJSON(`/api/plan-marks${hall ? `?hall=${encodeURIComponent(hall.id)}` : ''}`).catch(() => ({}));
      markIcons = body.icons || {};
      marks = (body.marks || []).filter(m => MARK_LAYERS.includes(m.layer || 'overview'));
    }
    const here = (item) => !hall || item.hall_id === hall.id;
    switches = sw.filter(here).map(s => ({ ...s, status: known[s.id] || s.status }));
    seatBlocks = blocks.filter(here);
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
    if (hall && hallCount > 1 && !OPT.title) $('k-title').textContent += ` · ${hall.name}`;
    if (OPT.heat) {
      $('k-title').textContent += ' · Traffic';
      $('k-heat-legend')?.classList.remove('hidden');
      loadHeat();
      setInterval(loadHeat, HEAT_EVERY);
    }
  }
  start();
})();
