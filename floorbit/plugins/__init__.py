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
development    ``FLOORBIT_DEV_PLUGINS`` (a folder of           inside Floorbit; never set
               checkouts, for writing plugins)                 it in production
=============  ==============================================  =========================

Installing other plugins (signed releases, run in a locked-down process of their own) comes in a
later step; until then no outside code runs. Every plugin starts switched off; an admin turns it on
under Settings > Plugins. See docs/plugins.md.
"""
from __future__ import annotations

import contextlib
import os
import re
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .base import Context, LogBuffer, Plugin, PluginError
from .widgets import WidgetError, check_widget

__all__ = ['Plugin', 'PluginError', 'Registry', 'Spec', 'init_plugins']

ID_RE = re.compile(r'^[a-z][a-z0-9-]{1,39}$')
NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
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
    'inventory': 'sends devices into the inventory (it never deletes; hand edits win)',
    'mapping':   'sends seat / IP / MAC / nick entries into the seat mapping (hand entries win)',
    'monitoring': 'live switch status, ports and IP to switch port lookups (one plugin at a time)',
    'health': 'service checks on the health wall (DHCP, DNS, cache, game servers, uplink)',
    'ports': 'act on switch ports (bounce, shut, turn on), with the tech\'s own login (one plugin at a time)',
    'security': 'security findings: rogue DHCP, ARP spoofing, MAC flapping, loops and storms',
    'power': 'load readings per circuit from smart PDUs and meters',
    'dns': 'lookups from the event\'s DNS resolver, for hall-wide DNS analytics (never per seat)',
    'logs': 'keeps the syslog longer (it gets every line) and searches it on the Logs page',
    'context_menu': 'entries in the floor plan\'s right-click menu that run one of its actions on a seat or switch',
}
# What a context_menu entry can be on, and the action parameter that carries the target.
MENU_TARGETS = {'seat': 'seat', 'switch': 'switch'}
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
}
# Builtin plugins only: on until an admin turns them off, and settings kept under a core section
# (NetBox's ``netbox.*`` keys and NETBOX_* env variables), so an existing install keeps working;
# ``enable_env`` names a variable that forces it on (FLOORBIT_DEMO for the demo data).
BUILTIN_ONLY = ('default_enabled', 'core_settings', 'enable_env')
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


@dataclass
class Spec:
    id: str
    path: Path
    trust: str
    manifest: dict = field(default_factory=dict)
    module: object = None
    error: str = ''

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
    for f in fields or []:
        if not isinstance(f, dict) or not NAME_RE.match(str(f.get('key', ''))):
            return f'{where}: bad key {f!r}'
        if f.get('type', 'string') not in SETTING_TYPES:
            return f"{where}.{f['key']}: type must be one of {', '.join(SETTING_TYPES)}"
        if f.get('type') == 'select' and not f.get('options'):
            return f"{where}.{f['key']}: a select needs options"
        if f['key'] in keys:
            return f"{where}.{f['key']}: duplicate"
        keys.add(f['key'])
    return ''


def validate(m):
    """An error message, or '' when the manifest is fine. No plugin code runs here."""
    if not isinstance(m, dict):
        return 'plugin.yaml must be a mapping'
    if not ID_RE.match(str(m.get('id', ''))):
        return 'id: 2 to 40 lowercase letters, digits and dashes, starting with a letter'
    uses = m.get('uses')
    if not isinstance(uses, list) or not uses:
        return f"uses: list the areas the plugin extends ({', '.join(AREAS)})"
    unknown = [u for u in uses if u not in AREAS]
    if unknown:
        return f"uses: unknown area(s) {', '.join(map(str, unknown))}"
    needs = {'settings': 'settings', 'actions': 'actions', 'widgets': 'widgets',
             'endpoints': 'endpoints', 'hooks': 'hooks', 'context_menu': 'context_menu'}
    for key, area in needs.items():
        if m.get(key) and area not in uses:
            return f'{key}: the plugin has {key} but "{area}" is not under uses:'
    err = _check_fields(m.get('settings'), 'settings')
    if err:
        return err
    for kind in ('actions', 'widgets', 'endpoints'):
        ids = set()
        for item in m.get(kind) or []:
            if not isinstance(item, dict) or not NAME_RE.match(str(item.get('id', ''))):
                return f'{kind}: bad id {item!r}'
            if item['id'] in ids:
                return f"{kind}.{item['id']}: duplicate"
            ids.add(item['id'])
            role = item.get('role', 'admin' if kind == 'actions' else 'viewer')
            if role not in ROLES or (kind == 'actions' and role == 'viewer'):
                return f"{kind}.{item['id']}: role must be " + ('editor or admin' if kind == 'actions'
                                                               else 'viewer, editor or admin')
            item['role'] = role
            # The permission it needs (auth/roles.py). Older manifests name a role; it maps across.
            permission = item.get('permission') or ROLE_PERMISSION[role]
            from auth.roles import PERMISSIONS
            if permission not in PERMISSIONS:
                return f"{kind}.{item['id']}: unknown permission {permission!r}"
            item['permission'] = permission
            item.setdefault('label', item['id'].replace('_', ' ').capitalize())
            if kind == 'actions':
                err = _check_fields(item.get('params'), f"actions.{item['id']}.params")
                if err:
                    return err
            if kind == 'widgets':
                if item.get('size', 'small') not in ('small', 'wide'):
                    return f"widgets.{item['id']}: size must be small or wide"
                item['refresh'] = max(10, int(item.get('refresh') or 60))
    actions = {a['id'] for a in m.get('actions') or []}
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
    allowed |= {'test'}
    for area, methods in AREA_METHODS.items():
        for method in methods:
            if area in spec.uses:
                allowed.add(method)
            elif callable(getattr(cls, method, None)):
                return f'plugin.py: {method}() needs "{area}" under uses:'
    for name in dir(cls):
        if name.startswith(('run_', 'widget_', 'endpoint_')) and name not in allowed:
            return f'plugin.py: {name} has no matching entry in plugin.yaml'
    for name in sorted(allowed - {'test'}):
        if not callable(getattr(cls, name, None)):
            return f'plugin.py: plugin.yaml lists it, but Plugin has no {name}()'
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
        spec.manifest = yaml.safe_load(mf.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as exc:
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
    py = path / 'plugin.py'
    if py.is_file():
        modname = f"floorbit_plugin_{spec.id.replace('-', '_')}"
        try:
            sp = importlib.util.spec_from_file_location(modname, py)
            mod = importlib.util.module_from_spec(sp)
            sys.modules[modname] = mod
            sp.loader.exec_module(mod)
            spec.module = mod
        except Exception as exc:  # noqa: BLE001  # a broken plugin must not take Floorbit down
            spec.error = f'plugin.py: {type(exc).__name__}: {exc}'
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
        return os.environ.get('PLUGINS_FILE') or os.path.join(
            os.path.dirname(os.path.abspath(store.DATA_FILE)), 'plugins.json')

    def _all(self, path=None):
        import json
        path = path or self.path()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            print(f'[plugins] could not read {path}: {exc}')
            return {}

    def _record(self, plugin_id):
        return self._all().get(plugin_id) or {}

    def _update(self, plugin_id, **changes):
        import json
        import tempfile
        with self._lock:
            path = self.path()   # once: read and write the same file
            data = self._all(path)
            data.setdefault(plugin_id, {}).update(changes)
            folder = os.path.dirname(path) or '.'
            fd, tmp = tempfile.mkstemp(dir=folder, prefix='.plugins-', suffix='.json')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp, path)
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
        record = self._record(spec.id)
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

    def log(self, plugin_id, line):
        self.logs.add(plugin_id, line)

    def require(self, spec, area):
        if area not in spec.uses:
            raise PluginError(f'{spec.name} uses {area} without listing it under uses: in plugin.yaml')

    # calls ---------------------------------------------------------------------------------
    def active(self, plugin_id):
        spec = self.specs.get(plugin_id)
        return spec if spec and self.enabled(spec) else None

    def call(self, spec, method, *args):
        """Run one plugin method. PluginError messages are shown; anything else is logged."""
        cls = spec.plugin_class()
        if cls is None:
            raise PluginError(f'{spec.name} has no code for this')
        try:
            return getattr(cls(Context(spec, self)), method)(*args)
        except PluginError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.log(spec.id, f'{method} failed: ' + ''.join(traceback.format_exception_only(exc)).strip())
            raise PluginError(f'{spec.name} failed ({type(exc).__name__}); details are in its log') from None

    def widget(self, spec, widget_id):
        item = spec.item('widgets', widget_id)
        try:
            return check_widget(self.call(spec, f'widget_{widget_id}'), item)
        except WidgetError as exc:
            self.log(spec.id, f'widget {widget_id}: {exc}')
            raise PluginError(f'{spec.name} returned a widget Floorbit can\'t draw') from None

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
        for spec in list(self.specs.values()):
            if spec.error or not self.enabled(spec):
                continue
            for hook in spec.items('hooks'):
                if event in hook.get('events', []):
                    threading.Thread(target=self._run_hook, args=(spec, hook['action'], event, data),
                                     daemon=True, name=f'plugin-{spec.id}').start()

    def _run_hook(self, spec, action, event, data):
        try:
            self.call(spec, f'run_{action}', {'event': event, 'data': data})
        except PluginError as exc:
            self.log(spec.id, f'hook {event} -> {action}: {exc}')

    def as_list(self):
        out = []
        for spec in self.specs.values():
            out.append({
                'id': spec.id, 'name': spec.name, 'version': str(spec.manifest.get('version', '')),
                'description': spec.manifest.get('description', ''), 'trust': spec.trust,
                'author': spec.manifest.get('author', ''), 'homepage': spec.manifest.get('homepage', ''),
                'uses': [{'id': u, 'label': AREAS.get(u, u)} for u in spec.uses if u in AREAS],
                'enabled': self.enabled(spec), 'error': spec.error,
                'settings_section': (spec.manifest.get('core_settings') or
                                     (f'plugin-{spec.id}' if spec.items('settings') and not spec.error else None)),
                'default_enabled': bool(spec.manifest.get('default_enabled')),
                'actions': [{k: a.get(k) for k in ('id', 'label', 'role', 'permission', 'danger', 'help')}
                            for a in spec.items('actions')],
                'widgets': [{k: w.get(k) for k in ('id', 'label', 'size', 'refresh', 'role', 'permission')}
                            for w in spec.items('widgets')],
                'endpoints': [{'id': e['id'], 'label': e.get('label'),
                               'url': f"/api/plugins/{spec.id}/endpoints/{e['id']}"}
                              for e in spec.items('endpoints')],
                'hooks': [{'events': h['events'], 'action': h['action']} for h in spec.items('hooks')],
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
        events.subscribe('switch.status', lambda ev: registry.emit('switch.status', ev.get('data') or {}))
        seat_sources.plugin_sources = registry.mapping_sources
    except ImportError:
        pass
    return registry
