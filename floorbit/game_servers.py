"""Game servers (issue #472): are they up, how full, which map, and an RCON console for the crew.

- **Servers** are kept in data.json (``game_servers``): name, game, host, port and how to ask it
  (``floorbit/game_query.py``: A2S, Minecraft or only TCP), and optionally an RCON port and password.
- **The RCON password** is sealed with floorbit/vault.py like the switch logins: write-only, opened
  only for one command. Setting, changing and removing servers needs ``settings.manage``.
- **Polling**: a background thread asks every server each ``GAME_INTERVAL`` seconds (default 30) and
  keeps the last answer and a short player history. With a local agent connected the agent asks
  instead, from the event network. The servers also show on the service health wall.
- **RCON** needs ``games.rcon`` (tech and up). Every command is in the audit log (a command that
  sets a password only by its name), and commands that stop the server, change the map or throw
  players out need ``confirm``.
"""
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from integrations import config

from . import game_query, probes, vault
from .store import load_data, save_data

KEY = 'game_servers'
MAX = 60
HISTORY = 60                       # player counts kept per server (30 minutes at the default interval)
NAME_RE = re.compile(r'^[^\x00-\x1f]{1,60}$')
HOST_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9.-]{0,252}|[0-9a-fA-F:.]{0,44})$')
# First words of commands that stop the server, change the map or throw players out.
DESTRUCTIVE = frozenset((
    'quit', 'exit', 'stop', 'shutdown', 'restart', '_restart', 'killserver', 'kill', 'ban', 'banid', 'banip',
    'addip', 'kick', 'kickid', 'kickall', 'changelevel', 'map', 'host_workshop_map', 'host_workshop_collection',
    'mp_restartgame', 'mp_warmup_end', 'exec', 'deop', 'op', 'pardon', 'whitelist', 'save-off', 'wipe',
    'kill-all', 'reload', 'sv_password', 'rcon_password', 'removeid', 'writeid',
))
MAX_COMMAND = 500
_lock = threading.Lock()


class GameServerError(ValueError):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


def _slot(server_id):
    return f'rcon:{server_id}'


def _all(data=None):
    data = load_data() if data is None else data
    return [s for s in data.get(KEY) or [] if isinstance(s, dict) and s.get('id')]


def _port(value, message, required=True):
    if value in (None, '') and not required:
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        raise GameServerError(message)
    return port


def _clean(body, old=None):
    old = old or {}
    name = ' '.join(str(body.get('name', old.get('name')) or '').split())
    if not NAME_RE.match(name):
        raise GameServerError('Give the server a name (up to 60 characters).')
    host = str(body.get('host', old.get('host')) or '').strip()
    if not HOST_RE.match(host):
        raise GameServerError('The host is an IP address or a host name.')
    query = body.get('query', old.get('query') or 'a2s')
    if query not in game_query.PROTOCOLS:
        raise GameServerError('The query is a2s, minecraft or tcp.')
    game = ' '.join(str(body.get('game', old.get('game')) or '').split())[:40]
    return {'name': name, 'game': game, 'host': host, 'query': query,
            'port': _port(body.get('port', old.get('port')), 'The port is a number from 1 to 65535.'),
            'rcon_port': _port(body.get('rcon_port', old.get('rcon_port')),
                               'The RCON port is a number from 1 to 65535.', required=False)}


def public(server):
    """A server as the API shows it: never the RCON password, only whether one is set."""
    return {k: server.get(k) for k in ('id', 'name', 'game', 'host', 'port', 'query', 'rcon_port')} | {
        'rcon': bool(server.get('rcon_port') and server.get('rcon_password'))}


def listing():
    return [public(s) for s in sorted(_all(), key=lambda s: s['name'].lower())]


def get(server_id):
    return next((s for s in _all() if s['id'] == server_id), None)


