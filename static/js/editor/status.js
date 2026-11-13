// Floor plan editor: Switch list filter, status refresh from LibreNMS, top bar stats.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Switch list filter & status chips ────────────────────────────────────────────────────
switchSearch.addEventListener('input', () => renderSidebar());

function setStatusFilter(status) {
  statusFilter = status;
  statusChips.forEach(c => c.classList.toggle('active', status !== 'all' && c.dataset.status === status));
  renderOverlay();
  renderSidebar();
  markSelection();
}
statusChips.forEach(chip => chip.addEventListener('click', () => {
  const s = chip.dataset.status;
  setStatusFilter(s === statusFilter ? 'all' : s);
}));
listFilterClear.addEventListener('click', () => setStatusFilter('all'));
// ── Refresh status ─────────────────────────────────────────────────────────────────────
async function doRefreshAll() {
  if (isRefreshing) return;
  isRefreshing = true;
  btnRefreshAll.classList.add('is-busy');
  try {
    const placed = switches.filter(s => s.placed !== false);
    let failures = 0;
    await Promise.all(placed.map(async (sw) => {
      try {
        const data = await api('GET', `/api/switches/${sw.id}/status`);
        sw.status = data.status;
        storePortStats(sw.id, data);
      } catch {
        failures++;
      }
    }));

    const allFailed = placed.length > 0 && failures === placed.length;
    if (allFailed && !lastRefreshFailed) toast('Status refresh failed. Is the server reachable?', { type: 'error' });
    lastRefreshFailed = allFailed;
    if (!allFailed) lastRefreshAt = Date.now();
    updateLastUpdated();

    renderOverlay();
    renderSidebar();
    markSelection();
    updateHeroStats();
    if (heatmapVisible) renderHeatmap();
    saveStatusCache();

    if (seatHeatmapVisible) {
      await fetchSeatHeatmapData();
      renderSeatHeatmap();
    }
  } finally {
    isRefreshing = false;
    btnRefreshAll.classList.remove('is-busy');
  }
}

function updateLastUpdated() {
  if (!config.librenms_enabled) return;
  if (lastRefreshFailed) {
    lastUpdatedEl.textContent = 'Refresh failed';
    lastUpdatedEl.className = 'last-updated error';
    return;
  }
  if (!lastRefreshAt) return;
  const secs = Math.round((Date.now() - lastRefreshAt) / 1000);
  lastUpdatedEl.textContent = secs < 5 ? 'Updated just now'
    : secs < 60 ? `Updated ${secs}s ago`
    : `Updated ${Math.round(secs / 60)} min ago`;
  lastUpdatedEl.className = 'last-updated' + (secs > 60 ? ' stale' : '');
}
setInterval(updateLastUpdated, 1000);

function saveStatusCache() {
  const statuses = {};
  for (const sw of switches) if (sw.status) statuses[sw.id] = sw.status;
  setCache({ portStats: { ...portStats }, statuses });
}

btnRefreshAll.addEventListener('click', async () => {
  if (isRefreshing) return;
  btnRefreshAll.disabled = true;
  try { await doRefreshAll(); } finally { btnRefreshAll.disabled = false; }
});

// Auto-refresh (skipped while the tab is hidden)
setInterval(() => {
  if (!document.hidden) doRefreshAll().catch(() => {});
}, REFRESH_INTERVAL);
// ── Top bar stats ──────────────────────────────────────────────────────────────────────
function updateHeroStats() {
  const placed  = switches.filter(s => s.placed !== false);
  const online  = placed.filter(s => s.status === 'online').length;
  const offline = placed.filter(s => s.status === 'offline').length;
  heroTotal.textContent   = placed.length;
  heroOnline.textContent  = online;
  heroOffline.textContent = offline;
  heroUnknown.textContent = placed.length - online - offline;
  document.querySelector('.chip-offline').classList.toggle('has-items', offline > 0);
}
