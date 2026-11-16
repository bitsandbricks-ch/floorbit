// Floor plan editor: alignment guides while dragging seat blocks. The dragged blocks snap when their
// edges, middles or seat rows line up with another block, or when they sit at the same distance
// from the blocks left and right (above and below) of them; a line or a spacing marker shows why.
// Hold Alt while dragging to place freely. Works in plan pixels (the wrapper before zoom).
// Classic script sharing one global scope with the other editor/*.js files; the load order
// is in templates/index.html (see static/js/editor/README.md).
'use strict';

const ALIGN_PX = 6;   // screen pixels within which a block snaps to a guide
let alignState = null;

function planBox(r, wr) {
  return { l: (r.left - wr.left) / view.k, t: (r.top - wr.top) / view.k, r: (r.right - wr.left) / view.k, b: (r.bottom - wr.top) / view.k };
}

// What a block lines up by: the box around its seats (not its name label) and the middle of each row
// of seats, running across (ys) or, for a block turned on its side, down (xs).
function blockFeatures(el, wr) {
  const seatsEls = el.querySelectorAll('.seat-block-seat');
  if (!seatsEls.length) return null;
  const box = { l: Infinity, t: Infinity, r: -Infinity, b: -Infinity };
  const ys = new Set(), xs = new Set();
  for (const s of seatsEls) {
    const p = planBox(s.getBoundingClientRect(), wr);
    box.l = Math.min(box.l, p.l); box.t = Math.min(box.t, p.t);
    box.r = Math.max(box.r, p.r); box.b = Math.max(box.b, p.b);
    ys.add(Math.round(p.t + p.b)); xs.add(Math.round(p.l + p.r));   // doubled, rounded to half pixels
  }
  const block = seatBlocks.find(b => b.id === el.dataset.id);
  const sideways = block && Math.round(((block.rotation || 0) % 180) / 90) === 1;
  return { box, rowsY: sideways ? [] : [...ys].map(v => v / 2), rowsX: sideways ? [...xs].map(v => v / 2) : [] };
}

// Called when a drag starts: `ids` are the blocks that move.
function alignBegin(ids) {
  alignState = null;
  const moving = new Set(ids);
  if (!moving.size) return;
  const wr = wrapper.getBoundingClientRect();
  const statics = [];
  let box = null, rowsY = [], rowsX = [];
  for (const el of blocksOverlay.querySelectorAll('.seat-block')) {
    const f = blockFeatures(el, wr);
    if (!f) continue;
    if (moving.has(el.dataset.id)) {
      box = box ? { l: Math.min(box.l, f.box.l), t: Math.min(box.t, f.box.t), r: Math.max(box.r, f.box.r), b: Math.max(box.b, f.box.b) } : f.box;
      rowsY = rowsY.concat(f.rowsY); rowsX = rowsX.concat(f.rowsX);
    } else {
      statics.push(f);
    }
  }
  if (!box || !statics.length) return;
  let layer = $('align-guides');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'align-guides';
    layer.setAttribute('aria-hidden', 'true');
    wrapper.appendChild(layer);
  }
  alignState = { box, rowsY, rowsX, statics, layer, planW: wrapper.offsetWidth, planH: wrapper.offsetHeight };
}

function alignEnd() {
  if (alignState) alignState.layer.innerHTML = '';
  alignState = null;
}

// The best snap on one axis: the smallest distance between a moving line and a still one.
function bestLine(moving, statics, pick, limit) {
  let best = null;
  for (const s of statics) {
    for (const want of pick(s)) {
      for (const have of moving) {
        const d = want - have;
        if (Math.abs(d) <= limit && (!best || Math.abs(d) < Math.abs(best.d))) best = { d, at: want };
      }
    }
  }
  return best;
}

// Equal room on both sides: the nearest block before and after along the axis, overlapping across it.
function bestSpacing(box, statics, horizontal, limit) {
  const [lo, hi, alo, ahi] = horizontal ? ['l', 'r', 't', 'b'] : ['t', 'b', 'l', 'r'];
  let before = null, after = null;
  for (const { box: s } of statics) {
    if (s[ahi] < box[alo] || s[alo] > box[ahi]) continue;
    if (s[hi] <= box[lo] + limit && (!before || s[hi] > before[hi])) before = s;
    if (s[lo] >= box[hi] - limit && (!after || s[lo] < after[lo])) after = s;
  }
  if (!before || !after) return null;
  const size = box[hi] - box[lo];
  const room = (after[lo] - before[hi] - size) / 2;
  if (room <= 0) return null;
  const d = before[hi] + room - box[lo];
  return Math.abs(d) <= limit ? { d, before, after, room } : null;
}

