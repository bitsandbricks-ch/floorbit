"""The hosted side of agent plugins (floorbit/plugins/agent.py, docs/agent-plugins.md).

* ``config()``: which plugins each agent runs and their settings, pulled by the agent
  (``GET /api/agent/v1/plugins``) every minute and when told to (``plugins_reload``).
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
        plugins[spec.id] = {
            'version': str(spec.manifest.get('version', '')),
            'settings': registry.settings_of(spec),
            'sends': {k: {'privacy': v.get('privacy', 'aggregate')} for k, v in (block.get('sends') or {}).items()},
            'calls': list(block.get('calls') or []),
            'actions': list(block.get('actions') or []),
        }
    raw = json.dumps(plugins, sort_keys=True, default=str).encode()
    return {'plugins': plugins, 'etag': hashlib.sha256(raw).hexdigest()[:32]}


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
        raise Refused(str(exc), 500) from None
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
        out[pid] = {
            'status': h.get('status') if h.get('status') in STATUSES else 'error',
            'message': str(h.get('message') or '')[:300],
            'running': bool(h.get('running')),
            'metrics': {k: v for k, v in list(metrics.items())[:40] if NAME_RE.match(str(k)) and _number(v)},
            'errors': [{'at': e['at'] if _number(e.get('at')) else None, 'error': str(e.get('error') or '')[:300]}
                       for e in errors[-10:] if isinstance(e, dict)],
        }
    return out


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
