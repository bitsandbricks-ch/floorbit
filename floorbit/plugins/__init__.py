"""Plugins: extra data sources, actions, widgets and endpoints that live outside Floorbit's core.

A plugin is a folder with ``plugin.yaml`` (the manifest) and usually ``plugin.py``. The design
follows labdex (manifest, ``Plugin`` class with methods found by name, a context object, widgets
as data) and Hubra (``uses:``: a plugin lists the areas it extends and is refused anything else).
Adapted from labdex's plugins/__init__.py (AGPL-3.0, by the same author).

Where plugins come from, and how far they are trusted:

=============  ==============================================  =========================
trust          where                                           runs
=============  ==============================================  =========================
builtin        ``floorbit/builtin_plugins/`` (ships with it)   inside Floorbit
official       the Marketplace, signed with a key built into    inside Floorbit
               this image (``floorbit/keys/plugins/``)
community      a Marketplace source the operator added, signed  inside Floorbit
               with a key in ``FLOORBIT_COMMUNITY_KEYS``
development    ``FLOORBIT_DEV_PLUGINS`` (a folder of           inside Floorbit; never set
               checkouts, for writing plugins)                 it in production
=============  ==============================================  =========================

Nothing unsigned is ever installed: an admin picks from signed indexes, and only the server's
operator can trust a key (floorbit/marketplace.py, docs/marketplace.md). Every plugin starts
switched off; an admin turns it on under Settings > Plugins. See docs/plugins.md.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import re
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .base import Context, LogBuffer, Plugin, PluginError
from .widgets import WidgetError, check_widget

__all__ = ['Plugin', 'PluginError', 'Registry', 'Spec', 'init_plugins']

ID_RE = re.compile(r'^[a-z][a-z0-9-]{1,39}\Z')
NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}\Z')
BUILTIN_DIR = Path(__file__).resolve().parent.parent / 'builtin_plugins'
DEV_ENV = 'FLOORBIT_DEV_PLUGINS'

# The areas a plugin may extend (Hubra's ``uses:``). Anything not listed is refused.
AREAS = {
    'settings':  'its own settings, under Settings > Plugins',
    'actions':   'buttons that run plugin code (audited)',
    'widgets':   'tiles on the dashboard',
    'endpoints': 'read-only JSON under /api/plugins/<id>/endpoints/',
    'hooks':     'run an action when something changes in Floorbit',
    'http':      'outgoing HTTP requests',
    'storage':   'a small private state (64 KB)',
    'documents': 'its own JSON documents (256 KB each, 5 MB in all)',
    'inventory': 'sends devices into the inventory (it never deletes; hand edits win)',
    'mapping':   'sends seat / IP / MAC / nick entries into the seat mapping (hand entries win)',
    'monitoring': 'live switch status, ports and IP to switch port lookups (one plugin at a time)',
    'health': 'service checks on the health wall (DHCP, DNS, cache, game servers, uplink)',
    'ports': 'act on switch ports (bounce, shut, turn on), with the tech\'s own login (one plugin at a time)',
    'security': 'security findings: rogue DHCP, ARP spoofing, MAC flapping, loops and storms',
    'power': 'load readings per circuit from smart PDUs and meters',
    'dns': 'lookups from the event\'s DNS resolver, for hall-wide DNS analytics (never per seat)',
    'wifi': 'access point load and client counts per radio, for the Wi-Fi view (never client names or MACs)',
    'logs': 'keeps the syslog longer (it gets every line) and searches it on the Logs page',
    'brackets': 'tournament brackets from a tournament tool, shown read-only on the bracket view',
    'context_menu': 'entries in the floor plan\'s right-click menu that run one of its actions on a seat or switch',
    'panels':    'a box in the side panel of a seat, a switch or an inventory device',
    'layers':    'a layer on the floor plan that colours the seats (one plugin layer at a time)',
    'pages':     'pages of its own tiles in the sidebar\'s Plugins group',
    'agent': 'runs a part of it on the local agent, in the hall (agent.py; docs/agent-plugins.md)',
}
# Device credential kinds an agent part may ask for (floorbit/plugins/agent.py, CREDENTIAL_KINDS).
CREDENTIAL_KINDS_ALL = ('ssh', 'snmp_v2c', 'snmp_v3', 'api', 'http')
# What a context_menu entry can be on, and the action parameter that carries the target.
MENU_TARGETS = {'seat': 'seat', 'switch': 'switch'}
# What a panel can be on: the plan's seat and switch panels, the inventory's device panel.
PANEL_TARGETS = ('seat', 'switch', 'device')
PANEL_TARGET_MAX = 128
PANEL_KEYS = ('id', 'for', 'label', 'permission', 'role', 'refresh')
# A plan layer: layer_<id>() colours seats with one of these tones, explained by its legend.
LAYER_KEYS = ('id', 'label', 'permission', 'role', 'refresh')
LAYER_TONES = ('ok', 'warn', 'err', 'info')
LAYER_SEATS_MAX = 5000
LAYER_LEGEND_MAX = 8
# A sidebar page: the plugin's own widgets and actions, laid out like a dashboard.
PAGE_KEYS = ('id', 'label', 'permission', 'role', 'widgets', 'actions', 'columns')
PAGE_TILES_MAX = 24
# The methods each data area calls. A plugin must define them all, and only with the area listed.
AREA_METHODS = {
    'inventory': ('inventory',),
    'mapping': ('seat_mapping',),
    'monitoring': ('configured', 'devices', 'device_details', 'resolve_ip', 'port_stats', 'arp', 'device_ports'),
    'health': ('health_checks',),
    'security': ('security_findings',),
    'ports': ('port_login', 'bounce_port', 'set_port'),
    'power': ('power_readings',),
    'dns': ('dns_queries',),
    'logs': ('push_logs', 'query_logs'),
    'wifi': ('wifi_aps',),
    'brackets': ('brackets',),
}
# The methods that talk to the event network. On the Floorbit server they run only through the local
# agent (floorbit/agent_link.py, lan_here): ``call`` refuses them here, so no feature can reach the
# LAN around it. ``configured`` and ``port_login`` only read settings and stay.
LAN_METHODS = frozenset({
    'devices', 'device_details', 'resolve_ip', 'port_stats', 'arp', 'device_ports', 'port_clients', 'neighbours',
    'inventory', 'entries', 'cables', 'firewall_ranges', 'health_checks', 'security_findings', 'seat_mapping',
    'bounce_port', 'set_port', 'send_commands', 'open_shell', 'power_readings', 'dns_queries', 'wifi_aps'})
# Methods a plugin of the area may have but doesn't need: without them the feature says the plugin
# can't do it (switch commands, issue #94; the browser terminal, issue #95).
OPTIONAL_METHODS = {
    'inventory': ('cables',),
    'ports': ('send_commands', 'command_platform', 'open_shell'),
}
# Builtin plugins only: on until an admin turns them off, and settings kept under a core section
# (NetBox's ``netbox.*`` keys and NETBOX_* env variables), so an existing install keeps working;
# ``enable_env`` names a variable that forces it on (FLOORBIT_DEMO for the demo data).
BUILTIN_ONLY = ('default_enabled', 'core_settings', 'enable_env')
# Every key plugin.yaml may have (docs/plugin-spec.md). An unknown key is refused, so a typo or a
# feature this Floorbit doesn't have fails at load, not quietly at run time.
MANIFEST_KEYS = frozenset({
    'id', 'name', 'icon', 'version', 'floorbit', 'description', 'author', 'homepage', 'license', 'uses',
    'settings', 'actions', 'widgets', 'endpoints', 'hooks', 'context_menu', 'agent', 'panels', 'layers', 'pages',
    'schema',
    *BUILTIN_ONLY})
# Agreed in docs/plugin-spec.md but not built yet: refused with a clearer word than "unknown".
MANIFEST_NEXT = ()
# ``schema:``: the version of the data the plugin keeps; ``migrate`` moves older data up to it.
SCHEMA_MAX = 10_000
MIGRATE_SECONDS = 60
MIGRATE_RETRY = 60        # seconds before a failed migration is tried again


def plugin_icons():
    """The names a plugin's ``icon:`` may take: the sidebar's and the inventory's icon sets, which the
    page draws (frontend/src/pages/plugins/icon.ts). Never a file: nothing a plugin ships is drawn as is."""
    from .. import inventory, nav_sections
    return tuple(dict.fromkeys((*nav_sections.ICONS, *inventory.ICONS)))
TRUE_WORDS = ('1', 'true', 'yes', 'on')
# Manifest setting types and the settings page type each becomes.
SETTING_TYPES = {'string': 'text', 'text': 'text', 'url': 'url', 'secret': 'secret', 'bool': 'bool',
                 'int': 'int', 'select': 'choice', 'list': 'list'}
ROLES = ('viewer', 'editor', 'admin')
ROLE_PERMISSION = {'viewer': 'floorplan.view', 'editor': 'plugins.run', 'admin': 'settings.manage'}
# Events a hook can listen to. ``change`` is any audited change (area, action, target, fields),
# ``switch.status`` a switch going offline or coming back (from the status monitor),
# ``health.status`` a service on the health wall changing colour (floorbit/health.py).
# ``security.finding`` a new security finding (floorbit/security.py), ``power.alert`` a circuit
# turning red or tripping (floorbit/power.py).
EVENTS = ('change', 'switch.status', 'health.status', 'security.finding', 'power.alert')
# Hooks run on a few shared threads, not one thread each: a burst of changes (a bulk edit, a
# switch flapping) must not start hundreds of threads. Past HOOK_QUEUE waiting, the oldest go.
HOOK_WORKERS = 4
HOOK_QUEUE = 200
# A tile or an endpoint answers within this, or the request gets an error and the worker is free;
# at most CALLS_PER_PLUGIN of one plugin's run at once, so one stuck plugin can't take every worker.
REQUEST_BUDGET = 10
CALLS_PER_PLUGIN = 4
# plugin.yaml is read before anything is checked: a bigger one is refused unread.
MANIFEST_MAX_BYTES = 256 * 1024
# plugin.py runs when it is loaded; one that doesn't finish (a loop at import, a network call)
# is given up on so Floorbit still starts.
IMPORT_TIMEOUT = 15
# A plugin's own German (locales/de-CH.json): {"English text": "German text"}.
LOCALE_FILE = ('locales', 'de-CH.json')
LOCALE_MAX_BYTES = 256 * 1024
LOCALE_MAX_TEXTS = 2000
# Tests set this to run hooks in the caller's thread, so no hook outlives its test.
HOOKS_INLINE = False
# plugins.json is read for every "is it on?": keep what was read this long (writes refresh it).
STATE_TTL = 2.0


@dataclass
class Spec:
    id: str
    path: Path
    trust: str
    manifest: dict = field(default_factory=dict)
    module: object = None
    error: str = ''
    german: tuple = None     # its locales/de-CH.json, compiled (floorbit.i18n.compile_texts)

    @property
    def name(self):
        return self.manifest.get('name', self.id)

    @property
    def uses(self):
        return list(self.manifest.get('uses') or [])

    def items(self, kind):
        return [i for i in self.manifest.get(kind) or [] if isinstance(i, dict)]

    def item(self, kind, item_id):
        return next((i for i in self.items(kind) if i.get('id') == item_id), None)

    @property
    def agent(self):
        """The manifest's ``agent:`` block (floorbit/plugins/agent.py), or None."""
        block = self.manifest.get('agent') if 'agent' in self.uses else None
        return block if isinstance(block, dict) else None

    def plugin_class(self):
        cls = getattr(self.module, 'Plugin', None) if self.module else None
        return cls if isinstance(cls, type) and issubclass(cls, Plugin) else None


