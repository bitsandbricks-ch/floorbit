"""Each local agent's own settings, set on its page in Floorbit (docs/agent.md, "Settings from Floorbit").

Two kinds, kept on the agent's record (data.json ``agents``):

- **The agent's settings** (``FIELDS``): where laptops reach it, its metrics port, its disk budget and buffer age,
  the Telegraf port, VRRP. Each has the environment variable the agent read before; the agent's
  environment still wins when it sets one, and the agent reports where each value came from.
- **Plugin settings for this agent** (``plugin_settings``): a plugin's setting (the flow port, a
  listen address) that differs on this agent. Settings > Plugins stays the default.

Not here, on purpose: what the people in the hall allow (actions, plugin updates, the networks the
agent may reach, ``LOCAL_ONLY``). A stolen Floorbit login must not widen those; the page only shows
what the agent reports for them. Nor the machine itself (its URL, key, files): the agent needs
them before it can ask.
"""
import ipaddress
import re

from .agent_link import AgentError, _change, load_data

KEY = 'settings'
PLUGIN_KEY = 'plugin_settings'

# key, env var, type, default, limits; "restart": the agent takes it at its next start.
FIELDS = [
    {'key': 'metrics', 'env': 'FLOORBIT_AGENT_METRICS', 'type': 'listen', 'default': '0.0.0.0:9520', 'restart': True},
    {'key': 'metrics_token', 'env': 'FLOORBIT_AGENT_METRICS_TOKEN', 'type': 'secret', 'default': '', 'restart': True},
    # One budget for all it keeps on disk (raw flows, the buffer, plugin files), floorbit/disk_budget.py.
    # 0 is automatic: half of what the agent's volume could hold.
    {'key': 'disk_budget_mb', 'env': 'FLOORBIT_AGENT_DISK_BUDGET_MB', 'type': 'int', 'default': 0,
     'min': 0, 'max': 100_000_000, 'restart': False},
    {'key': 'buffer_max_hours', 'env': 'FLOORBIT_AGENT_BUFFER_MAX_HOURS', 'type': 'int', 'default': 24,
     'min': 1, 'max': 720, 'restart': True},
    # Where laptops in the hall reach it, when it can't learn that (a reverse proxy, port forwarding,
    # issue #1361): the seat walk-through sends the crew there.
    {'key': 'hall_url', 'env': 'FLOORBIT_AGENT_HALL_URL', 'type': 'url', 'default': '', 'restart': False},
    {'key': 'telemetry_port', 'env': 'FLOORBIT_TELEMETRY_PORT', 'type': 'int', 'default': 8186,
     'min': 1, 'max': 65535, 'restart': True},
    {'key': 'cert_names', 'env': None, 'type': 'names', 'default': [], 'restart': False},
    {'key': 'vrrp_vips', 'env': 'FLOORBIT_AGENT_VRRP_VIPS', 'type': 'cidrs', 'default': [], 'restart': True},
    {'key': 'vrrp_interface', 'env': 'FLOORBIT_AGENT_VRRP_INTERFACE', 'type': 'iface', 'default': '', 'restart': True},
    {'key': 'vrrp_prefer', 'env': 'FLOORBIT_AGENT_VRRP_PREFER', 'type': 'int', 'default': 0,
     'min': 0, 'max': 16, 'restart': True},
    {'key': 'vrrp_id', 'env': 'FLOORBIT_AGENT_VRRP_ID', 'type': 'int', 'default': 51, 'min': 1, 'max': 255,
     'restart': True},
    {'key': 'vrrp_peers', 'env': 'FLOORBIT_AGENT_VRRP_PEERS', 'type': 'ips', 'default': [], 'restart': True},
    {'key': 'log_level', 'env': 'FLOORBIT_AGENT_LOG_LEVEL', 'type': 'choice', 'default': 'info',
     'options': ['debug', 'info', 'warning', 'error'], 'restart': False},
    {'key': 'log_summary', 'env': 'FLOORBIT_AGENT_LOG_SUMMARY', 'type': 'int', 'default': 300,
     'min': 0, 'max': 86400, 'restart': True},
]
BY_KEY = {f['key']: f for f in FIELDS}
# Only the agent's own environment sets these; Floorbit shows what the agent reports.
LOCAL_ONLY = ('FLOORBIT_AGENT_ALLOW_ACTIONS', 'FLOORBIT_AGENT_PLUGIN_UPDATES', 'FLOORBIT_AGENT_UPDATES',
              'FLOORBIT_AGENT_SWITCH_NETS', 'FLOORBIT_AGENT_GAME_NETS', 'FLOORBIT_AGENT_PROBE_NETS')
