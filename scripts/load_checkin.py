"""Load test for doors-open (issue #473): a burst of check-ins and every device asking the captive
portal, against a real Floorbit under gunicorn and a real agent, with a pretend LibreNMS.

What it does, all on this machine (nothing talks to LibreNMS, NetBox or Redis):

1. Starts Floorbit under gunicorn as the Docker image does (1 worker, 64 threads), with a floor
   plan of ``--seats`` seats and check-in, the captive portal and ``CHECKIN_TRUST_PROXY`` on. The
   port lookup behind check-in is a fake that takes ``--lookup-ms`` and counts its calls.
2. Starts the agent's captive portal (floorbit_agent.captive) in its own process, asking that
   Floorbit for the done list like at an event.
3. ``--checkins`` players arrive over ``--over`` seconds, most of them early. Each loads the portal page and its info,
   then checks in (each from its own IP, through ``X-Forwarded-For``). Meanwhile ``--clients``
   devices ask the captive portal every ``--captive-every`` seconds.
4. When the port lookups have caught up, Floorbit is stopped and the devices go on asking for
   ``--offline`` seconds: the agent answers from its last list.

It prints response times (p50, p99) against the targets and writes two charts to ``--out``.

    python scripts/load_checkin.py --agent-src ../floorbit-agent
    python scripts/load_checkin.py --checkins 1000 --over 120 --clients 4000 --rate 10

The numbers and charts in docs/sizing.md come from this script.
"""
import argparse
import json
import os
import random
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TARGETS = {'captive': 20, 'portal': 100, 'submit': 100}     # p99 in ms
CAPTIVE_PATH = '/.well-known/captive-portal'


# ── the hosted side, inside gunicorn ───────────────────────────────────────────
class _Redis:
    """No Redis for the load test: an empty one, so the cache never waits for a real one."""

    def __init__(self, *args, **kwargs):
        self.data = {}

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, *args, **kwargs):
        self.data[key] = value
        return True

    def setex(self, key, ttl, value):
        return self.set(key, value)

    def delete(self, *keys):
        return sum(self.data.pop(k, None) is not None for k in keys)

    def keys(self, pattern='*'):
        return list(self.data)

    def scan_iter(self, match='*', **kwargs):
        return iter(list(self.data))

    def ttl(self, key):
        return -1

    def dbsize(self):
        return len(self.data)

    def info(self, *args, **kwargs):
        return {}


def hosted_app():
    """gunicorn's app factory: Floorbit with a pretend LibreNMS behind the port lookup."""
    import redis
    redis.Redis = _Redis
    from floorbit import create_app
    from integrations import checkin

    lookup_s = float(os.environ['LOAD_LOOKUP_MS']) / 1000
    lookups = []

    class Monitoring:
        """LibreNMS as far as check-in sees it: every PC on its own access port."""

        def enabled(self):
            return True

        def resolve_ip(self, ip):
            time.sleep(lookup_s)
            lookups.append(time.time())
            return {'device_name': 'sw-load', 'port': f'Gi1/0/{ip.rsplit(".", 1)[-1]}', 'macs_on_port': 1}

    checkin.lookup_mac = lambda ip: None
    checkin._monitoring = Monitoring
    app = create_app()

    from flask import jsonify

    from floorbit import captive

    # Load-test only: these are never part of Floorbit itself.
    @app.route('/_load/stats')
    def load_stats():
        return jsonify({'lookups': list(lookups), 'queue': checkin.queue_depth()})

    @app.route('/_load/captive')
    def load_captive():
        return jsonify(captive.answer(app, 'load'))

    load_stats._auth_public = load_captive._auth_public = True

    return app


