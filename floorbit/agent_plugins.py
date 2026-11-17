"""The hosted side of agent plugins (floorbit/plugins/agent.py, docs/agent-plugins.md).

* ``config()``: which plugins each agent runs and their settings, pulled by the agent
  (``GET /api/agent/v1/plugins``) every minute and when told to (``plugins_reload``). ``local``
  also names the plugins without an agent part the agent turns on in its own copy of Floorbit.
* ``take()``: what an agent part sent (``POST /api/agent/v1/plugins/<id>/<kind>``), checked and
  handed to the hosted part's ``agent_<kind>(agent, payload)``.
* ``ask()``: a call or an action for the agent part, over the tunnel (method ``plugin``).
* ``clean_health()``: the per-plugin health in an agent's report, cleaned up.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from .plugins.agent import STATUSES, check_payload

CALL_TIMEOUT = 15
ACTION_TIMEOUT = 120
PLUGIN_ID_RE = re.compile(r'^[a-z][a-z0-9-]{1,39}$')
NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
MAX_PLUGINS_REPORTED = 40
# Plugins the agent also turns on in its own copy of Floorbit when they are on here: with them it
# answers the hosted side's monitoring, inventory, health, DNS, Wi-Fi and port calls.
LOCAL_AREAS = ('monitoring', 'inventory', 'health', 'dns', 'wifi', 'ports')
NEVER_LOCAL = ('demo',)


def _registry():
    from . import sources
    return sources.registry


def agent_specs(registry=None):
    """The plugins that are on and have an agent part, in id order."""
    registry = registry or _registry()
    if registry is None:
        return []
    return [s for s in registry.feeders('agent') if s.agent and not s.error]


def config(registry=None):
    """What every agent runs: ``{"plugins": {id: {...}}, "etag": ...}``. The agent compares the
    etag and restarts only the plugins whose part changed."""
    registry = registry or _registry()
    plugins = {}
    for spec in agent_specs(registry):
        block = spec.agent
        settings = registry.settings_of(spec)
        if block.get('targets'):
            # The devices this plugin may work on: enabled for them (device, group, tag) and with
            # credentials, as the inventory resolves it (inventory_scope, docs/agent-plugins.md).
            # Before agent_settings, so a plugin with devices of its own can merge both lists.
            settings = {**settings, 'targets': plugin_targets(spec.id, block['targets'].get('credentials'))}
        cls = spec.plugin_class()
        if cls is not None and callable(getattr(cls, 'agent_settings', None)):
            # Settings kept elsewhere (Settings > Telemetry): the hosted part says what the agent gets.
            from .plugins.base import PluginError
            try:
                settings = registry.call(spec, 'agent_settings', settings)
            except PluginError as exc:
                registry.log(spec.id, f'agent_settings: {exc}')
                continue
        plugins[spec.id] = {
            'version': str(spec.manifest.get('version', '')),
            'settings': settings,
            'sends': {k: {'privacy': v.get('privacy', 'aggregate'), **({'latest': True} if v.get('latest') else {})}
                      for k, v in (block.get('sends') or {}).items()},
            'fetches': list(block.get('fetches') or []),
            'calls': list(block.get('calls') or []),
            'actions': list(block.get('actions') or []),
        }
    local = local_config(registry)
    raw = json.dumps([plugins, local], sort_keys=True, default=str).encode()
    return {'plugins': plugins, 'local': local, 'etag': hashlib.sha256(raw).hexdigest()[:32]}


def local_config(registry=None):
    """``{id: {"settings": {full settings key: value}}}`` for the built-in plugins that are on here
    and answer for the hall (LOCAL_AREAS), with an agent part or not: telemetry is both, and the
    agent's own monitoring source. Empty values are left out, so the
    agent's own environment still fills them."""
    registry = registry or _registry()
    if registry is None:
        return {}
    out = {}
    for spec in sorted(registry.specs.values(), key=lambda s: s.id):
        if (spec.error or spec.trust != 'builtin' or spec.id in NEVER_LOCAL
                or not set(spec.manifest.get('uses') or ()) & set(LOCAL_AREAS) or not registry.enabled(spec)):
            continue
        keys = registry._core_fields(spec) + [f"plugin.{spec.id}.{f['key']}" for f in spec.items('settings')]
        values = {}
        for key in keys:
            value = registry.settings_store.get(key)
            if value not in (None, '', [], {}):
                values[key] = value
        out[spec.id] = {'settings': values}
    return out