NAME_RE = re.compile(r'^(?=.{1,253}\Z)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\Z')
IFACE_RE = re.compile(r'^[A-Za-z0-9_.:@-]{1,15}\Z')
MAX_NAMES = 10


def _list(raw):
    if isinstance(raw, str):
        raw = raw.split(',')
    if not isinstance(raw, list):
        raise AgentError('Give a list.')
    return [str(x).strip() for x in raw if str(x).strip()]


def clean(field, raw):
    """``raw`` as the field's type, or AgentError. None and "" clear it (the default applies)."""
    if raw is None or raw == '' or raw == []:
        return None
    t, key = field['type'], field['key']
    if t == 'int':
        try:
            val = int(raw)
        except (TypeError, ValueError, OverflowError):
            raise AgentError(f'{key} must be a whole number.') from None
        if not field['min'] <= val <= field['max']:
            raise AgentError(f"{key} must be between {field['min']} and {field['max']}.")
        return val
    if t in ('cidrs', 'ips', 'names'):
        items = _list(raw)
        if len(items) > MAX_NAMES:
            raise AgentError(f'{key} takes at most {MAX_NAMES} entries.')
        for item in items:
            try:
                if t == 'cidrs':
                    ipaddress.ip_interface(item)
                elif t == 'ips' or not NAME_RE.match(item):
                    ipaddress.ip_address(item)
            except ValueError:
                raise AgentError(f'{key}: "{item[:60]}" is not valid.') from None
        return items
    val = str(raw).strip()
    if t == 'choice':
        if val not in field['options']:
            raise AgentError(f"{key} must be one of {', '.join(field['options'])}.")
        return val
    if '\n' in val or '\x00' in val or len(val) > 300:
        raise AgentError(f'{key} is not valid.')
    if t == 'url' and not re.match(r'^https?://[A-Za-z0-9.:\[\]-]{1,120}(/[^\s]{0,60})?$', val):
        raise AgentError(f'{key} must be an http:// or https:// address.')
    if t == 'listen' and val.lower() != 'off' and not re.match(r'^[A-Za-z0-9.:\[\]-]{1,100}:\d{1,5}$', val):
        raise AgentError(f'{key} must be host:port or off.')
    if t == 'iface' and not IFACE_RE.match(val):
        raise AgentError(f'{key} must be a network interface name.')
    return val.rstrip('/') if t == 'url' else val


def _slot(agent_id, key):
    return f'agent-setting:{agent_id}:{key}'


def _record(agent_id):
    found = next((a for a in load_data().get('agents') or [] if a['id'] == agent_id), None)
    if found is None:
        err = AgentError('No such agent.')
        err.status = 404
        raise err
    return found


# ── plugin settings for one agent ───────────────────────────────────────────────────────────────

def plugin_fields(registry=None):
    """{plugin id: [setting field]} an agent may override: the settings of the plugins that run on
    an agent, without secrets (one token for every agent is enough, and it stays write-only)."""
    from . import agent_plugins
    from . import settings as settings_module
    out = {}
    for spec in agent_plugins.agent_specs(registry):
        fields = [settings_module.FIELDS_BY_KEY.get(f"plugin.{spec.id}.{f['key']}") for f in spec.items('settings')]
        fields = [f for f in fields if f and f['type'] != 'secret']
        if fields:
            out[spec.id] = fields
    return out


