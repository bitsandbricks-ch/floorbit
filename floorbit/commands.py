"""Switch commands (issue #94): saved commands run on one or many switches, output side by side.
See docs/commands.md.

Nobody types a command: the crew picks a template. ``show`` templates only read (every command
must start with a word that reads, such as ``show``) and need ``ports.act``, like port actions.
``change`` templates (``clear counters``) need ``commands.change`` and a second confirm. Admins add
their own templates; the built-in ones cover the switch software the SSH plugin knows.

The switch login is the tech's own, typed for each run, used for those connections and dropped,
like port actions (floorbit/ports.py). Every run is audited per switch, never with its output.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import inventory, ports
from .plugins import PluginError
from .store import load_data, save_data

KINDS = ('show', 'change')
# A show template may only start its commands with these: they read and change nothing.
READ_WORDS = ('show', 'display', 'ping', 'traceroute', 'get')
ID_RE = re.compile(r'^[a-z][a-z0-9_-]{1,31}$')
MAX_SWITCHES = 20
MAX_COMMANDS = 10
MAX_OUTPUT = 64 * 1024       # characters kept per switch
WORKERS = 8
KEY = 'command_templates'

# (id, kind, label, {platform: [commands]}); "*" is every platform not named.
BUILTIN = (
    ('port_status', 'show', 'Port status', {
        '*': ['show interface {port}'], 'juniper_junos': ['show interfaces {port} extensive'],
        'aruba_procurve': ['show interfaces {port}']}),
    ('all_ports', 'show', 'All ports', {
        '*': ['show interfaces status'], 'aruba_aoscx': ['show interface brief'],
        'aruba_procurve': ['show interfaces brief'], 'juniper_junos': ['show interfaces terse']}),
    ('mac_table', 'show', 'MAC address table', {
        '*': ['show mac address-table'], 'aruba_aoscx': ['show mac-address-table'],
        'aruba_procurve': ['show mac-address'], 'juniper_junos': ['show ethernet-switching table']}),
    ('port_macs', 'show', 'MAC addresses on a port', {
        '*': ['show mac address-table interface {port}'], 'aruba_aoscx': ['show mac-address-table port {port}'],
        'aruba_procurve': ['show mac-address {port}'],
        'juniper_junos': ['show ethernet-switching table interface {port}']}),
    ('errors', 'show', 'Port errors', {
        '*': ['show interfaces counters errors'], 'aruba_aoscx': ['show interface {port} extended'],
        'aruba_procurve': ['show interfaces {port}'], 'juniper_junos': ['show interfaces {port} extensive']}),
    ('version', 'show', 'Software version', {'*': ['show version']}),
    ('clear_counters', 'change', 'Clear port counters', {
        '*': ['clear counters {port}'], 'aruba_aoscx': ['clear interface {port} statistics'],
        'aruba_procurve': ['clear statistics {port}'], 'juniper_junos': ['clear interfaces statistics {port}']}),
)


class CommandError(ValueError):
    def __init__(self, message, status=400, confirm=False):
        super().__init__(message)
        self.status = status
        self.confirm = confirm    # a change template that still needs its second confirmation


def _clean_command(text):
    text = ' '.join(str(text or '').split())
    if not text or len(text) > 200:
        raise CommandError('A command is empty or longer than 200 characters.')
    if re.search(r'\{(?!port\})', text):
        raise CommandError('{port} is the only placeholder a command can have.')
    return text


def check_template(body):
    """A custom template from an admin, checked. Raises CommandError."""
    tid = str(body.get('id') or '').strip().lower()
    if not ID_RE.match(tid) or tid in {b[0] for b in BUILTIN}:
        raise CommandError('The id is 2 to 32 lower-case letters, digits, - or _, and not a built-in one.')
    kind = body.get('kind')
    if kind not in KINDS:
        raise CommandError('Kind is show or change.')
    label = ' '.join(str(body.get('label') or '').split())[:80]
    if not label:
        raise CommandError('Give the template a name.')
    raw = body.get('commands')
    if isinstance(raw, str):
        raw = raw.splitlines()
    commands = [_clean_command(c) for c in raw or [] if str(c).strip()]
    if not commands or len(commands) > MAX_COMMANDS:
        raise CommandError(f'A template has 1 to {MAX_COMMANDS} commands.')
    if kind == 'show':
        bad = [c for c in commands if c.split()[0].lower() not in READ_WORDS]
        if bad:
            raise CommandError(f'"{bad[0]}" doesn\'t start with {", ".join(READ_WORDS)}: make it a change template.')
    return {'id': tid, 'kind': kind, 'label': label, 'commands': commands}


def custom_templates():
    return list(load_data().get(KEY) or [])


_save_lock = threading.Lock()


def save_template(body):
    tpl = check_template(body)
    with _save_lock:
        data = load_data()
        kept = [t for t in data.get(KEY) or [] if t.get('id') != tpl['id']]
        data[KEY] = [*kept, tpl][-100:]
        save_data(data)
    return tpl


def delete_template(tid):
    with _save_lock:
        data = load_data()
        kept = [t for t in data.get(KEY) or [] if t.get('id') != tid]
        if len(kept) == len(data.get(KEY) or []):
            return False
        data[KEY] = kept
        save_data(data)
    return True


def templates(platform):
    """Every template, with its commands for the plugin's switch software."""
    out = []
    for tid, kind, label, per in BUILTIN:
        out.append({'id': tid, 'kind': kind, 'label': label, 'commands': per.get(platform) or per['*'],
                    'builtin': True})
    for t in custom_templates():
        out.append({**t, 'builtin': False})
    for t in out:
        t['needs_port'] = any('{port}' in c for c in t['commands'])
    return out