def give(agent, plugin_id, kind):
    """What the agent part asks for (``GET /api/agent/v1/plugins/<id>/<kind>``): the hosted part's
    ``agent_get_<kind>(agent)``. Refused like ``take``."""
    registry = _registry()
    if not PLUGIN_ID_RE.match(str(plugin_id)) or not NAME_RE.match(str(kind)):
        raise Refused('bad plugin or kind', 404)
    spec = registry.specs.get(plugin_id) if registry else None
    if spec is None or not spec.agent or spec.error:
        raise Refused(f'No agent plugin {plugin_id} here.', 404)
    if not registry.enabled(spec):
        raise Refused(f'{spec.name} is turned off on this Floorbit.', 409)
    if kind not in (spec.agent.get('fetches') or []):
        raise Refused('bad plugin or kind', 422)
    from .plugins.base import PluginError
    try:
        return registry.call(spec, f'agent_get_{kind}', {'id': agent['id'], 'name': agent['name']})
    except PluginError as exc:
        raise Refused(str(exc), 409) from exc


def _scope():
    try:
        from . import inventory_scope
    except ImportError:
        return None
    return inventory_scope


def plugin_targets(plugin_id, kinds=None):
    """The inventory's devices for a plugin (on for them after groups and tags, a credential that
    resolves and isn't blocked), or [] while the inventory can't say."""
    scope = _scope()
    if scope is None:
        return []
    try:
        return list(scope.plugin_targets(plugin_id, kinds) or [])
    except Exception as exc:  # noqa: BLE001  # no targets is safe: the plugin logs in nowhere
        print(f'[agent-plugins] targets of {plugin_id}: {exc}')
        return []


