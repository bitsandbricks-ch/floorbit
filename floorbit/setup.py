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

STEPS = ('netbox', 'librenms', 'switches', 'theme')
STATES = ('done', 'skipped')
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
        raise SetupError('A step is done or skipped.')
    with _lock:
        data = load_data()
        rec = data.setdefault('setup', {'done': False, 'steps': {}})
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
