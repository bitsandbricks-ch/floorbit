// Floor plan editor: The traffic heatmap layer (seats, switches or both).
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Traffic heatmap ─────────────────────────────────────────────────────────────────────
// Throughput maps to colour on a log scale, so every 10× more traffic is the
// same step along the ramp. Seats and switches use different ranges because a
// switch carries many seats' traffic.
const TRAFFIC_SCALES = {
  seat:   { min: 1e5, max: 1e9 },   // 100 kbps – 1 Gbps (ticks in index.html)
  switch: { min: 1e7, max: 1e10 },  // 10 Mbps – 10 Gbps
};
// Colour-blind-friendly ramp (blue → teal → yellow → orange → crimson); the
// .heat-scale bar in style.css uses the same stops.
const HEAT_STOPS = [
  [0,    [76, 154, 255]],
  [0.30, [46, 196, 182]],
  [0.55, [244, 196, 48]],
  [0.78, [255, 140, 66]],
  [1,    [214, 34, 70]],
];
const HEAT_LUT = (() => {
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let j = 1;
    while (j < HEAT_STOPS.length - 1 && t > HEAT_STOPS[j][0]) j++;
    const [t0, c0] = HEAT_STOPS[j - 1];
    const [t1, c1] = HEAT_STOPS[j];
    const f = (t - t0) / (t1 - t0);
    for (let k = 0; k < 3; k++) lut[i * 3 + k] = c0[k] + (c1[k] - c0[k]) * f;
  }
  return lut;
})();

function heatLevel(bps, scale) {
  if (!(bps > 0)) return 0;
  const t = Math.log10(bps / scale.min) / Math.log10(scale.max / scale.min);
  return Math.min(1, Math.max(0, t));
}
function heatColor(level) {
  const i = Math.round(Math.min(1, Math.max(0, level)) * 255) * 3;
  return `rgb(${HEAT_LUT[i]}, ${HEAT_LUT[i + 1]}, ${HEAT_LUT[i + 2]})`;
}

// Each level writes its own line of the summary under the legend.
const trafficSummaryParts = { seat: '', switch: '' };
function setTrafficSummary(level, text) {
  trafficSummaryParts[level] = text;
  trafficSummary.textContent = [trafficSummaryParts.seat, trafficSummaryParts.switch].filter(Boolean).join('\n');
}

let heatRenderQueued = false;
function scheduleHeatRender() {
  if (heatRenderQueued || !(heatmapVisible || seatHeatmapVisible)) return;
  heatRenderQueued = true;
  requestAnimationFrame(() => {
    heatRenderQueued = false;
    if (heatmapVisible) renderHeatmap();
    if (seatHeatmapVisible) renderSeatHeatmap();
  });
}

let seatHeatmapFailed = false;
async function fetchSeatHeatmapData() {
  try {
    const data = await api('GET', '/api/seats/heatmap');
    seatHeatmapData.seats = data.seats || {};
    seatHeatmapFailed = false;
  } catch (e) {
    seatHeatmapData.seats = {};
    // This runs every refresh; only say so once per outage.
    if (!seatHeatmapFailed) toastError('Could not load seat traffic', e);
    seatHeatmapFailed = true;
  }
}

function prepareCanvas(canvas) {
  const cw = canvas.offsetWidth || wrapper.offsetWidth;
  const ch = canvas.offsetHeight || wrapper.offsetHeight;
  if (!cw || !ch) return null;
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, cw, ch);
  // Screen pixels → canvas pixels (undoes the current zoom)
  const rect = canvas.getBoundingClientRect();
  const scale = rect.width > 0 ? cw / rect.width : 1;
  return { ctx, cw, ch, rect, scale };
}

// Draws a heat field: each point is a soft disc whose centre value is its
// level. Overlapping discs keep the higher value (not the sum), so the colour
// always means "throughput here", never "how many points are close together".
const HEAT_RES = 0.5;   // the field is computed at half resolution and scaled up
const HEAT_FLOOR = 0.14; // idle-but-up still shows as faint blue
let heatScratch = null;
function drawHeatField(ctx, cw, ch, points, radius) {
  if (!points.length) return;
  const w = Math.max(1, Math.round(cw * HEAT_RES));
  const h = Math.max(1, Math.round(ch * HEAT_RES));
  heatScratch = heatScratch || document.createElement('canvas');
  heatScratch.width = w;
  heatScratch.height = h;
  const g = heatScratch.getContext('2d', { willReadFrequently: true });
  g.globalCompositeOperation = 'source-over';
  g.fillStyle = '#000';
  g.fillRect(0, 0, w, h);
  g.globalCompositeOperation = 'lighten';
  const r = radius * HEAT_RES;
  for (const p of points) {
    const x = p.x * HEAT_RES, y = p.y * HEAT_RES;
    const v = Math.round((HEAT_FLOOR + (1 - HEAT_FLOOR) * p.level) * 255);
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0,    `rgb(${v},${v},${v})`);
    grad.addColorStop(0.45, `rgb(${Math.round(v * 0.82)},${Math.round(v * 0.82)},${Math.round(v * 0.82)})`);
    grad.addColorStop(1,    'rgb(0,0,0)');
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  const img = g.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = d[i] / 255;
    if (v < 0.01) { d[i + 3] = 0; continue; }
    const t = Math.max(0, (v - HEAT_FLOOR) / (1 - HEAT_FLOOR));
    const li = Math.round(t * 255) * 3;
    d[i]     = HEAT_LUT[li];
    d[i + 1] = HEAT_LUT[li + 1];
    d[i + 2] = HEAT_LUT[li + 2];
    d[i + 3] = Math.round(Math.min(1, v / HEAT_FLOOR) * (120 + 90 * t));
  }
  g.globalCompositeOperation = 'source-over';
  g.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(heatScratch, 0, 0, cw, ch);
}