class Refused(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def take(agent, plugin_id, kind, payload, registry=None):
    """Hand what an agent sent to the plugin's hosted part. Returns its answer (JSON-able) or
    raises Refused. An agent from before a plugin was turned off gets a 409, so it stops."""
    registry = registry or _registry()
    if not PLUGIN_ID_RE.match(str(plugin_id)) or not NAME_RE.match(str(kind)):
        raise Refused('bad plugin or kind', 404)
    spec = registry.specs.get(plugin_id) if registry else None
    if spec is None or not spec.agent or spec.error:
        raise Refused(f'No agent plugin {plugin_id} here.', 404)
    if not registry.enabled(spec):
        raise Refused(f'{spec.name} is turned off on this Floorbit.', 409)
    err = check_payload(spec.agent, kind, payload)
    if err:
        registry.log(spec.id, f'refused {kind} from {agent.get("name")}: {err}')
        raise Refused(err, 422)
    cls = spec.plugin_class()
    if cls is None or not callable(getattr(cls, f'agent_{kind}', None)):
        return {'ok': True, 'kept': False}       # nothing on the hosted side wants it (yet)
    from .plugins.base import PluginError
    try:
        answer = registry.call(spec, f'agent_{kind}', {'id': agent.get('id'), 'name': agent.get('name')}, payload)
    except PluginError as exc:
        # 409, not 500: the agent sends a 5xx again and again; this is the hosted part saying no.
        raise Refused(str(exc), 409) from None
    return answer if isinstance(answer, dict) else {'ok': True}


def ask(spec, way, op, args=None, agent=None):
    """``way`` "call" or "action": run the agent part's ``<way>_<op>`` on one agent or on every
    connected one. ``[{agent, name, result | error}]``."""
    from . import agent_link
    from .plugins.base import PluginError
    listed = (spec.agent or {}).get('calls' if way == 'call' else 'actions') or []
    if op not in listed:
        raise PluginError(f'{spec.name} has no agent {way} {op}')
    names = {a['id']: a['name'] for a in agent_link.load_data().get(agent_link.KEY) or []}
    targets = [agent] if agent else sorted(agent_link.tunnel.connected_agents() & set(names))
    if not targets:
        raise PluginError('No local agent is connected.')
    timeout = CALL_TIMEOUT if way == 'call' else ACTION_TIMEOUT
    message = [spec.id, way, op, args if args is not None else {}]

    def one(agent_id):
        try:
            return {'agent': agent_id, 'name': names.get(agent_id, agent_id),
                    'result': agent_link.tunnel.call('plugin', message, timeout, {agent_id})}
        except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
            return {'agent': agent_id, 'name': names.get(agent_id, agent_id), 'error': str(exc)[:300]}

    with ThreadPoolExecutor(min(len(targets), 8)) as pool:
        return list(pool.map(one, targets))


def reload_agents():
    """Tell the connected agents the plugin config changed (settings saved, a plugin turned on or
    off), so they don't wait for their next minute. Never fails: they pull it anyway."""
    from . import agent_link
    for agent_id in sorted(agent_link.tunnel.connected_agents()):
        try:
            agent_link.tunnel.call('plugins_reload', [], 5, {agent_id})
        except (agent_link.AgentUnavailable, agent_link.AgentError):
            continue


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e18


def clean_health(raw):
    """``{plugin id: {status, message, metrics, errors, running}}`` from an agent's report.
    What an agent sends is not trusted: known shapes, short strings, numbers only."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for pid, h in list(raw.items())[:MAX_PLUGINS_REPORTED]:
        if not PLUGIN_ID_RE.match(str(pid)) or not isinstance(h, dict):
            continue
        metrics = h.get('metrics') if isinstance(h.get('metrics'), dict) else {}
        errors = h.get('errors') if isinstance(h.get('errors'), list) else []
        blocks = h.get('auth_blocked') if isinstance(h.get('auth_blocked'), list) else []
        out[pid] = {
            'auth_blocked': [{'device': str(b.get('device') or '')[:120],
                              'credential': str(b.get('credential') or '')[:120],
                              'rev': None if b.get('rev') is None else str(b['rev'])[:40],
                              'since': b['since'] if _number(b.get('since')) else None,
                              'message': str(b.get('message') or '')[:300]}
                             for b in blocks[:50] if isinstance(b, dict) and b.get('device')],
            'status': h.get('status') if h.get('status') in STATUSES else 'error',
            'message': str(h.get('message') or '')[:300],
            'running': bool(h.get('running')),
            'metrics': {k: v for k, v in list(metrics.items())[:40] if NAME_RE.match(str(k)) and _number(v)},
            'errors': [{'at': e['at'] if _number(e.get('at')) else None, 'error': str(e.get('error') or '')[:300]}
                       for e in errors[-10:] if isinstance(e, dict)],
        }
    return out


def note_blocks(agent_id, before, after):
    """Audit-log the logins an agent newly stopped trying (from its report)."""
    from . import agent_link, audit
    def keys(report):
        return {(pid, b['device'], b['credential'], b['rev']): b
                for pid, h in ((report or {}).get('plugins') or {}).items() for b in h.get('auth_blocked') or []}
    old, new = keys(before), keys(after)
    if not set(new) - set(old):
        return
    names = {a['id']: a['name'] for a in agent_link.load_data().get(agent_link.KEY) or []}
    for (pid, device, credential, _rev), b in new.items():
        if (pid, device, credential, _rev) in old:
            continue
        audit.record('agents', f'{names.get(agent_id, agent_id)}: {pid} stopped logging in to {device} '
                     f'with {credential} ({b["message"][:120]})', user='agent', target=device, ok=False)
        # The block lives on the device too, so every agent and the hosted SSH path leave it alone.
        scope = _scope()
        if scope is not None and hasattr(scope, 'auth_failed'):
            try:
                scope.auth_failed(device, credential, _rev, pid, b['message'], agent=agent_id)
            except Exception as exc:  # noqa: BLE001
                print(f'[agent-plugins] could not keep the block on {device}: {exc}')


def auth_blocks(device=None):
    """``[{agent, agent_name, plugin, device, credential, rev, since, message}]``: logins the agents
    stopped trying, for the Local agents page and the device's own page."""
    from . import agent_link
    out = []
    for a in agent_link.all_agents():
        for pid, h in ((a.get('report') or {}).get('plugins') or {}).items():
            for b in h.get('auth_blocked') or []:
                if device is None or b['device'] == str(device):
                    out.append({'agent': a['id'], 'agent_name': a['name'], 'plugin': pid, **b})
    return out


def unblock(agent_id, plugin_id, device, credential, user=None):
    """A tech cleared it: the agent may try that login again. Returns how many blocks went."""
    from . import agent_link, audit
    from .plugins.base import PluginError
    scope = _scope()
    if scope is not None and hasattr(scope, 'clear_block'):
        scope.clear_block(device, credential, user=user)
    try:
        ask = [plugin_id, 'unblock', '', {'device': device, 'credential': credential}]
        result = agent_link.tunnel.call('plugin', ask, CALL_TIMEOUT, {agent_id})
    except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
        if scope is None:
            raise PluginError(str(exc)) from None
        result = {}        # cleared on the device; the agent drops its copy with the next settings
    audit.record('agents', f'Cleared the failed login of {plugin_id} to {device} ({credential})', user=user,
                 target=device)
    return (result or {}).get('cleared', 0)


def health_of(plugin_id):
    """``{agent id: {name, connected, health}}`` for one plugin, from each agent's last report."""
    from . import agent_link
    out = {}
    for a in agent_link.all_agents():
        report = a.get('report') or {}
        health = (report.get('plugins') or {}).get(plugin_id)
        if health is not None:
            out[a['id']] = {'name': a['name'], 'connected': a['connected'], 'health': health}
    return out
