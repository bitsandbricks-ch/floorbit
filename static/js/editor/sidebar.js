// Floor plan editor: Sidebar: collapsible sections, seat numbering, search, tool selection, NetBox sync.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

// ── Collapsible sections ───────────────────────────────────────────────────────
function initCollapsibleSections() {
  document.querySelectorAll('.collapsible-section').forEach(section => {
    const name = section.dataset.section;
    const header = section.querySelector('.section-header');
    let saved = null;
    try { saved = localStorage.getItem(`section-${name}`); } catch { /* ignore */ }
    if (saved === 'collapsed') section.classList.add('collapsed');
    else if (saved === 'expanded') section.classList.remove('collapsed');

    header.setAttribute('role', 'button');
    header.setAttribute('tabindex', '0');
    const toggle = () => {
      const isCollapsed = section.classList.toggle('collapsed');
      header.setAttribute('aria-expanded', String(!isCollapsed));
      try { localStorage.setItem(`section-${name}`, isCollapsed ? 'collapsed' : 'expanded'); } catch { /* ignore */ }
    };
    header.setAttribute('aria-expanded', String(!section.classList.contains('collapsed')));
    header.addEventListener('click', toggle);
    header.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });
}
// ── Seat numbering ─────────────────────────────────────────────────────────────────
// Returns the seat numbers of a block in render order (row by row).
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
// ── Universal search ───────────────────────────────────────────────────────────────
let searchDebounceTimer = null;
let searchActiveIndex = -1;

function renderUniversalSearchResults() {
  const query = universalSearch.value.trim().toLowerCase();
  searchActiveIndex = -1;
  if (!query) { searchResults.innerHTML = ''; return; }

  let html = '';
  const switchMatches = switches
    .filter(s => s.placed !== false && s.name.toLowerCase().includes(query))
    .slice(0, 10);

  if (switchMatches.length) {
    html += '<div class="search-result-group"><div class="search-result-group-title">Switches</div>';
    for (const sw of switchMatches) {
      html += `
        <div class="search-result-item" data-type="switch" data-id="${escHtml(sw.id)}">
          <span class="switch-item-glyph status-${escHtml(statusBucket(sw.status))}">${statusGlyph(sw.status)}</span>
          <span class="search-result-item-name">${escHtml(sw.name)}</span>
          <span class="search-result-item-sub">${escHtml(sw.status || '')}</span>
        </div>`;
    }
    html += '</div>';
  }

  const seatMatches = [];
  for (const block of seatBlocks) {
    for (const { number } of blockSeatNumbers(block)) {
      if (number.toLowerCase().includes(query)) {
        const user = seatMappings[number]?.username || '';
        seatMatches.push({ blockId: block.id, seatNumber: number, name: number, sub: user || block.name || 'block' });
      }
      const seatData = seatMappings[number];
      if (seatData && seatData.username && seatData.username.toLowerCase().includes(query)) {
        seatMatches.push({ blockId: block.id, seatNumber: number, name: seatData.username, sub: number });
      }
      // IPs and MACs are only in seatMappings for roles with seats.view (data.js).
      for (const key of ['ip_address', 'mac_address']) {
        const value = seatData && seatData[key];
        const hit = key === 'ip_address' ? String(value || '').toLowerCase().includes(query)
          : value && macKey(query).length >= 4 && macKey(value).includes(macKey(query));
        if (value && hit) {
          seatMatches.push({ blockId: block.id, seatNumber: number, name: value, sub: `${number}${seatData.username ? ' · ' + seatData.username : ''}` });
        }
      }
    }
  }
  const uniqueSeatMatches = seatMatches
    .filter((item, index, self) => index === self.findIndex(t => t.seatNumber === item.seatNumber && t.name === item.name))
    .slice(0, 10);

  if (uniqueSeatMatches.length) {
    html += '<div class="search-result-group"><div class="search-result-group-title">Seats</div>';
    for (const seat of uniqueSeatMatches) {
      html += `
        <div class="search-result-item" data-type="seat-block" data-block-id="${escHtml(seat.blockId)}" data-seat-number="${escHtml(seat.seatNumber)}">
          <span class="search-result-item-type">Seat</span>
          <span class="search-result-item-name">${escHtml(seat.name)}</span>
          <span class="search-result-item-sub">${escHtml(seat.sub)}</span>
        </div>`;
    }
    html += '</div>';
  }

  searchResults.innerHTML = html || '<div class="search-no-results">No matches</div>';
  bindSearchResults();
  if (looksLikeAddress(universalSearch.value)) findOnNetwork(universalSearch.value.trim());
}

function bindSearchResults() {
  searchResults.querySelectorAll('.search-result-item:not([data-bound])').forEach(item => {
    item.dataset.bound = '1';
    item.addEventListener('click', () => handleSearchResultClick(item));
  });
}

// A full IP or MAC is also looked up on the network (issue #14): through the ARP table when no seat
// source knows it, and with the switch port it is plugged into. Needs seats.view; others get a 403.
const macKey = (v) => String(v).toLowerCase().replace(/[\s:.\-]/g, '');
const IP_RE = /^(\d{1,3}\.){3}\d{1,3}$|^[0-9a-f:]*:[0-9a-f:]+$/i;
function looksLikeAddress(q) {
  const v = q.trim();
  return IP_RE.test(v) || /^[0-9a-f]{12}$/i.test(macKey(v));
}