def overrides(agent_id, data=None):
    """{plugin id: {setting: value}} set for this agent only."""
    data = load_data() if data is None else data
    found = next((a for a in data.get('agents') or [] if a['id'] == agent_id), None)
    return {k: dict(v) for k, v in ((found or {}).get(PLUGIN_KEY) or {}).items() if isinstance(v, dict)}


# ── reading and saving ──────────────────────────────────────────────────────────────────────────

def values(agent_id, reveal=False):
    """{key: value} Floorbit sets for this agent. Secrets: the clear text with ``reveal`` (for the
    agent), else ``True`` (it is set)."""
    from . import vault
    out = {}
    for key, value in (_record(agent_id).get(KEY) or {}).items():
        field = BY_KEY.get(key)
        if field is None or value is None:
            continue
        if field['type'] == 'secret':
            if not reveal:
                out[key] = True
                continue
            try:
                value = vault.open_(_slot(agent_id, key), value)
            except vault.VaultError:
                continue
        out[key] = value
    return out


def update(agent_id, settings=None, plugins=None, registry=None):
    """Save ``{key: value | None}`` and ``{plugin id: {setting: value | None}}`` (None clears).
    Returns the names of what changed, for the audit log."""
    from . import settings as settings_module
    from . import vault
    changed = []
    clean_settings = {}
    for key, raw in (settings or {}).items():
        field = BY_KEY.get(key)
        if field is None:
            raise AgentError(f'Unknown agent setting: {key}')
        value = clean(field, raw)
        if field['type'] == 'secret' and value is not None:
            value = vault.seal(_slot(agent_id, key), value)
        clean_settings[key] = value
    clean_plugins = {}
    if plugins:
        allowed = plugin_fields(registry)
        if not isinstance(plugins, dict):
            raise AgentError('plugins must map plugin ids to settings.')
        for pid, changes in plugins.items():
            fields = {f['key'].split('.', 2)[2]: f for f in allowed.get(pid, [])}
            if not fields or not isinstance(changes, dict):
                raise AgentError(f'No plugin settings for {pid} on an agent.')
            out = {}
            for key, raw in changes.items():
                if key not in fields:
                    raise AgentError(f'{pid} has no setting {key} an agent can change.')
                full = fields[key]['key']
                try:
                    out[key] = None if raw in (None, '') else settings_module.check_changes({full: raw})[full]
                except settings_module.SettingsError as exc:
                    raise AgentError(str(exc)) from None
            clean_plugins[pid] = out

    def apply(a):
        mine = dict(a.get(KEY) or {})
        for key, value in clean_settings.items():
            if mine.get(key) != value:
                changed.append(key)
            if value is None:
                mine.pop(key, None)
            else:
                mine[key] = value
        a[KEY] = mine
        theirs = {k: dict(v) for k, v in (a.get(PLUGIN_KEY) or {}).items()}
        for pid, changes in clean_plugins.items():
            block = theirs.setdefault(pid, {})
            for key, value in changes.items():
                if block.get(key) != value:
                    changed.append(f'{pid}.{key}')
                if value is None:
                    block.pop(key, None)
                else:
                    block[key] = value
            if not block:
                theirs.pop(pid)
        a[PLUGIN_KEY] = theirs
    found = _change(agent_id, apply)
    return found['name'], changed