def plan(seats):
    """Seat blocks of 48, and the IP of the PC on each seat."""
    blocks, ips = [], {}
    for b in range((seats + 47) // 48):
        name = f'L{b + 1:03d}'
        count = min(48, seats - b * 48)
        blocks.append({'id': f'blk-{b}', 'name': name, 'cols': count, 'rows': 1, 'x': 0, 'y': b * 40})
        for i in range(1, count + 1):
            n = b * 48 + i
            ips[f'{name}-{i}'] = f'10.{n >> 16 & 255}.{n >> 8 & 255}.{n & 255}'
    return blocks, ips


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_up(url, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.3)
    raise SystemExit(f'{url} did not come up')


AGENT = """
import json, sys, time, urllib.request
sys.path.insert(0, sys.argv[1])
from floorbit_agent import captive
def ask():
    with urllib.request.urlopen(sys.argv[2], timeout=5) as r:
        return json.load(r)
captive.REFRESH = float(sys.argv[4])
c = captive.Captive(ask, proxies=['127.0.0.1'], log=lambda m: print(m, flush=True))
captive.serve(c, sys.argv[3], log=lambda m: print(m, flush=True))
while True:
    time.sleep(3600)
"""


# ── the clients ────────────────────────────────────────────────────────────────
class Recorder:
    def __init__(self, start):
        self.start = start
        self.rows = []          # (kind, at, ms, ok)
        self.lock = threading.Lock()

    def get(self, kind, url, ip, body=None):
        headers = {'X-Forwarded-For': ip}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=data, headers=headers)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                payload = r.read()
                ok = r.status == 200
        except (OSError, urllib.error.URLError):
            payload, ok = b'', False
        ms = (time.perf_counter() - t0) * 1000
        with self.lock:
            self.rows.append((kind, time.time() - self.start, ms, ok))
        return payload


