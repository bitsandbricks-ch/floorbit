// Floor plan editor: Layer toggles and the grid.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Layers ────────────────────────────────────────────────────────────────────────────
function setLayerButton(btn, on) {
  btn.classList.toggle('heatmap-on', on);
  btn.setAttribute('aria-pressed', String(on));
}

// Traffic heatmap: one layer, shown per seat (the seat's switch port), per
// switch (all its ports) or both at once. heatmapVisible / seatHeatmapVisible
// say which canvas is live, so the rest of the file can keep checking them.
let trafficOn = false;
let trafficLevel = 'seat';   // 'seat' | 'switch' | 'both'
const TRAFFIC_LEVELS = ['seat', 'switch', 'both'];

function setTrafficLayer(on, level = trafficLevel) {
  trafficOn = on;
  trafficLevel = TRAFFIC_LEVELS.includes(level) ? level : 'seat';
  heatmapVisible = on && trafficLevel !== 'seat';
  seatHeatmapVisible = on && trafficLevel !== 'switch';

  setLayerButton(btnTraffic, on);
  trafficOptions.classList.toggle('hidden', !on);
  for (const b of trafficLevelSeg.querySelectorAll('button[data-level]')) {
    const active = b.dataset.level === trafficLevel;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  }
  trafficLegendSeat.classList.toggle('hidden', trafficLevel === 'switch');
  trafficLegendSwitch.classList.toggle('hidden', trafficLevel === 'seat');
  trafficNodataLabel.textContent = { seat: 'No data or port down', switch: 'Offline or no data',
                                     both: 'Offline, no data or port down' }[trafficLevel];
  trafficSummaryParts.seat = trafficSummaryParts.switch = '';
  trafficSummary.textContent = '';
  writeJSON('layer-traffic', { on, level: trafficLevel });

  heatCanvas.style.display = heatmapVisible ? 'block' : 'none';
  seatHeatCanvas.style.display = seatHeatmapVisible ? 'block' : 'none';
  wrapper.classList.toggle('heat-seat', seatHeatmapVisible);
  wrapper.classList.toggle('heat-switch', heatmapVisible);
  wrapper.classList.toggle('heat-both', heatmapVisible && seatHeatmapVisible);
  if (!seatHeatmapVisible) clearSeatTints();

  if (heatmapVisible) renderHeatmap();
  if (seatHeatmapVisible) {
    if (seatHeatmapData.seats) renderSeatHeatmap();
    fetchSeatHeatmapData().then(() => { if (seatHeatmapVisible) renderSeatHeatmap(); });
  }
}

function setGridVisible(on) {
  gridVisible = on;
  setLayerButton(btnGrid, on);
  gridEl.classList.toggle('hidden', !on);
  writeJSON('layer-grid', on);
  updateGrid();
}

function setLabelsAlways(on) {
  wrapper.classList.toggle('labels-always', on);
  setLayerButton(btnLabels, on);
  writeJSON('layer-labels', on);
}
function restoreLayerPrefs() {
  setSnap(readJSON('snapEnabled', true));
  setLabelsAlways(readJSON('layer-labels', false));
  setGridVisible(readJSON('layer-grid', true));
  // Older builds had two separate heatmap toggles; carry their state over.
  let traffic = readJSON('layer-traffic', null);
  if (!traffic) {
    if (readJSON('layer-seat-heatmap', false)) traffic = { on: true, level: 'seat' };
    else if (readJSON('layer-heatmap', false)) traffic = { on: true, level: 'switch' };
  }
  setTrafficLayer(!!traffic?.on, traffic?.level);
}

btnGrid.addEventListener('click', () => setGridVisible(!gridVisible));
btnTraffic.addEventListener('click', () => setTrafficLayer(!trafficOn));
trafficLevelSeg.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-level]');
  if (b && b.dataset.level !== trafficLevel) setTrafficLayer(true, b.dataset.level);
});
btnLabels.addEventListener('click', () => setLabelsAlways(!wrapper.classList.contains('labels-always')));
// ── Grid ──────────────────────────────────────────────────────────────────────────
// The grid lives behind the floor plan and follows pan and zoom. Its finest
// visible step is picked from GRID_STEPS (in % of the floor plan, the same unit
// as snapping) so lines never get denser than GRID_MIN_PX; every fifth-ish step
// is a stronger major line. The finest step at high zoom is GRID_SNAP, so
// snapped items sit exactly on lines.
let gridVisible = true;
const GRID_STEPS = [GRID_SNAP, 1, 2.5, 5, 10, 25, 50];
const GRID_MIN_PX = 10;

function updateGrid() {
  if (!gridVisible) return;
  const w = wrapper.offsetWidth * view.k;
  const h = wrapper.offsetHeight * view.k;
  if (!w || !h) return;
  const pxPerPercent = Math.min(w, h) / 100;
  let i = GRID_STEPS.findIndex(step => step * pxPerPercent >= GRID_MIN_PX);
  if (i < 0) i = GRID_STEPS.length - 1;
  const minor = GRID_STEPS[i];
  const major = GRID_STEPS[Math.min(i + 2, GRID_STEPS.length - 1)];
  // Fade the minor lines in as they open up, so zooming doesn't make them pop.
  const fade = Math.min(1, Math.max(0, (minor * pxPerPercent - GRID_MIN_PX) / GRID_MIN_PX));
  const st = gridEl.style;
  st.setProperty('--grid-minor-w', `${minor * w / 100}px`);
  st.setProperty('--grid-minor-h', `${minor * h / 100}px`);
  st.setProperty('--grid-major-w', `${major * w / 100}px`);
  st.setProperty('--grid-major-h', `${major * h / 100}px`);
  st.setProperty('--grid-x', `${view.x}px`);
  st.setProperty('--grid-y', `${view.y}px`);
  st.setProperty('--grid-minor-pct', `${Math.round(6 + fade * 10)}%`);
}