def page(agent_id, registry=None, lang='en'):
    """What the agent's Settings tab shows: the fields, Floorbit's values, each plugin's default and
    this agent's overrides. Where each value really comes from is in the agent's report."""
    from . import agent_plugins
    registry = registry or agent_plugins._registry()
    mine = values(agent_id)
    theirs = overrides(agent_id)
    plugins = []
    specs = {s.id: s for s in agent_plugins.agent_specs(registry)}
    for pid, fields in plugin_fields(registry).items():
        defaults = registry.settings_of(specs[pid]) if pid in specs else {}
        spec = specs.get(pid)

        def text(value, spec=spec):
            return registry.text(spec, value, lang) if spec is not None and isinstance(value, str) else value
        plugins.append({
            'id': pid, 'name': text(spec.name) if spec else pid,
            'fields': [{'key': f['key'].split('.', 2)[2], 'label': text(f['label']), 'type': f['type'],
                        'help': text(f.get('help')), 'min': f.get('min'), 'max': f.get('max'),
                        'options': f.get('options'), 'placeholder': text(f.get('placeholder')),
                        'default': defaults.get(f['key'].split('.', 2)[2])} for f in fields],
            'values': theirs.get(pid, {}),
        })
    return {
        'fields': [dict(f) for f in FIELDS],
        'values': mine,
        'local_only': list(LOCAL_ONLY),
        'plugins': plugins,
        **state(agent_id),
    }


# ── what the agent gets with its plugin config ─────────────────────────────────────────────────

def agent_block(agent_id):
    """``{"settings", "roll_key", "cert"}`` for one agent (agent_plugins.config): its settings with
    secrets in clear (the config goes only to that agent), whether to fetch a new key, and which
    names its certificate must carry (``asked``: a new one was asked for after this time)."""
    try:
        record = _record(agent_id)
    except AgentError:
        return {}
    settings = values(agent_id, reveal=True)
    out = {'settings': settings, 'roll_key': bool(record.get('roll_asked'))}
    names = cert_names(agent_id, settings.get('cert_names') or [])
    if names:
        out['cert'] = {'names': names, 'asked': record.get('cert_asked') or 0}
    from . import public_cert
    public = public_cert.block()
    if public:
        # The tenant's Let's Encrypt certificate (public_cert.py); an agent that can't take it
        # ignores the key and keeps the CA's.
        out['public_cert'] = public
    return out


# ── a new key, fetched by the agent itself ─────────────────────────────────────────────────────

def ask_roll(agent_id, now=None):
    """The agent fetches a new key at its next config pull (within a minute, or at once when told)."""
    import time
    now = time.time() if now is None else now
    return _change(agent_id, lambda a: a.__setitem__('roll_asked', now))['name']


def take_roll(agent_id, now=None):
    """A new key for an agent that was asked to fetch one, or None. The key it uses now keeps
    working until it first uses the new one (agent_link.check), at most ROTATE_GRACE. Asked again
    before it ever used the last one (the answer got lost): the key it really has stays the old one."""
    import secrets
    import time

    from . import agent_link
    now = time.time() if now is None else now
    secret = secrets.token_urlsafe(32)
    took = {}

    def swap(a):
        if not a.pop('roll_asked', None):
            return
        unused = a.get('prev_hash') and (a.get('prev_until') or 0) > now
        a.update(prev_hash=a['prev_hash'] if unused else a['hash'], prev_until=now + agent_link.ROTATE_GRACE,
                 hash=agent_link._hash(secret), renewed_at=now)
        took['local'] = bool(a.get('local'))
    _change(agent_id, swap)
    if not took:
        return None
    key = f'{agent_link.PREFIX}{agent_id}_{secret}'
    if took['local'] and agent_link._local_key_file():
        try:     # the agent next to us also reads it from the shared file at its next start
            agent_link._write_key_file(agent_link._local_key_file(), key)
        except OSError as exc:
            print(f'[agent] cannot write the new key to {agent_link._local_key_file()}: {exc}', flush=True)
    return key


# ── certificates (agent_ca.py) ─────────────────────────────────────────────────────────────────

def ask_cert(agent_id, now=None):
    import time
    now = time.time() if now is None else now
    return _change(agent_id, lambda a: a.__setitem__('cert_asked', now))['name']