let networkSearchSeq = 0;
async function findOnNetwork(query) {
  const seq = ++networkSearchSeq;
  let body;
  try { body = await api('GET', `/api/seats/find?q=${encodeURIComponent(query)}`); } catch { return; }
  if (seq !== networkSearchSeq || universalSearch.value.trim() !== query) return;
  const hits = (body.results || []).filter(r => r.port);
  if (!hits.length) return;
  let html = '<div class="search-result-group"><div class="search-result-group-title">On the network</div>';
  for (const r of hits) {
    const where = `${r.switch || '?'} ${r.port}`;
    html += `
      <div class="search-result-item" data-type="network" data-seat-number="${escHtml(r.seat || '')}"
           data-switch-id="${escHtml(r.switch_id || '')}">
        <span class="search-result-item-type">${r.seat ? 'Seat' : 'Port'}</span>
        <span class="search-result-item-name">${escHtml(r.seat ? `${r.seat}${r.username ? ' · ' + r.username : ''}` : where)}</span>
        <span class="search-result-item-sub">${escHtml(r.seat ? where : (body.arp || r.ip || r.mac || ''))}</span>
      </div>`;
  }
  html += '</div>';
  searchResults.querySelector('.search-no-results')?.remove();
  searchResults.insertAdjacentHTML('afterbegin', html);
  bindSearchResults();
}

// Light up the switch a found seat hangs on for a few seconds, so the eye finds both.
function flashSwitch(switchId) {
  const marker = switchId && overlay.querySelector(`[data-id="${CSS.escape(switchId)}"]`);
  if (!marker) return;
  marker.classList.remove('search-hit');
  void marker.offsetWidth;   // restart the animation
  marker.classList.add('search-hit');
  setTimeout(() => marker.classList.remove('search-hit'), 6000);
}

function handleSearchResultClick(item) {
  const type = item.dataset.type;
  if (type === 'switch') {
    selectSwitch(item.dataset.id);
    focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(item.dataset.id)}"]`));
  } else if (type === 'seat-block') {
    flashSwitchOnResolve = true;
    showBlockSeatDetail(item.dataset.seatNumber);
    focusOnItem(blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(item.dataset.seatNumber)}"]`));
  } else if (type === 'network') {
    if (item.dataset.seatNumber) {
      showBlockSeatDetail(item.dataset.seatNumber);
      focusOnItem(blocksOverlay.querySelector(`[data-seat-number="${CSS.escape(item.dataset.seatNumber)}"]`));
    } else if (item.dataset.switchId) {
      selectSwitch(item.dataset.switchId);
      focusOnItem(overlay.querySelector(`[data-id="${CSS.escape(item.dataset.switchId)}"]`));
    }
    flashSwitch(item.dataset.switchId);
  }
  universalSearch.value = '';
  searchResults.innerHTML = '';
  universalSearch.blur();
}

universalSearch.addEventListener('input', () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(renderUniversalSearchResults, 150);
});
universalSearch.addEventListener('keydown', (e) => {
  const items = [...searchResults.querySelectorAll('.search-result-item')];
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!items.length) return;
    e.preventDefault();
    searchActiveIndex = (searchActiveIndex + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items.forEach((el, i) => el.classList.toggle('kbd-active', i === searchActiveIndex));
    items[searchActiveIndex].scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'Enter') {
    const target = items[searchActiveIndex] || items[0];
    if (target) handleSearchResultClick(target);
  } else if (e.key === 'Escape') {
    universalSearch.value = '';
    searchResults.innerHTML = '';
    universalSearch.blur();
  }
});
// ── Tool selection ───────────────────────────────────────────────────────────────────
const TOOL_HINTS = {
  'add-switch': 'Click on the map to place a switch · Esc to cancel',
  'add-block':  'Click on the map to place a seat block · Esc to cancel',
};

function setTool(tool) {
  currentTool = tool;
  toolSelect.classList.toggle('active', tool === 'select');
  toolAddSwitch.classList.toggle('active', tool === 'add-switch');
  toolAddBlock.classList.toggle('active', tool === 'add-block');
  wrapper.dataset.tool = tool;
  toolHint.textContent = TOOL_HINTS[tool] || '';
  toolHint.classList.toggle('hidden', !TOOL_HINTS[tool]);
  if (tool !== 'select') deselectAll();
}

toolSelect.addEventListener('click', () => setTool('select'));
toolAddSwitch.addEventListener('click', () => setTool('add-switch'));
toolAddBlock.addEventListener('click', () => setTool('add-block'));

function setSnap(on) {
  snapEnabled = on;
  btnSnap.classList.toggle('active', on);
  btnSnap.setAttribute('aria-pressed', String(on));
  writeJSON('snapEnabled', on);
}
btnSnap.addEventListener('click', () => setSnap(!snapEnabled));
// ── NetBox sync ──────────────────────────────────────────────────────────────────────
btnSync.addEventListener('click', async () => {
  btnSync.disabled = true;
  btnSync.classList.add('is-busy');
  syncInfo.classList.add('hidden');
  try {
    const synced = await api('POST', '/api/switches/sync');
    // Keep the live status we already know about
    const statusById = Object.fromEntries(switches.map(s => [s.id, s.status]));
    const manual = switches.filter(s => s.source === 'manual');
    switches = [...inHall(synced).filter(s => s.source !== 'manual')
      .map(s => ({ ...s, status: statusById[s.id] || s.status })), ...manual];
    renderAll();
    const unplaced = switches.filter(s => !s.placed && s.source !== 'manual').length;
    syncInfo.textContent = `Synced ${synced.length} device(s), ${unplaced} not on the map yet`;
    syncInfo.classList.remove('hidden');
    toast(`NetBox sync done: ${synced.length} device(s)`, { type: 'success' });
  } catch (e) {
    syncInfo.textContent = 'Sync failed: ' + e.message;
    syncInfo.classList.remove('hidden');
    toastError('NetBox sync failed', e);
  } finally {
    btnSync.disabled = false;
    btnSync.classList.remove('is-busy');
  }
});