# ── Manifest checks ─────────────────────────────────────────────────────────────────────

def _version(text):
    return tuple(int(p) for p in re.findall(r'\d+', str(text))[:3]) or (0,)


def compatible(requirement, current):
    """``floorbit: ">=0.1,<2"``: comparisons separated by commas. Empty: assumed to work."""
    if not requirement:
        return True, ''
    cur = _version(current)
    for part in str(requirement).split(','):
        m = re.match(r'^\s*(>=|<=|==|!=|>|<)\s*([\d.]+)\s*$', part)
        if not m:
            return False, f"floorbit: '{requirement}' isn't a version range like '>=0.1,<2'"
        op, want = m.group(1), _version(m.group(2))
        n = max(len(cur), len(want))
        a, b = cur + (0,) * (n - len(cur)), want + (0,) * (n - len(want))
        ok = {'>=': a >= b, '<=': a <= b, '==': a == b, '!=': a != b, '>': a > b, '<': a < b}[op]
        if not ok:
            return False, f'needs Floorbit {requirement}, this is {current}'
    return True, ''


def _check_fields(fields, where):
    keys = set()
    if fields is not None and not isinstance(fields, list):
        return f'{where}: a list of fields'
    for f in fields or []:
        if not isinstance(f, dict) or not _name(f.get('key')):
            return f'{where}: bad key {f!r}'
        if not isinstance(f.get('type', 'string'), str) or f.get('type', 'string') not in SETTING_TYPES:
            return f"{where}.{f['key']}: type must be one of {', '.join(SETTING_TYPES)}"
        if f.get('type') == 'select' and not f.get('options'):
            return f"{where}.{f['key']}: a select needs options"
        if f['key'] in keys:
            return f"{where}.{f['key']}: duplicate"
        keys.add(f['key'])
    return ''


def _name(value):
    return isinstance(value, str) and bool(NAME_RE.match(value))


def validate(m):
    """An error message, or '' when the manifest is fine. No plugin code runs here."""
    try:
        return _validate(m)
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        # A value of a type no check above expected (YAML gives lists, maps, floats anywhere): the
        # plugin's own error, never an exception while Floorbit loads its plugins.
        return f'plugin.yaml: a value has the wrong type ({type(exc).__name__}: {exc})'