def save(body, server_id=None):
    """Add a server, or change one. ``rcon_password`` sets the password, ``clear_rcon`` removes it,
    neither keeps it."""
    password = body.get('rcon_password')
    if password not in (None, '') and (not isinstance(password, str) or len(password) > 256 or '\n' in password):
        raise GameServerError('The RCON password is one line of up to 256 characters.')
    with _lock:
        data = load_data()
        rows = data.setdefault(KEY, [])
        server = next((s for s in rows if s.get('id') == server_id), None) if server_id else None
        if server_id and server is None:
            raise GameServerError('No such game server.', 404)
        fields = _clean(body, server)
        clash = next((s for s in rows if s is not server and s.get('name', '').lower() == fields['name'].lower()), None)
        if clash:
            raise GameServerError(f"There is already a game server called {fields['name']}.", 409)
        if server is None:
            if len(rows) >= MAX:
                raise GameServerError(f'Floorbit keeps at most {MAX} game servers.')
            server = {'id': uuid.uuid4().hex[:12]}
            rows.append(server)
        server.update(fields)
        if body.get('clear_rcon'):
            server.pop('rcon_password', None)
        elif password:
            server['rcon_password'] = vault.seal(_slot(server['id']), password)
        save_data(data)
    return public(server)


def delete(server_id):
    with _lock:
        data = load_data()
        rows = data.get(KEY) or []
        gone = next((s for s in rows if s.get('id') == server_id), None)
        if gone is None:
            return None
        data[KEY] = [s for s in rows if s is not gone]
        save_data(data)
    poller.forget(server_id)
    return public(gone)


def rotate():
    """Seal every RCON password again with the current key. Returns how many."""
    with _lock:
        data = load_data()
        done = 0
        for server in data.get(KEY) or []:
            if server.get('rcon_password') and vault.needs_rotation(server['rcon_password']):
                slot = _slot(server['id'])
                server['rcon_password'] = vault.seal(slot, vault.open_(slot, server['rcon_password']))
                done += 1
        if done:
            save_data(data)
    return done


# ── asking the servers ──────────────────────────────────────────────────────
def _via_agent():
    from . import agent_link
    return agent_link.active()


def _ask(method, *args):
    """Run a query here, or on the local agent when one is enrolled (it is on the event network)."""
    demo = probes.stood_in(method, args)
    if demo is not None:
        return demo
    if not _via_agent():
        # The host is the second argument of a query (after the protocol), the first of RCON.
        at = 1 if method == 'game_query' else 0
        try:
            args = (*args[:at], probes.target(args[at]), *args[at + 1:])
        except probes.ProbeError as exc:
            raise game_query.QueryError(str(exc)) from None
        if method == 'game_query':
            return game_query.query(*args)
        return game_query.rcon(*args)
    from . import agent_link
    try:
        return agent_link.tunnel.call(method, args, timeout=10)
    except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
        raise game_query.QueryError(str(exc)) from None


def _number(value, top=100000):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= top else 0


# Minecraft's colour and format codes (§a, §l...): noise outside the game.
FORMAT_CODES = re.compile('\u00a7[0-9a-fk-orA-FK-OR]')


def _plain(text):
    return FORMAT_CODES.sub('', str(text or ''))


def _info(raw):
    """What came back (from here or from the agent), as plain values."""
    raw = raw if isinstance(raw, dict) else {}
    text = {k: ' '.join(_plain(raw.get(k)).split())[:120] for k in ('name', 'map', 'game', 'version')}
    ping = raw.get('ping_ms')
    return {**text, 'players': _number(raw.get('players')), 'max_players': _number(raw.get('max_players')),
            'bots': _number(raw.get('bots')),
            'ping_ms': round(float(ping), 1) if isinstance(ping, (int, float)) and not isinstance(ping, bool) else None}


class Poller:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {}          # server id -> {status, info, error, checked_at, since, history}
        self._thread = None
        self._stop = threading.Event()
        self.last_poll = None

    @staticmethod
    def interval():
        return config.get_int('GAME_INTERVAL', 30, minimum=10)

    def forget(self, server_id):
        with self._lock:
            self._state.pop(server_id, None)

    def reset(self):
        with self._lock:
            self._state = {}
            self.last_poll = None

    def check(self, server, now=None):
        """Ask one server now; returns its state."""
        now = time.time() if now is None else now
        try:
            info, error, status = _info(_ask('game_query', server['query'], server['host'], server['port'])), '', 'up'
        except game_query.QueryError as exc:
            info, error, status = None, str(exc), 'down'
        with self._lock:
            old = self._state.get(server['id']) or {}
            history = [*(old.get('history') or [])[-(HISTORY - 1):], [round(now), info['players'] if info else None]]
            state = {'status': status, 'info': info or old.get('info'), 'error': error, 'checked_at': now,
                     'since': old['since'] if old.get('status') == status else now, 'history': history}
            self._state[server['id']] = state
        return state

    def poll_once(self, now=None):
        servers = _all()
        if servers:
            with ThreadPoolExecutor(min(8, len(servers))) as pool:
                list(pool.map(lambda s: self.check(s, now), servers))
        with self._lock:
            known = {s['id'] for s in servers}
            for gone in set(self._state) - known:
                self._state.pop(gone)
            self.last_poll = time.time() if now is None else now

    def state(self, server_id):
        with self._lock:
            return dict(self._state.get(server_id) or {'status': 'unknown', 'info': None, 'error': '',
                                                        'checked_at': None, 'since': None, 'history': []})

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='game-servers', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                if _all():
                    self.poll_once()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                print(f'[game-servers] poll failed: {exc}')
            self._stop.wait(self.interval())


