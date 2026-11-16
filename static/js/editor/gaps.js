// Floor plan editor: gaps inside a seat block. Room in every row after a column (fiber rolls),
// or a lane after a row (a switch between two rows). Seat numbers carry on across a gap. The rules
// match floorbit/seat_gaps.py: { after, size } with "after" a column or row from the top left of
// the block as drawn, "size" in seats.
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

const GAP_MIN = 0.25, GAP_MAX = 20;
const SEAT_PITCH = 20;   // px: an 18 px seat and the 2 px between seats (style.css .seat-block-seat)

// How much room follows column (or row) `after` (1-based), in seats; 0 for none.
function gapAfter(gaps, after) {
  return (gaps || []).filter(g => Number(g.after) === after).reduce((n, g) => n + Number(g.size), 0);
}

// The spacer drawn for a gap: the flex gap already adds 2 px, so the spacer is a pitch less that.
function gapSpacer(size, dir) {
  const px = Math.max(0, size * SEAT_PITCH - 2);
  return `<div class="seat-gap seat-gap-${dir}" style="${dir === 'col' ? 'width' : 'height'}:${px}px" aria-hidden="true"></div>`;
}

function cleanGaps(list, count) {
  const merged = new Map();
  for (const g of list) {
    const after = Math.round(Number(g.after)), size = Math.min(GAP_MAX, Math.max(GAP_MIN, Number(g.size) || 1));
    if (after >= 1 && after < count) merged.set(after, Math.round(size * 100) / 100);
  }
  return [...merged.entries()].sort((a, b) => a[0] - b[0]).map(([after, size]) => ({ after, size }));
}

// Saves a block's gaps with undo, then redraws and refreshes the inspector.
async function setBlockGaps(blockId, kind, list) {
  const block = seatBlocks.find(b => b.id === blockId);
  if (!block) return;
  const key = kind === 'row' ? 'row_gaps' : 'col_gaps';
  const before = { [key]: block[key] || [] };
  const patch = { [key]: cleanGaps(list, kind === 'row' ? block.rows : block.cols) };
  try {
    await updateBlock(blockId, patch);
    pushHistory({
      label: kind === 'row' ? 'change the lanes between rows' : 'change the gaps in the rows',
      undo: () => updateBlock(resolveId(blockId), before), redo: () => updateBlock(resolveId(blockId), patch),
    });
    renderAll();
    if (selectedType === 'block' && selectedId === blockId) fillGapEditor(block);
  } catch (err) {
    toastError('Could not change the gaps', err);
  }
}

// Where a seat sits in its block as drawn: { block, row, col } (0-based), or null.
function seatPlace(seatNumber) {
  for (const block of seatBlocks) {
    const i = blockSeatNumbers(block).findIndex(s => s.number === seatNumber);
    if (i >= 0) return { block, row: Math.floor(i / block.cols), col: i % block.cols };
  }
  return null;
}

// Right-click entries on a seat (menus.js): a gap after it in every row, a lane after its row.
function gapMenuEntries(seatNumber) {
  const at = seatPlace(seatNumber);
  if (!at) return [];
  const { block, row, col } = at;
  const out = [];
  if (col < block.cols - 1) {
    const has = gapAfter(block.col_gaps, col + 1) > 0;
    out.push({ label: has ? 'Remove the gap after this seat' : 'Gap after this seat (every row)',
      run: () => setBlockGaps(block.id, 'col', has ? (block.col_gaps || []).filter(g => g.after !== col + 1)
                                                    : [...(block.col_gaps || []), { after: col + 1, size: 1 }]) });
  }
  if (row < block.rows - 1) {
    const has = gapAfter(block.row_gaps, row + 1) > 0;
    out.push({ label: has ? 'Remove the lane after this row' : 'Lane after this row (for a switch)',
      run: () => setBlockGaps(block.id, 'row', has ? (block.row_gaps || []).filter(g => g.after !== row + 1)
                                                    : [...(block.row_gaps || []), { after: row + 1, size: 2 }]) });
  }
  return out;
}

// ── The Gaps section of the block inspector ─────────────────────────────────────────
function gapRowHtml(kind, gap, count) {
  return `<div class="gap-row" data-kind="${kind}">
    <label class="gap-field"><span>${kind === 'row' ? 'After row' : 'After column'}</span>
      <input class="modal-input input-compact" type="number" data-gap="after" min="1" max="${count - 1}" step="1" value="${gap.after}" /></label>
    <label class="gap-field"><span>${kind === 'row' ? 'Height' : 'Width'} (seats)</span>
      <input class="modal-input input-compact" type="number" data-gap="size" min="${GAP_MIN}" max="${GAP_MAX}" step="0.5" value="${gap.size}" /></label>
    <button type="button" class="btn btn-ghost btn-icon gap-remove" title="Remove this gap" aria-label="Remove this gap">✕</button>
  </div>`;
}

function fillGapEditor(block) {
  const section = $('block-gaps-section');
  if (!section) return;
  section.dataset.block = block.id;
  for (const kind of ['col', 'row']) {
    const count = kind === 'row' ? block.rows : block.cols;
    const gaps = (kind === 'row' ? block.row_gaps : block.col_gaps) || [];
    $(`gap-list-${kind}`).innerHTML = gaps.map(g => gapRowHtml(kind, g, count)).join('');
    $(`gap-add-${kind}`).disabled = count < 2;
  }
}

function readGaps(kind) {
  return [...$(`gap-list-${kind}`).querySelectorAll('.gap-row')].map(r => ({
    after: Number(r.querySelector('[data-gap="after"]').value),
    size: Number(r.querySelector('[data-gap="size"]').value),
  }));
}

if ($('block-gaps-section')) {
  const section = $('block-gaps-section');
  const blockOf = () => seatBlocks.find(b => b.id === section.dataset.block);
  for (const kind of ['col', 'row']) {
    $(`gap-add-${kind}`).addEventListener('click', () => {
      const block = blockOf();
      if (!block) return;
      const count = kind === 'row' ? block.rows : block.cols;
      const taken = new Set(readGaps(kind).map(g => g.after));
      // The middle first, then the nearest free spot.
      const mid = Math.max(1, Math.floor(count / 2));
      const free = [...Array(count - 1).keys()].map(i => i + 1).sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid))
        .find(n => !taken.has(n));
      if (free === undefined) return;
      setBlockGaps(block.id, kind, [...readGaps(kind), { after: free, size: kind === 'row' ? 2 : 1 }]);
    });
    const list = $(`gap-list-${kind}`);
    list.addEventListener('change', () => { const b = blockOf(); if (b) setBlockGaps(b.id, kind, readGaps(kind)); });
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('.gap-remove');
      const b = blockOf();
      if (!btn || !b) return;
      btn.closest('.gap-row').remove();
      setBlockGaps(b.id, kind, readGaps(kind));
    });
  }
}
