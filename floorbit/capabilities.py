"""Capabilities (#989): one switch for something the crew wants, with what it still needs.

Turning on attendee check-in took several places (a setting, a plugin, an agent, the DHCP).
A capability switches its parts together: settings that are only on/off for it, feature switches
(``features.py``) and the plugins that exist only to provide it. Then it lists what it still needs,
each worked out from what is there (an agent connected, a port set, another capability on), or
marked as outside Floorbit (an option in the event's DHCP), with a link to where it is done.

Nothing new is stored: a capability is on when all its parts are on.
"""
from . import features

# id, the parts it switches, the capabilities it needs on, and the extra checks it lists.
CAPABILITIES = (
    {'id': 'front_door', 'settings': (), 'features': (), 'plugins': ('front-door',), 'requires': (),
     'checks': ('agent',)},
    # The note on phones comes with the front door on every agent; option 114 makes phones ask for it.
    {'id': 'checkin', 'settings': ('integrations.checkin_enabled',), 'features': (), 'plugins': (),
     'requires': ('front_door',), 'checks': ('dhcp114',)},
    {'id': 'logs', 'settings': (), 'features': ('syslog',), 'plugins': ('syslog-relay',), 'requires': (),
     'checks': ('agent', 'port:syslog-relay')},
    {'id': 'traffic', 'settings': (), 'features': ('traffic',), 'plugins': ('netflow-relay',), 'requires': (),
     'checks': ('agent', 'port:netflow-relay')},
    {'id': 'electrics', 'settings': (), 'features': ('power',), 'plugins': (), 'requires': (),
     'checks': ('power_source',)},
)
BY_ID = {c['id']: c for c in CAPABILITIES}


class CapabilityError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _parts(cap, settings, registry, off):
    """[(kind, id, on)] for every part this instance has (a plugin that isn't installed is left out)."""
    parts = [('setting', k, bool(settings.get(k))) for k in cap['settings']]
    parts += [('feature', f, f not in off) for f in cap['features']]
    for pid in cap['plugins']:
        spec = registry.specs.get(pid) if registry is not None else None
        if spec is not None:
            parts.append(('plugin', pid, bool(registry.enabled(spec))))
    return parts


def _port_set(pid, settings, agents_data):
    if int(settings.get(f'plugin.{pid}.port') or 0) > 0:
        return True
    return any(int(((a.get('plugin_settings') or {}).get(pid) or {}).get('port') or 0) > 0 for a in agents_data)


def _check(name, settings, registry, agents, agents_data):
    """One thing a capability needs: ``ok`` True, False, or None (outside Floorbit, can't tell)."""
    if name == 'agent':
        if not agents:
            return {'id': 'agent', 'ok': False, 'href': '/settings/agents'}
        return {'id': 'agentConnected', 'ok': any(a.get('connected') for a in agents), 'href': '/settings/agents'}
    if name.startswith('port:'):
        pid = name.split(':', 1)[1]
        return {'id': f'port.{pid}', 'ok': _port_set(pid, settings, agents_data), 'href': f'/settings/plugins/{pid}'}
    if name == 'dhcp114':
        return {'id': 'dhcp114', 'ok': None, 'href': None}
    if name == 'power_source':
        ok = bool(registry and registry.feeders('power'))
        return {'id': 'powerSource', 'ok': ok, 'href': '/settings/plugins'}
    raise KeyError(name)


def status(settings, registry, agents=(), data=None):
    """Every capability: on, off or partly on, its parts, and what it still needs."""
    from .store import load_data
    data = load_data() if data is None else data
    off = features.off(data)
    agents_data = [a for a in data.get('agents') or [] if isinstance(a, dict)]
    states = {}
    out = []
    for cap in CAPABILITIES:
        parts = _parts(cap, settings, registry, off)
        on = sum(p[2] for p in parts)
        state = 'on' if parts and on == len(parts) else 'off' if not on else 'partly'
        states[cap['id']] = state
        forced = sorted(f for f in cap['features'] if f in features.forced_off())
        out.append({'id': cap['id'], 'state': state, 'forced_off': bool(forced),
                    'parts': [{'kind': k, 'id': i, 'on': v} for k, i, v in parts], 'needs': []})
    for item, cap in zip(out, CAPABILITIES, strict=True):
        needs = [{'id': f'cap.{r}', 'ok': states[r] == 'on', 'href': f'#cap-{r}'} for r in cap['requires']]
        needs += [_check(c, settings, registry, agents, agents_data) for c in cap['checks']]
        item['needs'] = needs
    return out


def switch(cap_id, on, settings, registry):
    """Turn every part of a capability on or off together. Returns the parts that changed."""
    cap = BY_ID.get(cap_id)
    if cap is None:
        raise CapabilityError('No such capability.', 404)
    if not isinstance(on, bool):
        raise CapabilityError('Send {"on": true} or {"on": false}.')
    forced = [f for f in cap['features'] if f in features.forced_off()]
    if on and forced:
        raise CapabilityError(f"{', '.join(forced)} is turned off by {features.ENV} on the server.")
    changed = []
    wanted = {k: on for k in cap['settings'] if bool(settings.get(k)) != on}
    if wanted:
        settings.update(wanted)
        changed += list(wanted)
    feats = dict.fromkeys(cap['features'], on)
    if feats:
        changed += features.update(feats)
    for pid in cap['plugins']:
        spec = registry.specs.get(pid) if registry is not None else None
        if spec is not None and bool(registry.enabled(spec)) != on:
            registry.set_enabled(pid, on)
            changed.append(pid)
    return changed
