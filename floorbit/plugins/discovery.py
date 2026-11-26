"""Discovery areas a plugin adds (issue #968, docs/plugin-spec.md#discovery).

A plugin with an agent part that works on inventory devices (``agent.targets``) can say what it
reads from them, area by area, next to the built-in discovery actions::

    uses: [agent]
    agent:
      targets: {credentials: [api], roles: [firewall]}
    discovery:
      - area: routes               # a built-in area: the same shape as telemetry's facts
        platforms: [opnsense]      # optional: only devices whose platform says so
        minutes: 15
      - area: gateways             # an area of its own: a name, and the fields it gives
        name: Gateways
        fields: [name, address, status]
        minutes: 5

The agent part answers ``discover(area, devices)`` (floorbit.plugins.agent.AgentPlugin) with
``{device_id: facts}``; floorbit/plugin_discovery.py runs it on the area's clock and puts the facts
where the built-in areas put theirs.
"""
from __future__ import annotations

import re

AREA_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}\Z')
FIELD_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}\Z')
# The built-in areas a plugin can feed (inventory_discovery.ACTIONS without interfaces, which go
# through a plugin's ``interfaces`` the way monitoring's do).
BUILTIN = ('identity', 'networks', 'optics', 'poe', 'routes')
# Areas whose facts are addresses by nature (networks, next hops): the device's own, not a guest's.
ADDRESSED = ('networks', 'routes')
MAX_AREAS = 20
MAX_FIELDS = 40
MIN_MINUTES = 5
MAX_MINUTES = 24 * 60
DEFAULT_MINUTES = 15


def check_discovery_block(m):
    """An error message for the manifest's ``discovery:`` list, or ''. Normalises it in place: each
    entry gets ``area, name, builtin, roles, platforms, fields, minutes, privacy``."""
    if 'discovery' not in m:
        return ''
    areas = m['discovery']
    if not isinstance(areas, list) or not areas:
        return 'discovery: a list of areas ({area: routes, minutes: 15}, ...)'
    agent = m.get('agent') if isinstance(m.get('agent'), dict) else None
    if 'agent' not in (m.get('uses') or []) or agent is None:
        return 'discovery: runs on the local agent: add "agent" under uses: and an agent: block'
    targets = agent.get('targets')
    if not isinstance(targets, dict):
        return 'discovery: the agent part needs the devices: set agent.targets'
    if len(areas) > MAX_AREAS:
        return f'discovery: at most {MAX_AREAS} areas'
    from ..inventory import ROLES as DEVICE_ROLES
    from ..inventory_discovery import action as builtin_action
    from .agent import PRIVACY
    seen = set()
    for i, entry in enumerate(areas):
        if not isinstance(entry, dict):
            return f'discovery[{i}]: a mapping with area, name, roles, minutes'
        area = entry.get('area')
        if not isinstance(area, str) or not AREA_RE.match(area):
            return f'discovery[{i}].area: lowercase letters, digits and underscores'
        if area in seen:
            return f'discovery.{area}: listed twice'
        seen.add(area)
        if area == 'interfaces':
            return 'discovery.interfaces: interfaces come in through monitoring; not an area a plugin feeds yet'
        builtin = area in BUILTIN
        entry['builtin'] = builtin
        if builtin:
            entry['name'] = builtin_action(area)['name']
        else:
            name = entry.get('name')
            if not isinstance(name, str) or not name.strip():
                return f'discovery.{area}: an area of its own needs a name'
            entry['name'] = ' '.join(name.split())[:60]
        roles = entry.get('roles')
        allowed = list(builtin_action(area)['roles']) if builtin else list(DEVICE_ROLES)
        if isinstance(targets.get('roles'), list):
            allowed = [r for r in allowed if r in targets['roles']]
        if roles is None:
            roles = allowed
        if not isinstance(roles, list) or not roles or any(r not in DEVICE_ROLES for r in roles):
            return f"discovery.{area}.roles: some of {', '.join(DEVICE_ROLES)}"
        if any(r not in allowed for r in roles):
            return f"discovery.{area}.roles: the area is about {', '.join(allowed) or 'no device the plugin has'}"
        entry['roles'] = list(roles)
        platforms = entry.setdefault('platforms', [])
        if not isinstance(platforms, list) or any(not isinstance(p, str) or not p.strip() or len(p) > 60
                                                  for p in platforms):
            return f'discovery.{area}.platforms: a list of platform names'
        entry['platforms'] = [p.strip().lower() for p in platforms]
        fields = entry.setdefault('fields', [])
        if builtin and fields:
            return f'discovery.{area}.fields: a built-in area has the fields Floorbit gives it'
        if not isinstance(fields, list) or len(fields) > MAX_FIELDS \
                or any(not isinstance(f, str) or not FIELD_RE.match(f) for f in fields):
            return f'discovery.{area}.fields: up to {MAX_FIELDS} names (lowercase letters, digits, underscores)'
        minutes = entry.setdefault('minutes', DEFAULT_MINUTES)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not MIN_MINUTES <= minutes <= MAX_MINUTES:
            return f'discovery.{area}.minutes: a whole number from {MIN_MINUTES} to {MAX_MINUTES}'
        privacy = entry.setdefault('privacy', 'device' if area in ADDRESSED else 'aggregate')
        if privacy not in PRIVACY:
            return f"discovery.{area}.privacy: {' or '.join(PRIVACY)}"
        extra = sorted(set(entry) - {'area', 'name', 'builtin', 'roles', 'platforms', 'fields', 'minutes', 'privacy'})
        if extra:
            return f"discovery.{area}: unknown key(s) {', '.join(extra)}"
    # The hosted side asks the agent part through its one discovery call.
    calls = agent.setdefault('calls', [])
    if 'discover' not in calls:
        calls.append('discover')
    return ''
