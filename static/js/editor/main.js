// Floor plan editor: Start-up. Loaded last: everything above must be defined before init() runs.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Init ───────────────────────────────────────────────────────────────────────────
async function init() {
  restoreView();
  restoreLayerPrefs();
  initCollapsibleSections();

  const results = await Promise.allSettled([
    api('GET', '/api/config'),
    loadSwitches(),
    loadSeats(),
    loadSeatMappings(),
    loadSeatBlocks(),
  ]);
  if (results[0].status === 'fulfilled') config = results[0].value;
  const failed = results.filter(r => r.status === 'rejected');
  if (failed.length) toastError('Could not load all data', failed[0].reason);

  applyConfig();

  const cachedStatus = getCache();
  if (cachedStatus) applyCachedStatus(cachedStatus);

  renderAll();
  doRefreshAll().catch(() => {});
  loadIncidentMarkers();
  loadPortInfo();
}

function applyCachedStatus(cache) {
  for (const [id, stats] of Object.entries(cache.portStats || {})) portStats[id] = stats;
  for (const sw of switches) {
    if (cache.statuses && cache.statuses[sw.id]) sw.status = cache.statuses[sw.id];
  }
}

function applyConfig() {
  syncSection.classList.toggle('hidden', !config.netbox_enabled);
  if (!config.librenms_enabled) {
    lastUpdatedEl.textContent = 'LibreNMS not configured';
    lastUpdatedEl.title = 'Set LIBRENMS_URL and LIBRENMS_TOKEN to see live switch status';
  }
}

// ── Bootstrap ───────────────────────────────────────────────────────────────────────────
// The floor plan resizes with the window and when an inspector opens. Registered here, not
// in layers.js: an observer fires as soon as it observes, possibly before heatmap.js loaded.
if (window.ResizeObserver) {
  new ResizeObserver(() => { updateGrid(); scheduleHeatRender(); }).observe(wrapper);
}

updateHistoryButtons();
init();