def _validate(m):
    if not isinstance(m, dict):
        return 'plugin.yaml must be a mapping'
    if not ID_RE.match(str(m.get('id', ''))):
        return 'id: 2 to 40 lowercase letters, digits and dashes, starting with a letter'
    if m['id'] == 'floorbit':
        return 'id: "floorbit" is taken by Floorbit\'s own dashboard tiles'
    extra = sorted(str(k) for k in m if k not in MANIFEST_KEYS)
    if extra:
        later = [k for k in extra if k in MANIFEST_NEXT]
        if later:
            return f"{', '.join(later)}: not supported by this Floorbit yet (docs/plugin-spec.md)"
        return f"unknown key(s) {', '.join(extra)} (docs/plugin-spec.md lists what plugin.yaml may have)"
    if 'icon' in m and m['icon'] not in plugin_icons():
        return f"icon: one of {', '.join(plugin_icons())}"
    if 'schema' in m:
        schema = m['schema']
        if isinstance(schema, bool) or not isinstance(schema, int) or not 1 <= schema <= SCHEMA_MAX:
            return f'schema: a whole number from 1 to {SCHEMA_MAX}'
    uses = m.get('uses')
    if not isinstance(uses, list) or not uses:
        return f"uses: list the areas the plugin extends ({', '.join(AREAS)})"
    unknown = [u for u in uses if not isinstance(u, str) or u not in AREAS]
    if unknown:
        return f"uses: unknown area(s) {', '.join(map(str, unknown))}"
    needs = {'settings': 'settings', 'actions': 'actions', 'widgets': 'widgets',
             'endpoints': 'endpoints', 'hooks': 'hooks', 'context_menu': 'context_menu', 'panels': 'panels',
             'layers': 'layers', 'pages': 'pages'}
    for key, area in needs.items():
        if m.get(key) and area not in uses:
            return f'{key}: the plugin has {key} but "{area}" is not under uses:'
    if 'schema' in m and not {'documents', 'storage'} & set(uses):
        return 'schema: the plugin keeps no data ("documents" or "storage" under uses:)'
    err = _check_fields(m.get('settings'), 'settings')
    if err:
        return err
    for kind in ('actions', 'widgets', 'endpoints', 'panels', 'layers', 'pages'):
        ids = set()
        items = m.get(kind) or []
        if not isinstance(items, list):
            return f'{kind}: a list of entries'
        for item in items:
            if not isinstance(item, dict) or not _name(item.get('id')):
                return f'{kind}: bad id {item!r}'
            if item['id'] in ids:
                return f"{kind}.{item['id']}: duplicate"
            ids.add(item['id'])
            role = item.get('role', 'admin' if kind == 'actions' else 'viewer')
            if not isinstance(role, str) or role not in ROLES or (kind == 'actions' and role == 'viewer'):
                return f"{kind}.{item['id']}: role must be " + ('editor or admin' if kind == 'actions'
                                                               else 'viewer, editor or admin')
            item['role'] = role
            # The permission it needs (auth/roles.py). Older manifests name a role; it maps across.
            permission = item.get('permission') or ROLE_PERMISSION[role]
            from auth.roles import PERMISSIONS
            if not isinstance(permission, str) or permission not in PERMISSIONS:
                return f"{kind}.{item['id']}: unknown permission {permission!r}"
            item['permission'] = permission
            if item.get('label') is None:     # missing, or "label:" left empty
                item['label'] = item['id'].replace('_', ' ').capitalize()
            # Drawn as text on every page that lists it: a list or a map would break the page.
            if not isinstance(item['label'], str) or not 1 <= len(item['label']) <= 80:
                return f"{kind}.{item['id']}: label is text, 1 to 80 characters"
            if kind == 'actions':
                err = _check_fields(item.get('params'), f"actions.{item['id']}.params")
                if err:
                    return err
            if kind == 'panels':
                # A new kind, so a typo ("permision:") fails here instead of leaving the panel open.
                extra = sorted(str(k) for k in item if k not in PANEL_KEYS)
                if extra:
                    return f"panels.{item['id']}: unknown key(s) {', '.join(extra)}"
                # Not "on:": YAML reads that key as true.
                if item.get('for') not in PANEL_TARGETS:
                    return f"panels.{item['id']}: for must be one of {', '.join(PANEL_TARGETS)}"
                refresh = _refresh(item.get('refresh'))
                if refresh is None:
                    return f"{kind}.{item['id']}: refresh is a whole number of seconds, 10 to {REFRESH_MAX}"
                item['refresh'] = refresh
            if kind == 'pages':
                extra = sorted(str(k) for k in item if k not in PAGE_KEYS)
                if extra:
                    return f"pages.{item['id']}: unknown key(s) {', '.join(extra)}"
                tiles = 0
                for listed, known in (('widgets', m.get('widgets')), ('actions', m.get('actions'))):
                    names = item.get(listed) or []
                    have = {w.get('id') for w in known or [] if isinstance(w, dict)}
                    if not isinstance(names, list) or any(not isinstance(n, str) or n not in have for n in names):
                        return f"pages.{item['id']}.{listed}: only ids from the plugin's own {listed}:"
                    tiles += len(names)
                if not 1 <= tiles <= PAGE_TILES_MAX:
                    return f"pages.{item['id']}: 1 to {PAGE_TILES_MAX} widgets and actions"
                columns = item.get('columns', 2)
                if isinstance(columns, bool) or columns not in (1, 2, 3):
                    return f"pages.{item['id']}: columns is 1, 2 or 3"
                item['columns'] = columns
            if kind == 'layers':
                extra = sorted(str(k) for k in item if k not in LAYER_KEYS)
                if extra:
                    return f"layers.{item['id']}: unknown key(s) {', '.join(extra)}"
                refresh = _refresh(item.get('refresh'))
                if refresh is None:
                    return f"{kind}.{item['id']}: refresh is a whole number of seconds, 10 to {REFRESH_MAX}"
                item['refresh'] = refresh
            if kind == 'widgets':
                if item.get('size', 'small') not in ('small', 'wide'):
                    return f"widgets.{item['id']}: size must be small or wide"
                refresh = _refresh(item.get('refresh'))
                if refresh is None:
                    return f"{kind}.{item['id']}: refresh is a whole number of seconds, 10 to {REFRESH_MAX}"
                item['refresh'] = refresh
    actions = {a['id'] for a in m.get('actions') or []}
    from .agent import check_agent_block
    err = check_agent_block(m)
    if err:
        return err
    err = _check_menu(m)
    if err:
        return err
    for h in m.get('hooks') or []:
        if not isinstance(h, dict) or h.get('action') not in actions:
            return f'hooks: unknown action {h!r}'
        events = h.get('events') or []
        if not events or any(e not in EVENTS for e in events):
            return f"hooks: events must be some of {', '.join(EVENTS)}"
    return ''


