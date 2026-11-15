// Speedtest at the seat (issue #99): latency, download and upload to the Floorbit server, run from
// the seat's help page. The browser measures; the server only sends and swallows bytes. Only the
// numbers are sent back. See docs/speedtest.md.
(function () {
  'use strict';
  var me = document.currentScript;
  var base = me.dataset.base;
  var k = encodeURIComponent(me.dataset.k || '');
  var button = document.getElementById('speed-run');
  var note = document.getElementById('speed-note');
  var MB = 1024 * 1024;
  var MAX_UP = 24 * MB;
  var PHASE_MS = 6000;   // time spent on download, then on upload
  var PHASE_BYTES = 400 * MB;   // or until this much moved: 3 s on gigabit is plenty, and spares the budget
  var AIM_MS = 1500;     // each request should take about this long

  function url(what, extra) { return base + what + '?k=' + k + (extra || ''); }
  function now() { return performance.now(); }
  function show(id, value) { document.getElementById('speed-' + id).textContent = value; }
  function mbps(bytes, ms) { return bytes * 8 / (ms / 1000) / 1e6; }
  function fmt(n) { return n >= 100 ? Math.round(n).toString() : n.toFixed(1); }

  async function check(resp) {
    if (resp.ok) return resp;
    var body = await resp.json().catch(function () { return {}; });
    throw new Error(body.error || 'HTTP ' + resp.status);
  }

  async function latency() {
    var times = [];
    for (var i = 0; i < 11; i++) {
      var t0 = now();
      await check(await fetch(url('ping', '&n=' + i), { cache: 'no-store' }));
      if (i > 0) times.push(now() - t0);   // the first one sets up the connection
    }
    var sorted = times.slice().sort(function (a, b) { return a - b; });
    var jitter = 0;
    for (var j = 1; j < times.length; j++) jitter += Math.abs(times[j] - times[j - 1]);
    return { ping: sorted[Math.floor(sorted.length / 2)], jitter: jitter / (times.length - 1) };
  }

  async function downOnce(size) {
    var t0 = now();
    var resp = await check(await fetch(url('down', '&bytes=' + size), { cache: 'no-store' }));
    var reader = resp.body.getReader();
    var got = 0;
    for (;;) {
      var part = await reader.read();
      if (part.done) break;
      got += part.value.length;
    }
    return { bytes: got, ms: now() - t0 };
  }

  function randomBlob(size) {
    var block = new Uint8Array(MB);
    for (var i = 0; i < MB; i += 65536) crypto.getRandomValues(block.subarray(i, i + 65536));
    var parts = [];
    for (var n = 0; n < size; n += MB) parts.push(n + MB <= size ? block : block.subarray(0, size - n));
    return new Blob(parts);
  }

  async function upOnce(size) {
    var blob = randomBlob(size);
    var t0 = now();
    await check(await fetch(url('up'), { method: 'POST', body: blob, cache: 'no-store',
      headers: { 'Content-Type': 'application/octet-stream' } }));
    return { bytes: size, ms: now() - t0 };
  }

  // Requests sized to take about AIM_MS each, for PHASE_MS; the first one only finds the size.
  async function phase(once, cap, id) {
    var size = MB, bytes = 0, ms = 0, start = now(), first = true;
    while (now() - start < PHASE_MS && bytes < PHASE_BYTES) {
      var r = await once(size);
      if (!first) { bytes += r.bytes; ms += r.ms; show(id, fmt(mbps(bytes, ms))); }
      first = false;
      var rate = r.bytes / Math.max(r.ms, 1);
      size = Math.max(MB, Math.min(cap, PHASE_BYTES - bytes, Math.round(rate * AIM_MS / MB) * MB));
    }
    return ms ? mbps(bytes, ms) : null;
  }

  async function run() {
    button.disabled = true;
    var label = button.textContent;
    button.textContent = me.dataset.running;
    note.textContent = '';
    note.className = 'note';
    ['down', 'up', 'ping'].forEach(function (id) { show(id, '–'); });
    document.getElementById('speed-figures').hidden = false;
    try {
      var lat = await latency();
      show('ping', lat.ping < 10 ? lat.ping.toFixed(1) : Math.round(lat.ping));
      var down = await phase(downOnce, 200 * MB, 'down');
      var up = await phase(upOnce, MAX_UP, 'up');
      await check(await fetch(url('result'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ down_mbps: down, up_mbps: up, ping_ms: lat.ping, jitter_ms: lat.jitter }) }));
      note.textContent = me.dataset.saved;
      note.className = 'note done';
      button.textContent = me.dataset.again;
    } catch (err) {
      note.textContent = me.dataset.failed.replace('{error}', err.message);
      note.className = 'note bad';
      button.textContent = label;
    }
    button.disabled = false;
  }

  button.addEventListener('click', run);
})();