def plugin(registry):
    """The port actions plugin, if it can run commands."""
    spec = ports.plugin(registry)
    if not spec:
        return None
    cls = spec.plugin_class()
    return spec if cls is not None and hasattr(cls, 'send_commands') else None


def platform(registry, spec):
    if spec is None:
        return 'cisco_ios'
    try:
        return str(registry.call(spec, 'command_platform') or 'cisco_ios')
    except (PluginError, AttributeError):
        return 'cisco_ios'


def info(registry, may_change):
    spec = plugin(registry)
    plat = platform(registry, spec)
    switches = sorted(
        d['name'] for d in inventory.devices(load_data(), include_hidden=True)
        if d.get('mgmt_ip') and d.get('role') in ('switch', 'router'))
    return {
        'available': spec is not None,
        'plugin': spec.name if spec else None,
        'needs_login': ports.info(registry)['needs_login'] if spec else False,
        'platform': plat,
        'templates': [t for t in templates(plat) if may_change or t['kind'] == 'show'],
        'may_change': may_change,
        'switches': switches,
        'max_switches': MAX_SWITCHES,
    }


def _one(registry, spec, dev, commands, login, max_output=MAX_OUTPUT):
    started = time.monotonic()
    name = dev['name']
    with ports._lock:
        if name in ports._busy:
            return {'switch': name, 'ok': False, 'error': f'Another action on {name} is still running.', 'output': ''}
        ports._busy.add(name)
    mine = dict(login) if login else None   # each connection gets its own copy, cleared after
    try:
        result = registry.call(spec, 'send_commands', {'switch': name, 'host': dev['mgmt_ip'],
                                                      'commands': commands, 'login': mine})
        output = str((result or {}).get('output') or '') if isinstance(result, dict) else str(result or '')
        refused = (result or {}).get('refused') if isinstance(result, dict) else None
        return {'switch': name, 'ok': not refused, 'output': output[-max_output:],
                'error': f'The switch refused "{refused}".' if refused else None,
                'ms': int((time.monotonic() - started) * 1000)}
    except PluginError as exc:
        return {'switch': name, 'ok': False, 'output': '', 'error': str(exc)[:300], 'login_failed':
                'login' in str(exc).lower(), 'ms': int((time.monotonic() - started) * 1000)}
    finally:
        if mine:
            mine.clear()
        with ports._lock:
            ports._busy.discard(name)


def run_on(registry, spec, account, body, commands, max_output=MAX_OUTPUT):
    """Run commands on ``body['switches']`` with the login in ``body``. Returns one result per switch.

    Shared by templates and config backups (floorbit/config_backup.py)."""
    names = body.get('switches')
    if not isinstance(names, list) or not names:
        raise CommandError('Pick at least one switch.')
    names = list(dict.fromkeys(str(n) for n in names))
    if len(names) > MAX_SWITCHES:
        raise CommandError(f'At most {MAX_SWITCHES} switches at a time.')
    data = load_data()
    try:
        devs = [ports._switch(data, n) for n in names]
    except ports.PortError as exc:
        raise CommandError(str(exc)) from None
    needs_login = ports.info(registry)['needs_login']
    try:
        login = ports._login(body, needs_login)
    except ports.PortError as exc:
        raise CommandError(str(exc)) from None
    body.pop('password', None)
    with ports._lock:
        try:
            ports._check_failures(account, time.time())
        except ports.PortError as exc:
            if login:
                login.clear()
            raise CommandError(str(exc), exc.status) from None
    try:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(devs))) as pool:
            results = list(pool.map(lambda d: _one(registry, spec, d, commands, login, max_output), devs))
    finally:
        if login:
            login.clear()
    failed_login = needs_login and any(r.get('login_failed') for r in results)
    with ports._lock:
        if failed_login:
            ports._failures.setdefault(account, []).append(time.time())
        elif any(r['ok'] for r in results):
            ports._failures.pop(account, None)
    for r in results:
        r.pop('login_failed', None)
    return results


def run(registry, account, body, may_change):
    """Run one template on the chosen switches. Returns (template, port, results)."""
    spec = plugin(registry)
    if not spec:
        raise CommandError('No plugin that can run switch commands is on. An admin turns on SSH port actions '
                           'under Settings > Plugins.', 409)
    plat = platform(registry, spec)
    tpl = next((t for t in templates(plat) if t['id'] == body.get('template')), None)
    if not tpl:
        raise CommandError('No such template.', 404)
    if tpl['kind'] == 'change':
        if not may_change:
            raise CommandError('Your role can run show commands only.', 403)
        if body.get('confirm') is not True:
            raise CommandError(f'"{tpl["label"]}" changes something on the switch. Confirm again to run it.', 409,
                               confirm=True)
    port = ''
    if tpl['needs_port']:
        port = str(body.get('port') or '').strip()
        if not ports.PORT_RE.match(port):
            raise CommandError('Type the port, for example Gi1/0/3.')
    commands = [c.replace('{port}', port) for c in tpl['commands']]
    results = run_on(registry, spec, account, body, commands)
    return tpl, port, commands, results
