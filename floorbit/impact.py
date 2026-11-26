"""Which seats a down switch or uplink cuts off (issue #950, docs/alerts.md "Seats behind a failure").

Seats are keyed by switch + port, so a failure's reach is known: the seats on the down switch, and
the seats on every switch behind it. "Behind" comes from the links between switches (floorbit/links.py):
a switch is cut off when no path of up links through online boxes reaches the core any more.

The core is the routers and firewalls the links reach. Where the links name none (only switches
drawn), each group of linked switches counts its busiest switch (the most links) as the core: that is
the box the others hang off. Without links at all only the down switch's own seats count.

A single seat's port going down cuts off that seat alone; the floor plan already shows it as offline.

Only seat names leave here, never who sits there.
"""
from . import inventory, links

CORE_ROLES = ('router', 'firewall')


def short(name):
    return str(name or '').lower().split('.')[0]


def seats_by_switch(data):
    """{switch (short, lower case): {seat}} from every place that knows a seat's switch: the last
    port read, what the status page remembered while a switch went down, the seat mapping, the
    ports learned at check-in or on the seat walk, and the patch plan's cables."""
    from flask import current_app

    from integrations import checkin, seat_sources

    from . import cables, status_page
    out = {}

    def add(switch, seat):
        if switch and seat:
            out.setdefault(short(switch), set()).add(str(seat).upper())
    watch = current_app.extensions.get('floorbit_attention')
    for (switch, _port), seat in dict(getattr(watch.view() if watch is not None else None, 'port_seats', None)
                                      or {}).items():
        add(switch, seat)
    with status_page._lock:
        remembered = {k: set(v) for k, v in status_page._seats_of.items()}
    for switch, seats in remembered.items():
        for seat in seats:
            add(switch, seat)
    try:
        mapped = seat_sources.load() or {}
    except Exception:  # noqa: BLE001 - a seat source that fails leaves the other places
        mapped = {}
    for seat, row in mapped.items():
        add((row or {}).get('switch'), seat)
    for seat, port in (checkin.learned_ports() or {}).items():
        add((port or {}).get('switch'), seat)
    for c in cables.all_cables(data):
        add(c.get('switch'), c.get('seat'))
    return out


def _graph(data):
    """(nodes, edges, roles): the linked boxes by short name, the links as (a, b, link id)."""
    roles = {short(d['name']): d.get('role') for d in inventory.devices(data) if d.get('name')}
    edges = [(short(link['a']), short(link['b']), link['id']) for link in links.all_links(data)]
    nodes = {n for a, b, _ in edges for n in (a, b)}
    return nodes, edges, roles


def _components(nodes, edges):
    seen, groups = set(), []
    near = {n: set() for n in nodes}
    for a, b, _ in edges:
        near[a].add(b)
        near[b].add(a)
    for start in sorted(nodes):
        if start in seen:
            continue
        group, todo = set(), [start]
        while todo:
            n = todo.pop()
            if n in group:
                continue
            group.add(n)
            todo.extend(near[n] - group)
        seen |= group
        groups.append(group)
    return groups


def _roots(nodes, edges, roles):
    """The core of each group of linked boxes: its routers and firewalls, else its busiest switch."""
    degree = dict.fromkeys(nodes, 0)
    for a, b, _ in edges:
        degree[a] += 1
        degree[b] += 1
    roots = set()
    for group in _components(nodes, edges):
        core = {n for n in group if roles.get(n) in CORE_ROLES}
        roots |= core or {min(group, key=lambda n: (-degree[n], n))}
    return roots


def _reached(roots, edges, down_nodes, down_links):
    near = {}
    for a, b, link_id in edges:
        if link_id in down_links or a in down_nodes or b in down_nodes:
            continue
        near.setdefault(a, set()).add(b)
        near.setdefault(b, set()).add(a)
    seen, todo = set(), [r for r in roots if r not in down_nodes]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        todo.extend(near.get(n, set()) - seen)
    return seen


def failures(data, offline, down_links):
    """What each failure cuts off. ``offline``: the names of the switches that are down;
    ``down_links``: the ids of the links that are down.

    Returns ``{'switches': {name: {'behind': [switch], 'seats': [seat]}}, 'links': {link id: {...}},
    'seats': {seat: cause}}``. A failure's seats are its own (a switch's) plus those of every switch
    only it cuts off; ``seats`` is every seat cut off right now, with the down switch or link to blame."""
    nodes, edges, roles = _graph(data)
    names = {short(n): n for n in offline}
    down = set(names)
    down_links = set(down_links) & {e[2] for e in edges}
    by_switch = seats_by_switch(data)
    roots = _roots(nodes, edges, roles) if nodes else set()
    everyone = nodes - _reached(roots, edges, set(), set()) if nodes else set()   # never linked to the core

    def cut(dn, dl):
        if not nodes:
            return set()
        return nodes - _reached(roots, edges, dn, dl) - dn - everyone

    def seats_of(boxes):
        from .page_index import _seat_key  # C-9 before C-10
        return sorted(set().union(*(by_switch.get(b, set()) for b in boxes)) if boxes else set(), key=_seat_key)

    shown = {short(d['name']): d['name'] for d in inventory.devices(data) if d.get('name')}
    named = lambda boxes: sorted(shown.get(b, b) for b in boxes)   # noqa: E731
    out = {'switches': {}, 'links': {}, 'seats': {}}
    for key, name in sorted(names.items()):
        behind = cut({key}, set())
        out['switches'][name] = {'behind': named(behind), 'seats': seats_of({key} | behind)}
    labels = {e[2]: e for e in edges}
    for link_id in sorted(down_links):
        behind = cut(set(), {link_id})
        out['links'][link_id] = {'behind': named(behind), 'seats': seats_of(behind)}
    # Blame the failure furthest up: a seat on a switch that is down only because the one before it
    # is belongs to that one, so the plan and the list point at the same cause.
    for box in sorted(down | cut(down, down_links)):
        name = shown.get(box, box)
        cause = next((n for n, f in out['switches'].items() if name in f['behind']), None)
        if cause is None:
            link = next((i for i, f in out['links'].items() if name in f['behind']), None)
            if link:
                a, b, _ = labels[link]
                cause = f'{shown.get(a, a)} to {shown.get(b, b)}'
        cause = cause or names.get(box) or next(iter(sorted(names.values())), '')
        for seat in by_switch.get(box, ()):
            out['seats'].setdefault(seat, cause)
    return out