def check_layer(raw):
    """What ``layer_<id>()`` returned, cut to what the plan draws; WidgetError when it isn't that."""
    if not isinstance(raw, dict):
        raise WidgetError('a layer is {"seats": {seat: {"tone", "label"}}, "legend": [...]}')
    given = {} if raw.get('seats') is None else raw['seats']
    shown = [] if raw.get('legend') is None else raw['legend']
    if not isinstance(given, dict) or not isinstance(shown, list):
        raise WidgetError('a layer is {"seats": {seat: {"tone", "label"}}, "legend": [...]}')
    seats = {}
    for key, value in list(given.items())[:LAYER_SEATS_MAX]:
        if not isinstance(key, str) or not 1 <= len(key) <= PANEL_TARGET_MAX or not key.isprintable():
            raise WidgetError(f'a seat id is 1 to {PANEL_TARGET_MAX} printable characters')
        if not isinstance(value, dict) or value.get('tone') not in LAYER_TONES:
            raise WidgetError(f"seat {key}: tone must be one of {', '.join(LAYER_TONES)}")
        seats[key] = {'tone': value['tone'], 'label': str(value.get('label') or '')[:60]}
    legend = []
    for item in shown[:LAYER_LEGEND_MAX]:
        if not isinstance(item, dict) or item.get('tone') not in LAYER_TONES:
            raise WidgetError(f"legend: tone must be one of {', '.join(LAYER_TONES)}")
        legend.append({'tone': item['tone'], 'label': str(item.get('label') or '')[:60]})
    return {'seats': seats, 'legend': legend}


def touches(m):
    """What a plugin may touch, from its (validated) manifest: what the Marketplace shows before it
    is installed (docs/plugin-spec.md, "Permissions it asks for")."""
    agent = m.get('agent') if 'agent' in (m.get('uses') or []) and isinstance(m.get('agent'), dict) else {}
    permissions = {i.get('permission') for kind in ('actions', 'widgets', 'endpoints', 'panels', 'layers', 'pages')
                   for i in m.get(kind) or [] if isinstance(i, dict) and i.get('permission')}
    targets = agent.get('targets') if isinstance(agent.get('targets'), dict) else None
    return {
        'uses': [u for u in m.get('uses') or [] if u in AREAS],
        'permissions': sorted(permissions),
        'secrets': sum(1 for f in m.get('settings') or [] if isinstance(f, dict) and f.get('type') == 'secret'),
        'sends': {str(k): (v or {}).get('privacy', 'aggregate') for k, v in (agent.get('sends') or {}).items()},
        'hall_actions': list(agent.get('actions') or []),
        'credentials': (list(targets.get('credentials') or ['any']) if targets else []),
    }


REFRESH_MAX = 24 * 3600


def _refresh(value):
    """A tile's, panel's or layer's ``refresh``: seconds, at least 10 and at most a day; None when
    it is no whole number. Read from plugin.yaml, so anything can be there ("fast", 1e999)."""
    if value is None:
        return 60
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return min(max(10, value), REFRESH_MAX)


def _count(value, most):
    """A small count from an index: 0 to ``most``; 0 for anything that isn't a whole number."""
    return min(max(0, value), most) if isinstance(value, int) and not isinstance(value, bool) else 0


def clean_touches(raw):
    """``touches`` as an index lists it, cut to what Floorbit shows; None when there is none."""
    if not isinstance(raw, dict):
        return None
    names = re.compile(r'^[a-z][a-z0-9_.]{0,59}\Z')

    def listed(key, allowed=None):
        items = raw.get(key) if isinstance(raw.get(key), list) else []
        return [str(i) for i in items[:40] if names.match(str(i)) and (allowed is None or i in allowed)]
    from auth.roles import PERMISSIONS
    sends = raw.get('sends') if isinstance(raw.get('sends'), dict) else {}
    return {'uses': listed('uses', AREAS), 'permissions': listed('permissions', PERMISSIONS),
            'secrets': _count(raw.get('secrets'), 99),
            'sends': {str(k): v for k, v in list(sends.items())[:40]
                      if names.match(str(k)) and v in ('aggregate', 'device')},
            'hall_actions': listed('hall_actions'),
            'credentials': listed('credentials', (*CREDENTIAL_KINDS_ALL, 'any'))}


def _check_menu(m):
    """context_menu entries: an action of the plugin, on seats and/or switches, which takes the target."""
    entries = m.get('context_menu') or []
    if not isinstance(entries, list):
        return 'context_menu: a list of entries'
    actions = {a['id']: a for a in m.get('actions') or [] if isinstance(a, dict)}
    for entry in entries:
        action = actions.get(entry.get('action')) if isinstance(entry, dict) else None
        if action is None:
            return f'context_menu: unknown action {entry!r}'
        # "targets", not "on": YAML reads a bare on as true.
        on = entry.get('targets')
        on = [on] if isinstance(on, str) else on
        if not isinstance(on, list) or not on or any(t not in MENU_TARGETS for t in on):
            return f"context_menu.{action['id']}: targets must be seat, switch or both"
        params = {f.get('key') for f in action.get('params') or []}
        missing = [MENU_TARGETS[t] for t in on if MENU_TARGETS[t] not in params]
        if missing:
            return f"context_menu.{action['id']}: the action needs a {' and a '.join(missing)} parameter"
        entry['targets'] = on
        entry.setdefault('label', action['label'])
        if not isinstance(entry['label'], str) or not 1 <= len(entry['label']) <= 60:
            return f"context_menu.{action['id']}: label is 1 to 60 characters"
    return ''


def _check_methods(spec):
    """Hubra-style limits on the code: every public method must belong to something listed."""
    cls = spec.plugin_class()
    if cls is None:
        return 'plugin.py has no class Plugin(floorbit.plugins.base.Plugin)' if spec.module else ''
    allowed = {f"run_{a['id']}" for a in spec.items('actions')}
    allowed |= {f"widget_{w['id']}" for w in spec.items('widgets')}
    allowed |= {f"endpoint_{e['id']}" for e in spec.items('endpoints')}
    allowed |= {f"panel_{p['id']}" for p in spec.items('panels')}
    allowed |= {f"layer_{p['id']}" for p in spec.items('layers')}
    allowed |= {'test'}
    optional = set()
    for table in (AREA_METHODS, OPTIONAL_METHODS):
        for area, methods in table.items():
            for method in methods:
                if area in spec.uses:
                    (allowed if table is AREA_METHODS else optional).add(method)
                elif callable(getattr(cls, method, None)):
                    return f'plugin.py: {method}() needs "{area}" under uses:'
    has_migrate = callable(getattr(cls, 'migrate', None))
    if spec.manifest.get('schema') and not has_migrate:
        return 'plugin.py: plugin.yaml has schema:, but Plugin has no migrate(from_schema, store)'
    if has_migrate and not spec.manifest.get('schema'):
        return 'plugin.py: migrate() needs schema: in plugin.yaml'
    kinds = set((spec.agent or {}).get('sends') or {})
    fetches = set((spec.agent or {}).get('fetches') or [])
    for name in dir(cls):
        if not name.startswith('agent_') or name == 'agent_settings' or not callable(getattr(cls, name, None)):
            pass
        elif name.startswith('agent_get_'):
            if name[10:] not in fetches:
                return f'plugin.py: {name}() answers the agent, but agent.fetches has no {name[10:]}'
        elif name[6:] not in kinds:
            return f'plugin.py: {name}() takes what the agent sends, but agent.sends has no {name[6:]}'
        if name.startswith(('run_', 'widget_', 'endpoint_', 'panel_', 'layer_')) and name not in allowed:
            return f'plugin.py: {name} has no matching entry in plugin.yaml'
    for name in sorted(allowed - {'test'}):
        if not callable(getattr(cls, name, None)):
            return f'plugin.py: plugin.yaml lists it, but Plugin has no {name}()'
    for kind in sorted(fetches):
        if not callable(getattr(cls, f'agent_get_{kind}', None)):
            return f'plugin.py: agent.fetches lists {kind}, but Plugin has no agent_get_{kind}()'
    return ''


