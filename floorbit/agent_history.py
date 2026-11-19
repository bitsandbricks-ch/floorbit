"""Each local agent's numbers over time, for the graphs on its page (Settings > Local agents > one agent).

An agent's report (every half minute) only says how things are now. Here a few of its numbers are
kept with the telemetry series (telemetry/storage.py: Floorbit's database, or VictoriaMetrics when
it is there), under the device ``agent:<id>``, so they age out with them. Counters (points, sends,
syslog lines, reconnects) become rates per minute against the report before; a counter that went
down (the agent restarted) leaves that sample out.
"""
import contextlib
import threading
import time

from .telemetry import storage

DEVICE = storage.AGENT
# What the page draws, in its order. "rate": a counter, stored per minute.
METRICS = {
    'points': 'rate', 'sent': 'rate', 'series': 'gauge', 'heard': 'gauge', 'failing': 'gauge',
    'telegraf_restarts': 'gauge', 'reconnects': 'rate', 'syslog': 'rate', 'median_ms': 'gauge',
}
RATE_GAP = (5, 600)      # seconds between two reports that still make a rate


def device(agent_id):
    return f'{DEVICE}{agent_id}'


def _plugin_metrics(report):
    return {pid: (h.get('metrics') or {}) for pid, h in (report.get('plugins') or {}).items()}


def _counters(report):
    plugins = _plugin_metrics(report)
    tele = plugins.get('telemetry') or {}
    return {
        'points': tele.get('points', 0) + tele.get('polled_points', 0) if tele else None,
        'sent': sum(m.get('sent', 0) for m in plugins.values()) if plugins else None,
        'reconnects': max(report.get('reconnects', 0), report.get('link_drops', 0)),
        'syslog': report.get('syslog_received'),
    }


def values(before, report, stats=None):
    """{metric: value} worth keeping from one report, with ``before`` (the report before it) for rates."""
    out = {}
    tele = _plugin_metrics(report).get('telemetry')
    if tele:
        for metric, name in (('series', 'series'), ('heard', 'devices_heard'), ('failing', 'devices_failing'),
                             ('telegraf_restarts', 'telegraf_restarts')):
            if name in tele:
                out[metric] = float(tele[name])
    if stats and stats.get('median_ms') is not None:
        out['median_ms'] = float(stats['median_ms'])
    gap = report['at'] - before['at'] if before and 'at' in before else None
    if gap is not None and RATE_GAP[0] <= gap <= RATE_GAP[1]:
        old, new = _counters(before), _counters(report)
        for metric, value in new.items():
            was = old.get(metric)
            if value is not None and was is not None and value >= was:
                out[metric] = round((value - was) * 60 / gap, 2)
    return out


def _write(values_, now):
    from .database import DatabaseError
    # The database is away: this sample is lost, the next one comes in half a minute.
    with contextlib.suppress(DatabaseError):
        storage.storage().sample(values_, now)


def record(agent_id, before, report, stats=None):
    """Keep what one report says. VictoriaMetrics is asked over the network, so off the caller's
    thread: the report may come in on the agent's WebSocket link, which must not wait on it."""
    found = values(before, report, stats)
    if not found:
        return
    keyed = {storage.series_key(device(agent_id), None, k): v for k, v in found.items()}
    if storage.vm_url():
        threading.Thread(target=_write, args=(keyed, report['at']), daemon=True).start()
    else:
        _write(keyed, report['at'])


def history(agent_id, hours=6, now=None):
    """{metric: [[unix time, value]]} for one agent, oldest first."""
    now = time.time() if now is None else now
    store = storage.storage()
    return {m: store.series(device(agent_id), None, m, hours, now) for m in METRICS}