function seatThroughput(seatData) {
  const usage = seatData && seatData.resolved ? seatData.port_usage : null;
  if (!usage || usage.status !== 'up') return null;
  return usage.total_bps || 0;
}

function clearSeatTints() {
  for (const el of blocksOverlay.querySelectorAll('.seat-block-seat.heat, .seat-block-seat.heat-none')) {
    el.classList.remove('heat', 'heat-none');
    el.style.removeProperty('--heat');
  }
}

function renderSeatHeatmap() {
  if (!seatHeatmapData.seats) return;
  const c = prepareCanvas(seatHeatCanvas);
  if (!c) return;
  const { ctx, cw, ch, rect, scale } = c;
  const range = TRAFFIC_SCALES.seat;

  const points = [];
  let seatSize = 18;
  let busiest = null;
  let measured = 0;
  for (const el of blocksOverlay.querySelectorAll('.seat-block-seat')) {
    const bps = seatThroughput(seatHeatmapData.seats[el.dataset.seatNumber]);
    el.classList.toggle('heat', bps != null);
    el.classList.toggle('heat-none', bps == null);
    if (bps == null) { el.style.removeProperty('--heat'); continue; }
    const level = heatLevel(bps, range);
    el.style.setProperty('--heat', heatColor(level));
    const r = el.getBoundingClientRect();
    seatSize = r.width * scale;
    points.push({ x: (r.left + r.width / 2 - rect.left) * scale, y: (r.top + r.height / 2 - rect.top) * scale, level });
    measured++;
    if (!busiest || bps > busiest.bps) busiest = { name: el.dataset.seatNumber, bps };
  }
  // Legacy individual seats get the glow only.
  for (const el of seatsOverlay.querySelectorAll('[data-seat-number]')) {
    const bps = seatThroughput(seatHeatmapData.seats[el.dataset.seatNumber]);
    if (bps == null) continue;
    const r = el.getBoundingClientRect();
    points.push({ x: (r.left + r.width / 2 - rect.left) * scale, y: (r.top + r.height / 2 - rect.top) * scale,
                  level: heatLevel(bps, range) });
    measured++;
    if (!busiest || bps > busiest.bps) busiest = { name: el.dataset.seatNumber, bps };
  }

  drawHeatField(ctx, cw, ch, points, Math.max(14, seatSize * 1.7));
  setTrafficSummary('seat', measured
    ? `${measured} seat${measured === 1 ? '' : 's'} with traffic data · busiest ${busiest.name} at ${fmtBps(busiest.bps)}`
    : 'No seat has traffic data yet. Seats need an IP in the seat mapping and LibreNMS must find their port.');
}

function renderHeatmap() {
  const c = prepareCanvas(heatCanvas);
  if (!c) return;
  const { ctx, cw, ch, rect, scale } = c;
  const range = TRAFFIC_SCALES.switch;

  const hasTraffic = sw => sw.status !== 'offline' && portStats[sw.id] && portStats[sw.id].total_traffic_bps != null;
  const visible = switches.filter(sw =>
    sw.placed !== false && sw.x != null && !getDeviceSetting(sw.id, 'excludeHeatmap') && hasTraffic(sw));

  // Tint each switch's card with its level and show its throughput.
  for (const el of overlay.querySelectorAll('.switch-marker')) {
    const sw = switches.find(s => s.id === el.dataset.id);
    const excluded = !sw || getDeviceSetting(sw.id, 'excludeHeatmap');
    const live = !excluded && hasTraffic(sw);
    el.classList.toggle('no-heat', !!excluded);
    el.classList.toggle('heat-none', !excluded && !live);
    const rate = el.querySelector('.switch-heat-rate');
    if (live) {
      const bps = portStats[sw.id].total_traffic_bps;
      el.style.setProperty('--heat', heatColor(heatLevel(bps, range)));
      if (rate) rate.textContent = fmtBps(bps);
    } else {
      el.style.removeProperty('--heat');
      if (rate) rate.textContent = sw && sw.status === 'offline' ? 'offline' : 'no data';
    }
  }

  const points = visible.map(sw => {
    let x, y;
    const pin = overlay.querySelector(`[data-id="${CSS.escape(sw.id)}"] .switch-pin`);
    if (pin) {
      const pr = pin.getBoundingClientRect();
      x = (pr.left + pr.width / 2 - rect.left) * scale;
      y = (pr.top + pr.height * 5 / 18 - rect.top) * scale; // pin head centre
    } else {
      x = (sw.x / 100) * cw;
      y = (sw.y / 100) * ch;
    }
    return { x, y, level: heatLevel(portStats[sw.id].total_traffic_bps, range) };
  });
  // With seats on as well, keep the switch glow smaller so the seat tiles stay readable.
  drawHeatField(ctx, cw, ch, points, Math.min(cw, ch) * (seatHeatmapVisible ? 0.09 : 0.13));

  const busiest = visible.reduce((a, sw) =>
    (!a || portStats[sw.id].total_traffic_bps > portStats[a.id].total_traffic_bps ? sw : a), null);
  setTrafficSummary('switch', busiest
    ? `${visible.length} switch${visible.length === 1 ? '' : 'es'} reporting · busiest ${busiest.name} at ${fmtBps(portStats[busiest.id].total_traffic_bps)}`
    : 'No switch has reported traffic yet. Switches need to be online in LibreNMS.');
}