def _load_german(spec, path):
    """Read and check the plugin's locales/de-CH.json into spec.german. An error message or ''."""
    import json

    from .. import i18n
    f = path.joinpath(*LOCALE_FILE)
    if not f.is_file():
        return ''
    where = '/'.join(LOCALE_FILE)
    try:
        if f.stat().st_size > LOCALE_MAX_BYTES:
            return f'{where} is larger than {LOCALE_MAX_BYTES // 1024} KB'
        texts = json.loads(f.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return f'{where}: {exc}'
    if (not isinstance(texts, dict) or len(texts) > LOCALE_MAX_TEXTS
            or not all(isinstance(k, str) and isinstance(v, str) and len(k) <= 2000 and len(v) <= 2000
                       for k, v in texts.items())):
        return f'{where}: an object of up to {LOCALE_MAX_TEXTS} "English": "German" texts'
    for english, german in texts.items():
        if english.count('{}') != len(re.findall(r'\{\d*\}', german)):
            return f'{where}: {english!r} and its German have a different number of {{}}'
    spec.german = i18n.compile_texts(texts)
    return ''


def _load(path, trust, current_version):
    import importlib.util
    import sys

    import yaml

    mf = path / 'plugin.yaml'
    if not mf.is_file():
        return None
    spec = Spec(id=path.name, path=path, trust=trust)
    try:
        if mf.stat().st_size > MANIFEST_MAX_BYTES:
            spec.error = f'plugin.yaml is larger than {MANIFEST_MAX_BYTES // 1024} KB'
            return spec
        spec.manifest = yaml.safe_load(mf.read_text(encoding='utf-8')) or {}
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        spec.error = f'plugin.yaml: {exc}'
        return spec
    spec.id = str(spec.manifest.get('id', path.name)) if isinstance(spec.manifest, dict) else path.name
    spec.error = validate(spec.manifest)
    if spec.error:
        return spec
    extra = [k for k in BUILTIN_ONLY if spec.manifest.get(k)]
    if extra and trust != 'builtin':
        spec.error = f"{', '.join(extra)}: only for plugins that ship with Floorbit"
        return spec
    ok, why = compatible(spec.manifest.get('floorbit'), current_version)
    if not ok:
        spec.error = why
        return spec
    spec.error = _load_german(spec, path)
    if spec.error:
        return spec
    py = path / 'plugin.py'
    if py.is_file():
        modname = f"floorbit_plugin_{spec.id.replace('-', '_')}"
        box = {}

        def run():
            try:
                sp = importlib.util.spec_from_file_location(modname, py)
                mod = importlib.util.module_from_spec(sp)
                sys.modules[modname] = mod
                sp.loader.exec_module(mod)
                box['module'] = mod
            # BaseException too: a sys.exit() at import must not stop Floorbit.
            except BaseException as exc:  # noqa: BLE001  # a broken plugin must not take Floorbit down
                box['error'] = exc
        loader = threading.Thread(target=run, daemon=True, name=f'plugin-{spec.id}-import')
        loader.start()
        loader.join(IMPORT_TIMEOUT)
        if loader.is_alive():
            spec.error = f'plugin.py did not finish loading within {IMPORT_TIMEOUT} s'
            return spec
        if 'error' in box:
            exc = box['error']
            sys.modules.pop(modname, None)
            spec.error = f'plugin.py: {type(exc).__name__}: {exc}'
            return spec
        spec.module = box['module']
    agent = spec.agent
    if agent and not (path / agent['module']).is_file():
        spec.error = f"agent.module: {agent['module']} is missing"
        return spec
    spec.error = _check_methods(spec)
    return spec


# ── Registry ────────────────────────────────────────────────────────────────────────────

class Registry:
    """The loaded plugins, which of them are on, their settings and their state."""

    def __init__(self, settings_store, current_version='0', dirs=None):
        self.settings_store = settings_store
        self.version = current_version
        self.specs = {}
        self.logs = LogBuffer()
        self._lock = threading.Lock()
        self._cache = None             # (read at, path, data) of plugins.json
        self._writes = 0               # bumped by every change: a read that overlapped one isn't kept
        self._hooks = deque()
        self._hooks_cv = threading.Condition()
        self._hook_threads = 0
        self.hooks_dropped = 0
        self._busy = {}                # plugin id -> calls running within REQUEST_BUDGET
        self._busy_lock = threading.Lock()
        self._migrating = {}           # plugin id -> lock, one migration at a time
        self._migrate_failed = {}      # (plugins.json path, id, schema) -> (when, message)
        if dirs is None:
            dirs = [(BUILTIN_DIR, 'builtin')]
            dev = os.environ.get(DEV_ENV, '').strip()
            if dev:
                print(f'[plugins] Loading development plugins from {dev} ({DEV_ENV}). Never set this in production.')
                dirs.append((Path(dev), 'development'))
        for base, trust in dirs:
            if not base or not Path(base).is_dir():
                continue
            for sub in sorted(p for p in Path(base).iterdir() if p.is_dir() and not p.name.startswith(('_', '.'))):
                spec = _load(sub, trust, current_version)
                if spec is None:
                    continue
                if spec.id in self.specs:
                    spec.error = f'a plugin with id {spec.id} is already loaded'
                    spec.id = f'{spec.id}@{sub.name}'
                self.specs[spec.id] = spec
        self._register_settings()

    # Marketplace plugins (floorbit/marketplace.py) come and go while Floorbit runs --------
    def add(self, path, trust):
        """Load one plugin folder, replacing an installed one with the same id. Returns its Spec."""
        spec = _load(Path(path), trust, self.version)
        if spec is None:
            spec = Spec(id=Path(path).name, path=Path(path), trust=trust, error='plugin.yaml is missing')
        cur = self.specs.get(spec.id)
        if cur is not None and cur.trust in ('builtin', 'development'):
            spec.error = f'a plugin with id {spec.id} ships with this Floorbit'
            return spec
        # A new dict, never a change to the one in use: requests and hooks iterate it meanwhile.
        self.specs = {**self.specs, spec.id: spec}
        self._register_settings()
        return spec

    def drop(self, plugin_id):
        """Forget an installed plugin (its settings and state stay, for a later install)."""
        spec = self.specs.get(plugin_id)
        if spec is not None and spec.trust not in ('builtin', 'development'):
            self.specs = {k: v for k, v in self.specs.items() if k != plugin_id}

    # settings ------------------------------------------------------------------------------
    def _register_settings(self):
        from .. import settings as settings_module
        known = {s['id'] for s in settings_module.SECTIONS}
        for spec in self.specs.values():
            if spec.error or not spec.items('settings'):
                continue
            section = f'plugin-{spec.id}'
            if section not in known:
                settings_module.SECTIONS.append({
                    'id': section, 'title': f'Plugin: {spec.name}', 'plugin': spec.id,
                    'description': spec.manifest.get('description', '')})
            for f in spec.items('settings'):
                key = f"plugin.{spec.id}.{f['key']}"
                if key in settings_module.FIELDS_BY_KEY:
                    continue
                ftype = SETTING_TYPES[f.get('type', 'string')]
                default = f.get('default', [] if ftype == 'list' else False if ftype == 'bool' else
                                0 if ftype == 'int' else '')
                field_def = dict(
                    key=key, section=section, label=f.get('label') or f['key'].replace('_', ' ').capitalize(),
                    type=ftype, default=default, help=f.get('help'), placeholder=f.get('placeholder'),
                    # A plugin never picks which env var it reads (SECRET_KEY, other tokens): the name is fixed.
                    env=f"FLOORBIT_PLUGIN_{spec.id}_{f['key']}".upper().replace('-', '_'))
                if ftype == 'choice':
                    field_def['options'] = [o if isinstance(o, dict) else {'value': str(o), 'label': str(o)}
                                            for o in f['options']]
                if ftype == 'int':
                    field_def['min'], field_def['max'] = f.get('min', 0), f.get('max', 10 ** 9)
                settings_module.FIELDS.append(field_def)
                settings_module.FIELDS_BY_KEY[key] = field_def
        self.settings_store.reload()

    def _core_fields(self, spec):
        from .. import settings as settings_module
        section = spec.manifest.get('core_settings')
        return [f['key'] for f in settings_module.FIELDS if f['section'] == section] if section else []

    def settings_of(self, spec):
        out = {}
        for key in self._core_fields(spec):
            out[key.split('.', 1)[1]] = self.settings_store.get(key)
        for f in spec.items('settings'):
            out[f['key']] = self.settings_store.get(f"plugin.{spec.id}.{f['key']}")
        return out

    # on/off and state: plugins.json next to data.json (or PLUGINS_FILE) ------------------
    # Its own file, written whole and swapped in, so a hook writing state in the background
    # never races a request writing data.json.
    def path(self):
        from .. import store
        configured = os.environ.get('PLUGINS_FILE')
        return store.tenant_file(configured) if configured else store.tenant_path('plugins.json')

    def _all(self, path=None, strict=False):
        """Every plugin's saved state. While the database is away with no copy read yet, none
        (each plugin's defaults), so the background polls keep going; ``strict`` for a change,
        which must never start from that."""
        from .. import database, store
        path = path or self.path()
        cached = self._cache
        if not strict and cached and cached[1] == path and time.monotonic() - cached[0] < STATE_TTL:
            return cached[2]
        writes = self._writes
        try:
            data = store.read_json(path, {})
            data = data if isinstance(data, dict) else {}
            # A change saved while this read was on its way would be hidden for STATE_TTL by the
            # older copy: a plugin just turned on read as off ("No port actions plugin is on").
            if self._writes == writes:
                self._cache = (time.monotonic(), path, data)
            return data
        except database.DatabaseUnavailable:
            if strict:
                raise
            return {}
        except (OSError, ValueError) as exc:
            print(f'[plugins] could not read {path}: {exc}')
            return {}

    def _all_shared(self):
        """``_all()`` for the hot reads (is this plugin on?), parsed once per change. Shared: read only."""
        from .. import database, store
        try:
            data = store.read_shared(self.path(), {})
            return data if isinstance(data, dict) else {}
        except database.DatabaseUnavailable:
            return {}
        except (OSError, ValueError) as exc:
            print(f'[plugins] could not read {self.path()}: {exc}')
            return {}

    def _record(self, plugin_id):
        return self._all().get(plugin_id) or {}

    def _update(self, plugin_id, **changes):
        with self._lock:
            self._update_locked(plugin_id, **changes)

    def _update_locked(self, plugin_id, **changes):
        import json
        import tempfile
        path = self.path()   # once: read and write the same file
        data = self._all(path, strict=True)
        data = json.loads(json.dumps(data, default=str))   # a copy: the cached one stays as read
        data.setdefault(plugin_id, {}).update(json.loads(json.dumps(changes, default=str)))
        from .. import database, store
        self._writes += 1
        self._cache = None
        if database.backend().kind != 'files':
            store.write_json(path, data)
            self._writes += 1      # again: a read that began after the first bump may hold the old file
            self._cache = (time.monotonic(), path, data)
            return
        folder = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(dir=folder, prefix='.plugins-', suffix='.json')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, path)
            self._writes += 1
            self._cache = (time.monotonic(), path, data)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def enabled(self, spec):
        if spec.error:
            return False
        env = spec.manifest.get('enable_env') if spec.trust == 'builtin' else None
        if env and os.environ.get(str(env), '').strip().lower() in TRUE_WORDS:
            return True
        record = self._all_shared().get(spec.id) or {}
        if 'enabled' in record:
            return bool(record['enabled'])
        return bool(spec.trust == 'builtin' and spec.manifest.get('default_enabled'))

    def set_enabled(self, plugin_id, on):
        spec = self.specs.get(plugin_id)
        if spec is None:
            raise KeyError(plugin_id)
        if on and spec.error:
            raise PluginError(f'{spec.name} has an error and can\'t be turned on: {spec.error}')
        self._update(plugin_id, enabled=bool(on))

    def state_of(self, plugin_id):
        return self._record(plugin_id).get('state') or {}

    def save_state(self, plugin_id, state):
        self._update(plugin_id, state=state)

    def set_state_key(self, plugin_id, key, value, limit):
        """One key of the plugin's state, read and written under the lock from a fresh read, so
        two hooks setting different keys at once don't undo each other."""
        import json
        with self._lock:
            state = dict((self._all(strict=True).get(plugin_id) or {}).get('state') or {})
            state[str(key)] = value
            if len(json.dumps(state, default=str)) > limit:
                raise PluginError(f'Plugin state is limited to {limit // 1024} KB')
            self._update_locked(plugin_id, state=state)

    def log(self, plugin_id, line):
        self.logs.add(plugin_id, line)

    def text(self, spec, text, lang):
        """One of the plugin's texts in ``lang``: from its own locales/de-CH.json, else from
        Floorbit's catalog (shared words: "Up", "Down"), else as it is."""
        from .. import i18n
        if not isinstance(text, str) or not lang or lang == 'en':
            return text
        if spec is not None and spec.german:
            german = i18n.translate_in(text, lang, spec.german, fallback=False)
            if german is not None:
                return german
        return i18n.translate(text, lang)

    def settings_texts(self, sections, fields, accept_language):
        """The settings page's sections and fields with the plugins' labels, help and placeholders
        in the request's language (copies; Floorbit's own ones are left to the page)."""
        from .. import i18n
        lang = i18n.language(accept_language)
        if lang == 'en':
            return sections, fields

        def spec_of(section_id):
            return self.specs.get(section_id[7:]) if str(section_id).startswith('plugin-') else None
        out_sections = [({**s, 'title': f"Plugin: {self.text(spec_of(s['id']), spec_of(s['id']).name, lang)}",
                          'description': self.text(spec_of(s['id']), s.get('description'), lang)}
                         if spec_of(s['id']) else s) for s in sections]
        out_fields = []
        for f in fields:
            spec = spec_of(f.get('section', ''))
            if spec is not None:
                f = {**f, **{k: self.text(spec, f[k], lang) for k in ('label', 'help', 'placeholder')
                             if isinstance(f.get(k), str)}}
            out_fields.append(f)
        return out_sections, out_fields

    def require(self, spec, area):
        if area not in spec.uses:
            raise PluginError(f'{spec.name} uses {area} without listing it under uses: in plugin.yaml')

    # calls ---------------------------------------------------------------------------------
    def active(self, plugin_id):
        spec = self.specs.get(plugin_id)
        return spec if spec and self.enabled(spec) else None

    def reaches_lan(self, spec):
        """Does the plugin talk to the event network (has any of LAN_METHODS)?"""
        cls = spec.plugin_class()
        return cls is not None and any(callable(getattr(cls, m, None)) for m in LAN_METHODS)

    def call(self, spec, method, *args):
        """Run one plugin method. PluginError messages are shown; anything else is logged."""
        cls = spec.plugin_class()
        if cls is None:
            raise PluginError(f'{spec.name} has no code for this')
        if method in LAN_METHODS:
            from .. import agent_link
            if not agent_link.may_call_here(spec):
                raise PluginError(f'{spec.name} runs on the local agent: Floorbit reaches the event network '
                                  'only through it.')
        if method != 'migrate':
            self.ensure_schema(spec)
        try:
            return getattr(cls(Context(spec, self)), method)(*args)
        except PluginError:
            raise
        # BaseException too: a plugin's sys.exit() would otherwise end the worker serving the request.
        except BaseException as exc:
            if isinstance(exc, GeneratorExit):
                raise
            self.log(spec.id, f'{method} failed: ' + ''.join(traceback.format_exception_only(exc)).strip())
            raise PluginError(f'{spec.name} failed ({type(exc).__name__}); details are in its log') from None

    def schema_of(self, plugin_id):
        """The schema this tenant's data of the plugin is at (0: never migrated)."""
        value = self._record(plugin_id).get('schema')
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def ensure_schema(self, spec):
        """Move this tenant's data of the plugin up to its ``schema:`` before any other code of it
        runs: ``migrate(from_schema, store)``, once, within MIGRATE_SECONDS. A failure leaves the
        data marked at the old schema and the plugin refusing to run here (tried again after
        MIGRATE_RETRY); data at a newer schema than the plugin knows is never handed to it."""
        want = spec.manifest.get('schema') or 0
        if not want or self.schema_of(spec.id) == want:
            return
        key = (self.path(), spec.id, want)
        failed = self._migrate_failed.get(key)
        if failed and time.monotonic() - failed[0] < MIGRATE_RETRY:
            raise PluginError(failed[1])
        with self._busy_lock:
            lock = self._migrating.setdefault(spec.id, threading.Lock())
        with lock:
            from .. import database
            try:
                record = self._all(strict=True).get(spec.id) or {}
            except database.DatabaseUnavailable:
                raise PluginError(f"{spec.name} waits for Floorbit's database to move its data") from None
            have = record.get('schema') if isinstance(record.get('schema'), int) else 0
            if have == want:
                return
            if have > want:
                raise PluginError(f"{spec.name} {spec.manifest.get('version', '')} knows its data up to schema "
                                  f'{want}, but the data here is at schema {have}: install a newer version')
            from .documents import Store
            try:
                self.timed(spec, 'migrate', have, Store(spec, self), timeout=MIGRATE_SECONDS)
            except PluginError as exc:
                message = f'{spec.name} could not move its data from schema {have} to {want}: {exc}'
                self.log(spec.id, message)
                self._migrate_failed[key] = (time.monotonic(), message)
                raise PluginError(message) from None
            self._update(spec.id, schema=want)
            self._migrate_failed.pop(key, None)
            self.log(spec.id, f'moved its data from schema {have} to {want}')

    def timed(self, spec, method, *args, timeout=None):
        """``call`` for a request that waits on it: an answer within ``timeout`` or a PluginError.

        The call runs on its own thread with the request's context (tenant, event, app), so a
        plugin that hangs costs one thread, not the request's worker; past CALLS_PER_PLUGIN of the
        same plugin, the next is refused at once instead of piling up."""
        timeout = REQUEST_BUDGET if timeout is None else timeout
        with self._busy_lock:
            if self._busy.get(spec.id, 0) >= CALLS_PER_PLUGIN:
                raise PluginError(f'{spec.name} is still busy with earlier requests; try again shortly')
            self._busy[spec.id] = self._busy.get(spec.id, 0) + 1
        done = threading.Event()
        box = {}
        ctx = contextvars.copy_context()

        def run():
            try:
                box['value'] = ctx.run(self.call, spec, method, *args)
            except BaseException as exc:  # noqa: BLE001  # handed to the waiting request
                box['error'] = exc
            finally:
                with self._busy_lock:
                    self._busy[spec.id] = max(0, self._busy.get(spec.id, 1) - 1)
                done.set()
        threading.Thread(target=run, daemon=True, name=f'plugin-{spec.id}-call').start()
        if not done.wait(timeout):
            self.log(spec.id, f'{method} took longer than {timeout} s; the request gave up on it')
            raise PluginError(f'{spec.name} did not answer within {timeout} s')
        if 'error' in box:
            raise box['error']
        return box.get('value')

    def widget(self, spec, widget_id):
        item = spec.item('widgets', widget_id)
        try:
            return check_widget(self.timed(spec, f'widget_{widget_id}'), item)
        except WidgetError as exc:
            self.log(spec.id, f'widget {widget_id}: {exc}')
            raise PluginError(f'{spec.name} returned a widget Floorbit can\'t draw') from None

    def panel(self, spec, panel_id, target):
        """The panel's widget for one seat, switch or device (``target``: its id). Drawn like a tile."""
        item = spec.item('panels', panel_id)
        try:
            return check_widget(self.timed(spec, f'panel_{panel_id}', {'kind': item['for'], 'id': target}), item)
        except WidgetError as exc:
            self.log(spec.id, f'panel {panel_id}: {exc}')
            raise PluginError(f'{spec.name} returned a widget Floorbit can\'t draw') from None

    def layer(self, spec, layer_id):
        """The layer's seats and legend, checked: ``{seats: {id: {tone, label}}, legend: [{tone, label}]}``."""
        try:
            return check_layer(self.timed(spec, f'layer_{layer_id}'))
        except WidgetError as exc:
            self.log(spec.id, f'layer {layer_id}: {exc}')
            raise PluginError(f'{spec.name} returned a layer Floorbit can\'t draw') from None

    def feeders(self, area):
        """The plugins that are on and feed this area (``inventory``), in id order."""
        return [s for s in self.specs.values() if area in s.uses and self.enabled(s)]

    def monitoring_source(self):
        """The monitoring plugin in use: the first one that is on and set up, in id order (or None).

        LibreNMS is on by default, so a hall that switched to Prometheus would otherwise still ask an
        empty LibreNMS. Only one is used at a time: a mix of two sources would be nonsense.
        """
        found = self.feeders('monitoring')

        def set_up(spec):
            try:
                return bool(self.call(spec, 'configured'))
            except PluginError:
                return False
        # Demo data, once on, replaces the live source.
        found.sort(key=lambda spec: (spec.id != 'demo', not set_up(spec)))
        return found[0] if found else None

    def demo_on(self):
        spec = self.specs.get('demo')
        return bool(spec and spec.trust == 'builtin' and self.enabled(spec))

    def mapping_sources(self):
        """[(name, label, fetch)] for the seat sources: plugins that feed the seat mapping."""
        from .. import seatmap
        out = []
        for spec in self.feeders('mapping'):
            if spec.id in ('manual', 'json', 'http', 'checkin'):
                continue

            def fetch(spec=spec):
                try:
                    mapping, skipped = seatmap.clean_feed(self.call(spec, 'seat_mapping'))
                except seatmap.MappingError as exc:
                    raise PluginError(str(exc)) from None
                if skipped:
                    self.log(spec.id, f'seat mapping: skipped {skipped} bad entries')
                return mapping
            out.append((spec.id, spec.name, fetch))
        return out

    # hooks ---------------------------------------------------------------------------------
    def emit(self, event, data):
        """Run hooked actions in the background, so a slow plugin never slows a request."""
        jobs = []
        for spec in list(self.specs.values()):
            hooks = [h for h in spec.items('hooks') if event in h.get('events', [])]
            if not hooks or spec.error or not self.enabled(spec):
                continue
            jobs += [(spec, h['action']) for h in hooks]
        if not jobs:
            return
        if HOOKS_INLINE:
            for spec, action in jobs:
                self._run_hook(spec, action, event, data)
            return
        ctx = contextvars.copy_context()   # the tenant and event the change happened in
        with self._hooks_cv:
            for spec, action in jobs:
                if len(self._hooks) >= HOOK_QUEUE:
                    old = self._hooks.popleft()
                    self.hooks_dropped += 1
                    self.log(old[1].id, f'hook {old[3]} -> {old[2]} dropped: too many waiting ({HOOK_QUEUE})')
                self._hooks.append((ctx, spec, action, event, data))
            if self._hook_threads < HOOK_WORKERS:
                self._hook_threads += 1
                threading.Thread(target=self._hook_worker, daemon=True, name='plugin-hooks').start()
            self._hooks_cv.notify()

    def _hook_worker(self):
        while True:
            with self._hooks_cv:
                if not self._hooks and not self._hooks_cv.wait_for(lambda: self._hooks, timeout=30):
                    self._hook_threads -= 1    # idle: the next burst starts a new one
                    return
                ctx, spec, action, event, data = self._hooks.popleft()
            ctx.run(self._run_hook, spec, action, event, data)

    def hooks_waiting(self):
        with self._hooks_cv:
            return len(self._hooks)

    def _run_hook(self, spec, action, event, data):
        try:
            self.call(spec, f'run_{action}', {'event': event, 'data': data})
        except PluginError as exc:
            self.log(spec.id, f'hook {event} -> {action}: {exc}')
        except Exception as exc:  # noqa: BLE001  # a worker must outlive any hook
            self.log(spec.id, f'hook {event} -> {action} failed: {type(exc).__name__}')

    def as_list(self, lang='en'):
        out = []
        for spec in self.specs.values():
            def t(text, spec=spec):
                return self.text(spec, text, lang)
            out.append({
                'id': spec.id, 'name': t(spec.name), 'icon': spec.manifest.get('icon') or '',
                'version': str(spec.manifest.get('version', '')),
                'description': t(spec.manifest.get('description', '')), 'trust': spec.trust,
                'author': spec.manifest.get('author', ''), 'homepage': spec.manifest.get('homepage', ''),
                'uses': [{'id': u, 'label': AREAS.get(u, u)} for u in spec.uses if u in AREAS],
                'enabled': self.enabled(spec), 'error': spec.error,
                'settings_section': (spec.manifest.get('core_settings') or
                                     (f'plugin-{spec.id}' if spec.items('settings') and not spec.error else None)),
                'default_enabled': bool(spec.manifest.get('default_enabled')),
                'schema': spec.manifest.get('schema') or 0,
                'data_schema': self.schema_of(spec.id) if spec.manifest.get('schema') else 0,
                'actions': [{**{k: a.get(k) for k in ('id', 'role', 'permission', 'danger')},
                             'label': t(a.get('label')), 'help': t(a.get('help'))}
                            for a in spec.items('actions')],
                'widgets': [{**{k: w.get(k) for k in ('id', 'size', 'refresh', 'role', 'permission')},
                             'label': t(w.get('label'))}
                            for w in spec.items('widgets')],
                'panels': [{'id': p['id'], 'for': p['for'], 'label': t(p.get('label')), 'permission': p['permission']}
                           for p in spec.items('panels')],
                'layers': [{'id': p['id'], 'label': t(p.get('label')), 'permission': p['permission']}
                           for p in spec.items('layers')],
                'pages': [{'id': p['id'], 'label': t(p.get('label')), 'permission': p['permission'],
                           'href': f"/plugins/{spec.id}/{p['id']}"}
                          for p in spec.items('pages')],
                'endpoints': [{'id': e['id'], 'label': t(e.get('label')),
                               'url': f"/api/plugins/{spec.id}/endpoints/{e['id']}"}
                              for e in spec.items('endpoints')],
                'hooks': [{'events': h['events'], 'action': h['action']} for h in spec.items('hooks')],
                'agent': ({'sends': sorted(spec.agent.get('sends') or {}), 'calls': spec.agent.get('calls') or [],
                           'actions': spec.agent.get('actions') or []} if spec.agent else None),
                'has_test': bool(spec.plugin_class() and spec.plugin_class().test is not Plugin.test),
            })
        return out


def init_plugins(app, settings_store, current_version):
    registry = Registry(settings_store, current_version)
    app.extensions['floorbit_plugins'] = registry
    from .. import audit, sources
    sources.registry = registry
    audit.listeners.append(lambda entry: registry.emit('change', {
        k: entry.get(k) for k in ('area', 'action', 'target', 'fields', 'user')}))
    try:
        from integrations import events, seat_sources
        events.subscribe('switch.status', lambda ev: registry.emit('switch.status', ev.get('data') or {}),
                         leader_only=True)
        seat_sources.plugin_sources = registry.mapping_sources
    except ImportError:
        pass
    return registry
