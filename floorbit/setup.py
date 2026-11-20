"""First-run setup (issue #13): see docs/install.md.

A new install walks its first admin through creating their account, connecting NetBox and
LibreNMS, importing switches and picking a theme. Every step can be skipped and done later in
Settings; the steps themselves use the existing settings, test and sync APIs.

Stored in data.json under ``setup``: ``{done, steps: {step: 'done'|'skipped'}, finished_at, by}``.
An install from before this existed (it already has switches, blocks or settings) counts as set up.

The first account can be made in the browser only with the setup code that Floorbit prints to its
log while it has no accounts, so whoever reaches a fresh server first can't make themselves admin.
"""
import hmac
import secrets
import threading
import time

from .store import load_data, save_data

# The first-run wizard's steps, then the checklist's (#988), which can be skipped too.
STEPS = ('netbox', 'librenms', 'switches', 'theme',
         'event', 'inventory', 'monitoring', 'floor', 'seats', 'alerts', 'crew')
CHECKLIST = ('event', 'inventory', 'monitoring', 'floor', 'seats', 'alerts', 'crew')
STATES = ('done', 'skipped', 'open')   # open: forget a skip
MAX_CODE_TRIES = 10       # wrong codes before the code is replaced (and printed again)

_lock = threading.Lock()


class SetupError(ValueError):
    pass


def _has_content(data):
    return any(data.get(k) for k in ('inventory', 'switches', 'seat_blocks', 'seats', 'app_settings'))


def _has_floor(data):
    return any(data.get(k) for k in ('inventory', 'switches', 'seat_blocks', 'seats'))


def state(data=None):
    data = load_data() if data is None else data
    found = data.get('setup')
    if found is None:
        return {'done': _has_content(data), 'steps': {}, 'auto': _has_content(data)}
    return {'done': bool(found.get('done')), 'steps': dict(found.get('steps') or {}),
            'finished_at': found.get('finished_at'), 'by': found.get('by')}


def needed():
    return not state()['done']


def mark_existing():
    """Start the record: an install that has content but no record was set up before this page
    existed. A new one gets an open record now, so a setting saved during setup doesn't end it."""
    with _lock:
        data = load_data()
        found = data.get('setup')
        if found is None:
            data['setup'] = {'done': True, 'steps': {}, 'auto': True} if _has_content(data) \
                else {'done': False, 'steps': {}}
            save_data(data)
        elif not found.get('done') and not found.get('steps') and _has_floor(data):
            # Nobody started the setup, but the floor plan filled up anyway (the demo hall, a
            # restored backup, `flask users add` run before the first start): it is in use.
            found.update(done=True, auto=True)
            save_data(data)


def set_step(step, value):
    if step not in STEPS:
        raise SetupError(f'Unknown step: {step}')
    if value not in STATES:
        raise SetupError('A step is done, skipped or open.')
    with _lock:
        data = load_data()
        rec = data.setdefault('setup', {'done': False, 'steps': {}})
        if value == 'open':
            rec.setdefault('steps', {}).pop(step, None)
        else:
            rec.setdefault('steps', {})[step] = value
        save_data(data)
        return state(data)


def finish(user):
    with _lock:
        data = load_data()
        rec = data.setdefault('setup', {'done': False, 'steps': {}})
        rec.update(done=True, finished_at=time.time(), by=user)
        save_data(data)
        return state(data)


def _step(step_id, done, started, href, skipped, **facts):
    """One checklist step: done, needs a look (started but not done), skipped or not started."""
    status = 'done' if done else 'skipped' if skipped.get(step_id) == 'skipped' else 'look' if started else 'todo'
    return {'id': step_id, 'state': status, 'href': href, 'facts': facts}


def checklist(data, settings, agents=(), users=0, teams=0, hooks=0, monitoring=False, event_dates=None, mapped=0):
    """What an event needs, in the order it is done (#988): each step's state from what is really
    there, with the one place it is set. The caller gathers what lives outside ``data``.

    ``settings`` is the settings store (``get``); ``agents`` the enrolled agents; ``mapped`` the
    seats that have a switch port; ``monitoring`` whether a monitoring plugin is on and set up."""
    skipped = state(data).get('steps', {})
    devices = [d for d in data.get('inventory') or [] if not d.get('hidden')]
    placed = sum(d.get('x') is not None for d in devices)
    blocks = len(data.get('seat_blocks') or [])
    netbox = bool(settings.get('netbox.url') and settings.get('netbox.token'))
    librenms = bool(settings.get('librenms.url') and settings.get('librenms.token'))
    connected = sum(1 for a in agents if a.get('connected'))
    checkin = bool(settings.get('integrations.checkin_enabled'))
    discord = bool(settings.get('integrations.discord_webhook_url') or settings.get('integrations.discord_bot_token'))
    name = bool((settings.get('theme.name') or '').strip())
    dates = bool(event_dates and event_dates.get('start'))
    logo = bool(settings.get('theme.logo'))
    source = librenms or monitoring
    return [
        _step('event', name and dates, name or dates or logo, '/settings/appearance' if not name else '/schedule',
              skipped, name=name, dates=dates, logo=logo),
        _step('inventory', bool(devices), netbox, '/inventory' if netbox or devices else '/settings/plugins/netbox',
              skipped, devices=len(devices), netbox=netbox),
        _step('monitoring', connected > 0 and source, bool(agents) or source,
              '/settings/agents' if not agents or source else '/settings/plugins/librenms',
              skipped, agents=len(agents), connected=connected, source=source),
        _step('floor', blocks > 0 and placed > 0, blocks > 0 or placed > 0, '/plan', skipped,
              blocks=blocks, placed=placed, devices=len(devices)),
        _step('seats', mapped > 0, checkin, '/seat-mapping' if mapped or not checkin else '/settings/checkin', skipped,
              mapped=mapped, checkin=checkin),
        _step('alerts', discord or hooks > 0, False,
              '/settings/discord', skipped, discord=discord, webhooks=hooks),
        _step('crew', users > 1, teams > 0, '/settings/users', skipped, users=users, teams=teams),
    ]


class SetupCode:
    """The one-time code for making the first account in the browser. Kept in memory only."""

    def __init__(self, log=print):
        self._log = log
        self._code = None
        self._tries = 0

    def issue(self):
        # Easy to type from a log: 4+4 characters without look-alikes.
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        raw = ''.join(secrets.choice(alphabet) for _ in range(8))
        self._code, self._tries = f'{raw[:4]}-{raw[4:]}', 0
        self._log(f'[setup] No accounts yet. Open /setup and enter the setup code {self._code} '
                  'to create the first admin (or: flask --app app users add <name>).')
        return self._code

    def check(self, given):
        if self._code is None:
            self.issue()
        ok = hmac.compare_digest(str(given or '').strip().upper().encode(), self._code.encode())
        if ok:
            self._code = None
            return True
        self._tries += 1
        if self._tries >= MAX_CODE_TRIES:
            self.issue()
        return False