// dxPct, dyPct: how far the drag has moved the blocks, in % of the plan. Returns the snapped offsets
// ({ x, y }, null on an axis that didn't snap) and draws the guides.
function alignMove(dxPct, dyPct, free) {
  const s = alignState;
  if (!s) return { x: null, y: null };
  s.layer.innerHTML = '';
  if (free) return { x: null, y: null };
  const dx = dxPct / 100 * s.planW, dy = dyPct / 100 * s.planH;
  const box = { l: s.box.l + dx, r: s.box.r + dx, t: s.box.t + dy, b: s.box.b + dy };
  const limit = ALIGN_PX / view.k;
  const xs = [box.l, (box.l + box.r) / 2, box.r, ...s.rowsX.map(v => v + dx)];
  const ys = [box.t, (box.t + box.b) / 2, box.b, ...s.rowsY.map(v => v + dy)];
  const lineX = bestLine(xs, s.statics, f => [f.box.l, (f.box.l + f.box.r) / 2, f.box.r, ...f.rowsX], limit);
  const lineY = bestLine(ys, s.statics, f => [f.box.t, (f.box.t + f.box.b) / 2, f.box.b, ...f.rowsY], limit);
  const spaceX = lineX ? null : bestSpacing(box, s.statics, true, limit);
  const spaceY = lineY ? null : bestSpacing(box, s.statics, false, limit);
  const sx = lineX ? lineX.d : spaceX ? spaceX.d : 0;
  const sy = lineY ? lineY.d : spaceY ? spaceY.d : 0;
  const at = { l: box.l + sx, r: box.r + sx, t: box.t + sy, b: box.b + sy };
  const k = view.k;
  const html = [];
  const line = (x1, y1, x2, y2, cls) => html.push(
    `<div class="align-line ${cls}" style="left:${Math.min(x1, x2)}px;top:${Math.min(y1, y2)}px;` +
    `width:${Math.max(Math.abs(x2 - x1), 1 / k)}px;height:${Math.max(Math.abs(y2 - y1), 1 / k)}px"></div>`);
  if (lineX) {
    const near = s.statics.filter(f => [f.box.l, (f.box.l + f.box.r) / 2, f.box.r, ...f.rowsX].some(v => Math.abs(v - lineX.at) < 0.5));
    const top = Math.min(at.t, ...near.map(f => f.box.t)), bottom = Math.max(at.b, ...near.map(f => f.box.b));
    line(lineX.at, top - 8 / k, lineX.at, bottom + 8 / k, 'align-v');
  }
  if (lineY) {
    const near = s.statics.filter(f => [f.box.t, (f.box.t + f.box.b) / 2, f.box.b, ...f.rowsY].some(v => Math.abs(v - lineY.at) < 0.5));
    const left = Math.min(at.l, ...near.map(f => f.box.l)), right = Math.max(at.r, ...near.map(f => f.box.r));
    line(left - 8 / k, lineY.at, right + 8 / k, lineY.at, 'align-h');
  }
  const label = (x, y, room) => html.push(`<div class="align-gap" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) scale(${1 / k})">${
    (Math.round(room / SEAT_PITCH * 4) / 4).toLocaleString()} seats</div>`);
  if (spaceX) {
    const y = (at.t + at.b) / 2;
    line(spaceX.before.r, y, at.l, y, 'align-h align-space');
    line(at.r, y, spaceX.after.l, y, 'align-h align-space');
    label((spaceX.before.r + at.l) / 2, y, spaceX.room);
    label((at.r + spaceX.after.l) / 2, y, spaceX.room);
  }
  if (spaceY) {
    const x = (at.l + at.r) / 2;
    line(x, spaceY.before.b, x, at.t, 'align-v align-space');
    line(x, at.b, x, spaceY.after.t, 'align-v align-space');
    label(x, (spaceY.before.b + at.t) / 2, spaceY.room);
    label(x, (at.b + spaceY.after.t) / 2, spaceY.room);
  }
  s.layer.style.setProperty('--align-k', k);
  s.layer.innerHTML = html.join('');
  return {
    x: lineX || spaceX ? (dx + sx) / s.planW * 100 : null,
    y: lineY || spaceY ? (dy + sy) / s.planH * 100 : null,
  };
}