def cert_names(agent_id, own):
    """The names on the agent's certificate: its own, then those of the agents it shares a group
    with (the same tags, agent_ha.py). Two agents behind one VIP or check-in name answer for the
    same names, so the second one needs none typed in (issue #1405)."""
    from .agent_link import KEY as AGENTS
    out = [n for n in own if isinstance(n, str)]
    try:
        agents = [a for a in load_data().get(AGENTS) or [] if not a.get('demo')]
        me = next((a for a in agents if a['id'] == agent_id), None)
        mine = sorted((me or {}).get('tags') or ())
        for other in sorted(agents, key=lambda a: a['id']):
            if me is None or other['id'] == agent_id or sorted(other.get('tags') or ()) != mine:
                continue
            for name in values(other['id']).get('cert_names') or []:
                if isinstance(name, str) and name not in out:
                    out.append(name)
    except AgentError:
        pass
    return out[:MAX_NAMES]


def issue_cert(agent_id, csr_pem, now=None):
    """Sign the agent's request for the names set on its page. Returns the PEM chain."""
    import time

    from . import agent_ca
    now = time.time() if now is None else now
    names = cert_names(agent_id, values(agent_id).get('cert_names') or [])
    pem, not_after, serial = agent_ca.sign(csr_pem, names)

    def keep(a):
        # Every certificate still valid, not only the newest: revoking the agent lists them all.
        held = [c for c in (a.get('cert') or {}).get('serials') or [] if c.get('not_after', 0) > now]
        a['cert'] = {'issued_at': now, 'not_after': not_after, 'names': names,
                     'serials': [*held, {'serial': serial, 'not_after': not_after}]}
    _change(agent_id, keep)
    return pem


def mark_public_cert(agent_id, now):
    """This agent now holds the tenant's certificate key: revoking it replaces the certificate."""
    _change(agent_id, lambda a: a.__setitem__('public_cert_at', now))


def state(agent_id):
    """Key and certificate state for the page."""
    from . import agent_identity
    record = _record(agent_id)
    return {'roll_asked': record.get('roll_asked'), 'renewed_at': record.get('renewed_at') or record.get('created_at'),
            'cert': record.get('cert'), 'cert_asked': record.get('cert_asked'),
            'identity': agent_identity.public(record.get('identity')),
            'public_cert_at': record.get('public_cert_at'), 'public_cert': _public_status()}


def _public_status():
    from . import public_cert
    return public_cert.status()


# ── what the agent reports about them ──────────────────────────────────────────────────────────

SOURCES = ('env', 'floorbit', 'default')


def clean_report(raw):
    """The agent's ``settings`` report: where each value came from and what it is (secrets only as
    set or not), which take effect at its next start, its key's and certificate's state. What an
    agent sends is not trusted: known keys only, short strings."""
    if not isinstance(raw, dict):
        return None
    out = {}
    values_ = raw.get('values') if isinstance(raw.get('values'), dict) else {}
    known = {f['key'] for f in FIELDS} | set(LOCAL_ONLY)
    for key, v in values_.items():
        if key not in known or not isinstance(v, dict) or v.get('source') not in SOURCES:
            continue
        row = {'source': v['source']}
        value = v.get('value')
        secret = BY_KEY.get(key, {}).get('type') == 'secret'
        if isinstance(value, (str, int, float)) and not isinstance(value, bool) and not secret:
            row['value'] = str(v['value'])[:200]
        if v.get('set') is True:
            row['set'] = True
        out[key] = row
    result = {'values': out}
    pending = raw.get('pending')
    if isinstance(pending, list):
        result['pending'] = sorted({p for p in pending if p in known})
    if raw.get('key') in ('stored', 'env', 'file'):
        result['key'] = raw['key']
    cert = raw.get('cert')
    if isinstance(cert, dict) and isinstance(cert.get('not_after'), (int, float)) and cert.get('source') in SOURCES:
        names = [str(n)[:100] for n in cert.get('names') or [] if isinstance(n, str)][:MAX_NAMES]
        result['cert'] = {'not_after': cert['not_after'], 'names': names, 'source': cert['source'],
                          'floorbit_ca': cert.get('floorbit_ca') is True, 'public': cert.get('public') is True}
    return result