def pct(values, p):
    values = sorted(values)
    if not values:
        return 0.0
    return values[min(len(values) - 1, round(p / 100 * (len(values) - 1)))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--seats', type=int, default=4000)
    ap.add_argument('--checkins', type=int, default=1000)
    ap.add_argument('--over', type=float, default=120, help='seconds the check-ins arrive over')
    ap.add_argument('--clients', type=int, default=4000, help='devices asking the captive portal')
    ap.add_argument('--captive-every', type=float, default=30, help='seconds between asks per device')
    ap.add_argument('--rate', type=int, default=10, help='CHECKIN_VERIFY_RATE: port lookups a second')
    ap.add_argument('--lookup-ms', type=float, default=50, help='pretend LibreNMS time per port lookup')
    ap.add_argument('--offline', type=float, default=60, help='seconds the agent answers without Floorbit')
    ap.add_argument('--agent-src',
                    default=os.environ.get('FLOORBIT_AGENT_SRC') or os.path.join(ROOT, '..', 'floorbit-agent'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', 'img'), help='where the charts go')
    ap.add_argument('--seed', type=int, default=473)
    args = ap.parse_args(argv)
    if not os.path.isdir(os.path.join(args.agent_src, 'floorbit_agent')):
        raise SystemExit(f'No floorbit_agent in {args.agent_src}: pass --agent-src')
    rng = random.Random(args.seed)

    tmp = tempfile.mkdtemp(prefix='floorbit-burst-')
    blocks, ips = plan(args.seats)
    with open(os.path.join(tmp, 'data.json'), 'w') as f:
        json.dump({'setup': {'done': True, 'steps': {}}, 'seat_blocks': blocks}, f)
    port, agent_port = free_port(), free_port()
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, PYTHONPATH=ROOT, FLOORBIT_DATA_FILE=os.path.join(tmp, 'data.json'),
               CHECKIN_FILE=os.path.join(tmp, 'checkins.json'), SECRET_KEY='load-test-only',
               FLOORBIT_SECRET_KEY_FILE=os.path.join(tmp, 'secret.key'),
               CHECKIN_ENABLED='true', CAPTIVE_ENABLED='true', CHECKIN_TRUST_PROXY='true',
               CHECKIN_VERIFY_RATE=str(args.rate), PUBLIC_URL='https://floor.example.com',
               LOAD_LOOKUP_MS=str(args.lookup_ms))
    for name in ('NETBOX_URL', 'NETBOX_TOKEN', 'LIBRENMS_URL', 'LIBRENMS_TOKEN', 'FLOORBIT_DATABASE_URL'):
        env.pop(name, None)
    # The logs stay open as long as the processes run.
    hosted_log = open(os.path.join(tmp, 'hosted.log'), 'w')  # noqa: SIM115
    agent_log = open(os.path.join(tmp, 'agent.log'), 'w')  # noqa: SIM115
    hosted = subprocess.Popen(
        [sys.executable, '-m', 'gunicorn', '--bind', f'127.0.0.1:{port}', '--workers', '1',
         '--worker-class', 'gthread', '--threads', '64', '--chdir', os.path.join(ROOT, 'scripts'),
         'load_checkin:hosted_app()'],
        env=env, stdout=hosted_log, stderr=subprocess.STDOUT,
        start_new_session=True)
    agent = None
    try:
        wait_up(f'{base}/_load/stats')
        agent = subprocess.Popen(
            [sys.executable, '-I', '-c', AGENT, os.path.abspath(args.agent_src), f'{base}/_load/captive',
             f'127.0.0.1:{agent_port}', '5'],
            stdout=agent_log, stderr=subprocess.STDOUT, start_new_session=True)
        wait_up(f'http://127.0.0.1:{agent_port}{CAPTIVE_PATH}')
        result = run(args, rng, base, f'http://127.0.0.1:{agent_port}{CAPTIVE_PATH}', ips, hosted)
    finally:
        for proc in (hosted, agent):
            if proc and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(10)
        print(f'Logs in {tmp}')
    report(args, result)
    return result


def run(args, rng, base, captive_url, ips, hosted):
    start = time.time()
    rec = Recorder(start)
    stop_captive = threading.Event()
    samples = []                     # (at, queue, lookups so far)
    seats = rng.sample(sorted(ips), args.checkins)
    # Doors open: most arrive early, then fewer and fewer until --over.
    arrivals = sorted(rng.triangular(0, args.over, 0) for _ in seats)
    devices = list(ips.values())[:args.clients]
    while len(devices) < args.clients:   # more devices than seats: phones on the Wi-Fi
        n = len(devices)
        devices.append(f'10.200.{n >> 8 & 255}.{n & 255}')
    marks = {}

    def player(seat, at):
        time.sleep(max(0, start + at - time.time()))
        ip = ips[seat]
        rec.get('portal', f'{base}/checkin', ip)
        rec.get('portal', f'{base}/api/checkin/info', ip)
        rec.get('submit', f'{base}/api/checkin', ip, {'seat': seat, 'username': f'player-{seat.lower()}'})

    def devices_ask(pool):
        """Every device asks every ``--captive-every`` seconds, each at its own offset."""
        due = sorted((rng.uniform(0, args.captive_every), ip) for ip in devices)
        rounds = 0
        while not stop_captive.is_set():
            for at, ip in due:
                at += rounds * args.captive_every
                time.sleep(max(0, start + at - time.time()))
                if stop_captive.is_set():
                    return
                pool.submit(rec.get, 'captive', captive_url, ip)
            rounds += 1

    def sampler():
        while not stop_captive.is_set():
            try:
                with urllib.request.urlopen(f'{base}/_load/stats', timeout=5) as r:
                    s = json.load(r)
                samples.append((time.time() - start, s['queue'], [t - start for t in s['lookups']]))
            except (OSError, urllib.error.URLError):
                if hosted.poll() is not None:
                    return
            time.sleep(1)

    # The captive clients get their own pool so a slow hosted side can't hold them up.
    per_second = args.clients / args.captive_every
    cap_pool = ThreadPoolExecutor(max_workers=max(16, int(per_second / 5)))
    threading.Thread(target=devices_ask, args=(cap_pool,), daemon=True).start()
    threading.Thread(target=sampler, daemon=True).start()
    with ThreadPoolExecutor(max_workers=128) as pool:
        for seat, at in zip(seats, arrivals, strict=True):
            pool.submit(player, seat, at)
    marks['burst_end'] = time.time() - start
    # The lookups drain at the set rate; wait for them, plus one agent refresh.
    end = time.time() + args.checkins / args.rate * 2 + 60
    while time.time() < end and (not samples or samples[-1][1] > 0 or samples[-1][0] < marks['burst_end']):
        time.sleep(1)
    marks['drained'] = time.time() - start
    time.sleep(8)
    done = json.loads(rec.get('check', f'{base}/_load/captive', '127.0.0.1') or b'{}').get('done', [])
    marks['offline'] = time.time() - start
    os.killpg(hosted.pid, signal.SIGTERM)
    hosted.wait(15)
    time.sleep(args.offline)
    stop_captive.set()
    marks['end'] = time.time() - start
    cap_pool.shutdown(wait=True)
    # The agent still says "done" for the checked-in PCs and "sign in" for the others.
    checked = set(done)
    wrong = 0
    for ip in devices[:200]:
        body = json.loads(rec.get('verify', captive_url, ip) or b'{}')
        wrong += body.get('captive') is (ip in checked)
    lookups = samples[-1][2] if samples else []
    return {'rows': rec.rows, 'samples': samples, 'lookups': lookups, 'marks': marks, 'arrivals': arrivals,
            'checked_in': len(checked), 'wrong_answers': wrong}


# ── the report ────────────────────────────────────────────────────────────────
def report(args, r):
    rows, marks = r['rows'], r['marks']
    lines = [f"{args.checkins} check-ins over {args.over:g} s, {args.clients} devices asking the captive "
             f"portal every {args.captive_every:g} s, {args.rate} port lookups a second "
             f"({args.lookup_ms:g} ms each)", '',
             '| What | Requests | Failed | p50 | p99 | Target (p99) |', '| --- | --- | --- | --- | --- | --- |']
    phases = [('captive', 'Captive portal (agent), Floorbit up', lambda at: at < marks['offline']),
              ('captive', 'Captive portal (agent), Floorbit stopped', lambda at: at > marks['offline'] + 2),
              ('portal', 'Check-in page and its info', lambda at: True),
              ('submit', 'Check-in submit', lambda at: True)]
    ok = True
    for kind, label, when in phases:
        sel = [(ms, good) for k, at, ms, good in rows if k == kind and when(at)]
        ms = [m for m, _ in sel]
        failed = sum(1 for _, g in sel if not g)
        p99 = pct(ms, 99)
        meets = p99 < TARGETS[kind] and not failed
        ok &= meets
        lines.append(f'| {label} | {len(sel)} | {failed} | {pct(ms, 50):.1f} ms | {p99:.1f} ms | '
                     f'< {TARGETS[kind]} ms {"✓" if meets else "✗"} |')
    drain = marks['drained'] - marks['burst_end']
    peak = max((q for _, q, _ in r['samples']), default=0)
    lines += ['', f"Port lookup queue: peak {peak}, empty {drain:.0f} s after the last check-in "
              f"({len(r['lookups'])} lookups). Checked in: {r['checked_in']}. "
              f"Wrong captive answers after Floorbit stopped: {r['wrong_answers']} of 200."]
    text = '\n'.join(lines)
    print(text)
    os.makedirs(args.out, exist_ok=True)
    charts(args, r)
    return ok


def _svg_chart(width, height, panels, x_max, x_label, shade=None, legend=None):
    """Small multiples sharing one time axis. Each panel: title, y max, series of (label, color, points),
    and optional dashed reference lines (label, value)."""
    ink, muted, grid, surface = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    left, right, top = 56, 20, 36
    gap = 44
    ph = (height - top - 60 - gap * (len(panels) - 1)) / len(panels)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'font-family="Inter, Helvetica, Arial, sans-serif" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="{surface}"/>']
    if legend:
        x = left
        for label, color in legend:
            out.append(f'<rect x="{x}" y="12" width="12" height="3" rx="1.5" fill="{color}"/>'
                       f'<text x="{x + 18}" y="17" fill="{ink}">{label}</text>')
            x += 26 + len(label) * 6.6
    pw = width - left - right

    def sx(v):
        return left + v / x_max * pw
    for i, p in enumerate(panels):
        y0 = top + i * (ph + gap) + 16
        ymax = p['y_max']

        def sy(v, y0=y0, ymax=ymax):
            return y0 + ph - min(v, ymax) / ymax * ph
        out.append(f'<text x="{left}" y="{y0 - 8}" fill="{ink}" font-weight="600">{p["title"]}</text>')
        if shade:
            a, b, label = shade
            out.append(f'<rect x="{sx(a):.1f}" y="{y0}" width="{sx(b) - sx(a):.1f}" height="{ph}" fill="#efeeea"/>')
            if i == 0:
                out.append(f'<text x="{sx(a) + 6:.1f}" y="{y0 + 14}" fill="{muted}">{label}</text>')
        for v in _ticks(ymax):
            y = sy(v)
            out.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{grid}"/>'
                       f'<text x="{left - 8}" y="{y + 4:.1f}" fill="{muted}" text-anchor="end">{v:g}</text>')
        for label, value in p.get('refs', []):
            y = sy(value)
            out.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{muted}" '
                       f'stroke-dasharray="4 4"/><text x="{width - right}" y="{y - 5:.1f}" fill="{muted}" '
                       f'text-anchor="end">{label}</text>')
        for _label, color, pts in p['series']:
            if pts:
                d = ' '.join(f'{"M" if j == 0 else "L"}{sx(x):.1f},{sy(y):.1f}' for j, (x, y) in enumerate(pts))
                out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
                           f'stroke-linejoin="round" stroke-linecap="round"/>')
        out.append(f'<text x="{left - 44}" y="{y0 + ph / 2:.1f}" fill="{muted}" '
                   f'transform="rotate(-90 {left - 44} {y0 + ph / 2:.1f})" text-anchor="middle">{p["unit"]}</text>')
    yb = top + len(panels) * ph + (len(panels) - 1) * gap + 16
    step = 30 if x_max <= 400 else 60
    for t in range(0, int(x_max) + 1, step):
        out.append(f'<text x="{sx(t):.1f}" y="{yb + 18:.1f}" fill="{muted}" text-anchor="middle">{t}</text>')
    out.append(f'<text x="{left + pw / 2:.1f}" y="{yb + 34:.1f}" fill="{muted}" text-anchor="middle">{x_label}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def _nice(top):
    """A round axis maximum at or above ``top``, with four even steps."""
    for step in (1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if step * 4 >= top:
            return step * 4
    return top


def _ticks(ymax):
    return [ymax * k / 4 for k in range(5)]


def _per_second(times, x_max, window=5):
    n = int(x_max // window) + 1
    counts = [0] * n
    for t in times:
        if 0 <= t < n * window:
            counts[int(t // window)] += 1
    return [(i * window + window / 2, c / window) for i, c in enumerate(counts)]


def charts(args, r):
    blue, orange, aqua = '#2a78d6', '#eb6834', '#1baf7a'
    m, x_max = r['marks'], r['marks']['end']
    submits = [at for k, at, _, _ in r['rows'] if k == 'submit']
    arrive, look = _per_second(submits, x_max), _per_second(r['lookups'], x_max)
    queue = [(at, q) for at, q, _ in r['samples']]
    top_rate = max([y for _, y in arrive + look] + [1])
    burst = _svg_chart(900, 520, [
        {'title': 'Check-ins and port lookups a second', 'unit': 'per second', 'y_max': _nice(top_rate * 1.1),
         'series': [('Check-ins', blue, arrive), ('Port lookups', orange, look)],
         'refs': [(f'CHECKIN_VERIFY_RATE = {args.rate}', args.rate)]},
        {'title': 'Check-ins waiting for their port lookup', 'unit': 'waiting',
         'y_max': _nice(max([q for _, q in queue] + [10]) * 1.05), 'series': [('Waiting', blue, queue)]},
    ], x_max, 'seconds since doors open', shade=(m['offline'], x_max, 'Floorbit stopped'),
        legend=[('Check-ins', blue), ('Port lookups', orange)])

    def p99_series(kind, window=10):
        buckets = {}
        for k, at, ms, ok in r['rows']:
            if k == kind and ok:
                buckets.setdefault(int(at // window), []).append(ms)
        return [(b * window + window / 2, pct(v, 99)) for b, v in sorted(buckets.items())]
    lat = [p99_series(k) for k in ('captive', 'portal', 'submit')]
    top_ms = max([y for s in lat for _, y in s] + [110])
    times = _svg_chart(900, 360, [
        {'title': 'Response time, p99 per 10 seconds', 'unit': 'ms', 'y_max': _nice(top_ms * 1.05),
         'series': [('Captive portal (agent)', aqua, lat[0]), ('Check-in page', blue, lat[1]),
                    ('Check-in submit', orange, lat[2])],
         'refs': [('captive target 20 ms', 20), ('page and submit target 100 ms', 100)]},
    ], x_max, 'seconds since doors open', shade=(m['offline'], x_max, 'Floorbit stopped'),
        legend=[('Captive portal (agent)', aqua), ('Check-in page', blue), ('Check-in submit', orange)])
    for name, svg in (('load-checkin-burst', burst), ('load-checkin-latency', times)):
        path = os.path.join(args.out, f'{name}.svg')
        with open(path, 'w') as f:
            f.write(svg)
        print(f'Chart: {path}')


if __name__ == '__main__':
    sys.exit(0 if main() is not None else 1)