poller = Poller()


def overview():
    """Every server with how it was the last time it was asked."""
    servers = listing()
    if servers and poller.last_poll is None and not poller.running():
        poller.poll_once()          # no background thread (tests, a one-off): ask now rather than show all grey
    rows = [{**s, **poller.state(s['id'])} for s in servers]
    return {'servers': rows, 'interval': poller.interval(), 'last_poll': poller.last_poll,
            'via_agent': _via_agent(),
            'counts': {k: sum(r['status'] == k for r in rows) for k in ('up', 'down', 'unknown')},
            'players': sum((r['info'] or {}).get('players') or 0 for r in rows if r['status'] == 'up')}


def health_checks():
    """The servers as tiles of the service health wall (floorbit/health.py)."""
    out = []
    for server in listing():
        state = poller.state(server['id'])
        info = state['info'] or {}
        if state['status'] == 'up':
            summary = f"{info.get('players', 0)}/{info.get('max_players', 0)} players"
            if info.get('map'):
                summary += f" on {info['map']}"
        elif state['status'] == 'down':
            summary = state['error'] or 'Does not answer.'
        else:
            summary = 'Not asked yet.'
        metrics = [] if state['status'] != 'up' else [
            {'label': 'Players', 'value': info.get('players', 0), 'unit': f"/{info.get('max_players', 0)}", 'tone': ''},
            {'label': 'Ping', 'value': info.get('ping_ms'), 'unit': 'ms', 'tone': ''}]
        out.append({'id': f"game:{server['id']}", 'name': server['name'], 'kind': 'game', 'status': state['status'],
                    'summary': summary, 'link': '/game-servers', 'metrics': metrics,
                    'plugin': 'game-servers', 'plugin_name': 'Game servers'})
    return out


# ── RCON ────────────────────────────────────────────────────────────────────
def destructive(command):
    first = command.strip().split(None, 1)[0].lower() if command.strip() else ''
    return first in DESTRUCTIVE


def for_audit(command):
    """The command as the audit log keeps it: one that sets a password only by its first word."""
    words = command.strip().split(None, 1)
    if len(words) > 1 and ('password' in words[0].lower() or words[0].lower() in ('login', 'auth')):
        return f'{words[0]} …'
    return command.strip()[:200]


def run_rcon(server_id, command, confirm=False):
    """Send one RCON command. Returns ``(server, answer)``; GameServerError for what the crew can fix."""
    server = get(server_id)
    if server is None:
        raise GameServerError('No such game server.', 404)
    if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND or '\n' in command:
        raise GameServerError(f'Type one command (up to {MAX_COMMAND} characters, one line).')
    if not server.get('rcon_port') or not server.get('rcon_password'):
        raise GameServerError('RCON is not set up for this server. An admin adds the RCON port and password.', 409)
    if destructive(command) and not confirm:
        raise GameServerError('This command can stop the server, change the map or throw players out. '
                              'Confirm to send it.', 409, confirm=True)
    try:
        password = vault.open_(_slot(server['id']), server['rcon_password'])
    except vault.VaultError as exc:
        raise GameServerError(str(exc), 500) from None
    try:
        answer = _ask('game_rcon', server['host'], server['rcon_port'], password, command.strip())
    except game_query.QueryError as exc:
        raise GameServerError(str(exc), 502) from None
    finally:
        del password
    return public(server), _plain(answer)[:game_query.MAX_ANSWER]


def init_app(app, start_background=True):
    app.extensions['floorbit_game_servers'] = poller
    started = threading.Event()

    @app.before_request
    def start_game_servers_once():
        if start_background and not started.is_set():
            started.set()
            poller.start()
