"""The inventory list's Uplink, Last 24 h and Agent columns (issue #981), for every device in the
one list call, from what the server already keeps: the links and their last port read (links.py),
the status monitor's switch changes (stats), and who collects each device (telemetry.agent)."""
import time

HOURS = 24
ROOT_ROLES = ('router',)      # where the network starts when no internet line says otherwise


def uplinks(data, now=None):
    """{device name, lower case: its uplink}: the link towards the core, as the topology draws it.
    ``{'device', 'port', 'peer', 'peer_port', 'speed_bps', 'planned_gbps', 'state', 'issue'}``.
    The core is where the internet lines come in (else the routers); each other device's uplink is
    its link to a neighbour one hop closer, the fastest planned one when there are several."""
    from . import links
    from .links import ROLES as TOPOLOGY_ROLES
    topo = links.topology(now=now, suggest=False)
    nodes = {n['name'].lower(): n for n in topo['nodes']}
    roots = {u['device'].lower() for u in topo.get('uplinks') or []} \
        or {k for k, n in nodes.items() if n.get('role') in ROOT_ROLES}
    near = {}
    for link in topo['links']:
        a, b = link['a'].lower(), link['b'].lower()
        near.setdefault(a, []).append((b, link, 'a'))
        near.setdefault(b, []).append((a, link, 'b'))
    hops = dict.fromkeys(roots, 0)
    queue = list(roots)
    while queue:
        here = queue.pop(0)
        for other, _link, _end in near.get(here, ()):
            if other not in hops:
                hops[other] = hops[here] + 1
                queue.append(other)
    out = {}
    for name, ends in near.items():
        if name not in hops or hops[name] == 0 or (nodes.get(name) or {}).get('role') not in TOPOLOGY_ROLES:
            continue
        up = [(link, end) for other, link, end in ends if hops.get(other, 1e9) < hops[name]]
        if not up:
            continue
        link, end = max(up, key=lambda x: x[0].get('speed') or 0)
        peer = 'b' if end == 'a' else 'a'
        out[name] = {'port': link[f'{end}_port'], 'peer': link[peer], 'peer_port': link[f'{peer}_port'],
                     'speed_bps': link.get('speed_bps'), 'planned_gbps': link.get('speed'),
                     'state': link.get('state') or 'unknown', 'issue': link.get('issue') or ''}
    return out


def last_day(switch_events, states, now=None):
    """{device name, lower case: [seconds down in each of the last 24 hours, oldest first]}, from the
    status monitor's changes; ``states`` {name: 'online'|'offline'} now. A device the monitor never
    reported has no row: the strip stays grey."""
    now = time.time() if now is None else now
    start = now - HOURS * 3600
    by_name = {}
    for t, _sid, name, status in sorted(switch_events or [], key=lambda e: e[0]):
        by_name.setdefault(str(name or '').lower(), []).append((t, status))
    out = {}
    for name in set(by_name) | {k for k, v in states.items() if v in ('online', 'offline')}:
        changes = by_name.get(name, [])
        before = [s for t, s in changes if t < start]
        inside = [(t, s) for t, s in changes if t >= start]
        # The state at the start: the last change before it, else the opposite of the first one inside.
        state = before[-1] if before else (('online' if inside[0][1] == 'offline' else 'offline') if inside
                                           else states.get(name, 'online'))
        down = [0.0] * HOURS
        t0 = start
        for t, s in [*inside, (now, None)]:
            if state == 'offline':
                _add(down, start, t0, t)
            t0, state = t, s if s is not None else state
        out[name] = [round(x) for x in down]
    return out


def _add(down, start, a, b):
    for h in range(HOURS):
        lo, hi = start + h * 3600, start + (h + 1) * 3600
        down[h] += max(0.0, min(b, hi) - max(a, lo))


def collectors(data):
    """{device name, lower case: telemetry.agent's value}: '' (Auto) for the rest."""
    from .telemetry import targets
    out = {}
    for name, who in targets.pinned(data).items():
        out[name] = f"{targets.TAG_PREFIX}{who['tag']}" if who['tag'] else who['agent']
    return out
