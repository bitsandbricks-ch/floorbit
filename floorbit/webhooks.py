"""Outgoing webhooks (issue #40). See docs/api.md#webhooks.

An admin adds a URL and picks events; Floorbit POSTs each one as JSON, signed with the hook's
secret, so other tools can react without polling: a scoreboard, a ticket system, a chat bot.

The events come from the live event bus (integrations/events.py) and are reshaped here into a small,
stable set, so the bus can change without breaking anybody's receiver. Payloads carry no nicks, IPs
or MACs: a check-in says which seat, not who.

Delivery runs in a background thread with retries (10 s, 1 min, 5 min). Redirects are not followed.
The last deliveries of each hook are kept in memory for Settings > Webhooks. Kept in data.json under
``webhooks``; backups never include them, because of the secrets.
"""
import collections
import contextlib
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from urllib.parse import urlsplit

from .store import load_data, save_data

KEY = 'webhooks'
MAX_HOOKS = 20
TIMEOUT = 5
RETRY_DELAYS = (10, 60, 300)
LOG_SIZE = 20
NAME_RE = re.compile(r'^[^\x00-\x1f<>]{1,60}$')
# The events a hook can pick, in the order the settings page lists them.
EVENTS = ('switch.down', 'switch.up', 'monitoring.offline', 'monitoring.online', 'incident.opened',
          'incident.changed', 'seat.checked_in', 'security.finding', 'power.alert', 'health.changed',
          'forecast.alert', 'logs.alert')

_lock = threading.Lock()
_queue = collections.deque()          # jobs waiting to be sent
_log = collections.defaultdict(lambda: collections.deque(maxlen=LOG_SIZE))
_wake = threading.Event()


class WebhookError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ── Settings ─────────────────────────────────────────────────────────────────────────
def _hooks(data):
    raw = data.get(KEY)
    return [h for h in raw if isinstance(h, dict) and h.get('id')] if isinstance(raw, list) else []


def public(hook):
    return {k: hook.get(k) for k in ('id', 'name', 'url', 'events', 'active', 'created_at', 'created_by',
                                     'last')} | {'deliveries': list(_log.get(hook['id'], ()))[::-1]}


def all_hooks():
    return [public(h) for h in _hooks(load_data())]


def _clean(body, partial=False):
    out = {}
    if not partial or 'name' in body:
        name = str(body.get('name') or '').strip()
        if not NAME_RE.match(name):
            raise WebhookError('Give the webhook a name (up to 60 characters).')
        out['name'] = name
    if not partial or 'url' in body:
        url = str(body.get('url') or '').strip()
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or len(url) > 500:
            raise WebhookError('The URL must start with https:// (or http://) and name a host.')
        out['url'] = url
    if not partial or 'events' in body:
        events = body.get('events')
        if not isinstance(events, list) or not events or any(e not in EVENTS for e in events):
            raise WebhookError(f"Pick at least one event: {', '.join(EVENTS)}.")
        out['events'] = [e for e in EVENTS if e in events]
    if 'active' in body:
        out['active'] = bool(body['active'])
    return out


def create(body, user=None):
    """Add a hook. Returns (hook, secret): the secret is shown once."""
    fields = _clean(body if isinstance(body, dict) else {})
    secret = 'whsec_' + secrets.token_urlsafe(24)
    with _lock:
        data = load_data()
        hooks = _hooks(data)
        if len(hooks) >= MAX_HOOKS:
            raise WebhookError(f'There are already {MAX_HOOKS} webhooks. Remove one you no longer use.')
        hook = {'id': uuid.uuid4().hex[:10], **fields, 'active': fields.get('active', True), 'secret': secret,
                'created_at': time.time(), 'created_by': user, 'last': None}
        data[KEY] = [*hooks, hook]
        save_data(data)
    return public(hook), secret


def _change(hook_id, fn):
    with _lock:
        data = load_data()
        hooks = _hooks(data)
        hook = next((h for h in hooks if h['id'] == hook_id), None)
        if not hook:
            raise WebhookError('No such webhook.', 404)
        result = fn(hooks, hook)
        data[KEY] = hooks
        save_data(data)
    return result


def update(hook_id, body):
    fields = _clean(body if isinstance(body, dict) else {}, partial=True)
    return _change(hook_id, lambda hooks, hook: public(hook.update(fields) or hook))


def new_secret(hook_id):
    secret = 'whsec_' + secrets.token_urlsafe(24)
    hook = _change(hook_id, lambda hooks, hook: public(hook.update(secret=secret) or hook))
    return hook, secret


def delete(hook_id):
    hook = _change(hook_id, lambda hooks, hook: hooks.remove(hook) or public(hook))
    _log.pop(hook_id, None)
    return hook


# ── From the event bus to webhook events ─────────────────────────────────────────────
def _incident(data):
    from . import incidents
    found = incidents.get(data.get('id')) or {}
    if not found:
        return None
    return {k: found.get(k) for k in ('id', 'title', 'status', 'seat', 'switch_name', 'circuit_name', 'team',
                                      'assignee', 'source', 'created_at', 'updated_at')}


def translate(event):
    """[(webhook event, payload)] for one bus event; most bus events are none of ours."""
    kind, data = event.get('type'), event.get('data') or {}
    if kind == 'switch.status' and data.get('status') in ('online', 'offline'):
        name = 'switch.down' if data['status'] == 'offline' else 'switch.up'
        return [(name, {k: data.get(k) for k in ('id', 'name', 'since', 'down_for', 'reason')})]
    if kind in ('monitoring.offline', 'monitoring.online'):
        return [(kind, {k: data.get(k) for k in ('source', 'error', 'since', 'down_for') if k in data})]
    if kind == 'incident.changed':
        incident = _incident(data)
        opened = data.get('action') in ('created', 'reported')
        return [('incident.opened' if opened else 'incident.changed', incident)] if incident else []
    if kind == 'checkin':   # which seat, never who: nicks, IPs and MACs stay in Floorbit
        return [('seat.checked_in', {'seat': data.get('seat'), 'moved_from': data.get('moved_from')})]
    if kind == 'security.finding':
        return [(kind, {k: data.get(k) for k in ('id', 'kind', 'severity', 'switch', 'port', 'seat')})]
    if kind == 'power.alert':
        return [(kind, {k: v for k, v in data.items() if k not in ('ips', 'nicks')})]
    if kind == 'health.changed':
        return [(kind, {'changes': data.get('changes') or []})]
    if kind == 'forecast.alert':
        return [(kind, {k: data.get(k) for k in ('t', 'bps', 'pct', 'capacity_bps')})]
    if kind == 'logs.alert':   # the pattern and where, never the line: it can name MACs and IPs
        return [(kind, {k: data.get(k) for k in ('id', 'pattern', 'title', 'device', 'port', 'seat')})]
    return []


def on_event(event):
    out = translate(event)
    if not out:
        return
    hooks = [h for h in _hooks(load_data()) if h.get('active')]
    for name, payload in out:
        for hook in hooks:
            if name in (hook.get('events') or []):
                enqueue(hook, name, payload)


# ── Delivery ─────────────────────────────────────────────────────────────────────────
def sign(secret, ts, body):
    return hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()


def enqueue(hook, name, payload):
    delivery = uuid.uuid4().hex
    body = json.dumps({'event': name, 'delivery': delivery, 'ts': time.time(), 'data': payload},
                      default=str).encode()
    with _lock:
        _queue.append({'hook': hook['id'], 'event': name, 'delivery': delivery, 'body': body, 'attempt': 0,
                       'due': 0})
    _wake.set()


def _send(hook, job):
    import requests
    ts = str(int(time.time()))
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Floorbit-Webhooks/1',
               'Floorbit-Event': job['event'], 'Floorbit-Delivery': job['delivery'],
               'Floorbit-Signature': f"t={ts},v1={sign(hook['secret'], ts, job['body'])}"}
    try:
        resp = requests.post(hook['url'], data=job['body'], headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.exceptions.RequestException as exc:
        return False, None, type(exc).__name__
    ok = 200 <= resp.status_code < 300
    return ok, resp.status_code, None if ok else f'Answered {resp.status_code}'


def _record(hook_id, job, ok, status, error):
    entry = {'at': time.time(), 'event': job['event'], 'delivery': job['delivery'], 'ok': ok, 'status': status,
             'error': error, 'attempt': job['attempt'] + 1}
    _log[hook_id].append(entry)
    with contextlib.suppress(WebhookError):   # removed while it was being sent
        _change(hook_id, lambda hooks, hook: hook.update(last=entry))


def _run_job(job):
    hook = next((h for h in _hooks(load_data()) if h['id'] == job['hook']), None)
    if not hook or not hook.get('active'):
        return
    ok, status, error = _send(hook, job)
    _record(hook['id'], job, ok, status, error)
    if not ok and job['attempt'] < len(RETRY_DELAYS):
        with _lock:
            _queue.append({**job, 'due': time.time() + RETRY_DELAYS[job['attempt']], 'attempt': job['attempt'] + 1})


def drain(now=None, ignore_due=False):
    """Send every job that is due. The worker calls this; tests call it with ignore_due."""
    now = time.time() if now is None else now
    with _lock:
        due = [j for j in _queue if ignore_due or j['due'] <= now]
        for j in due:
            _queue.remove(j)
    for job in due:
        _run_job(job)
    return len(due)


def pending():
    with _lock:
        return len(_queue)


def test(hook_id):
    """Send a ping now and answer how it went."""
    hook = next((h for h in _hooks(load_data()) if h['id'] == hook_id), None)
    if not hook:
        raise WebhookError('No such webhook.', 404)
    job = {'hook': hook_id, 'event': 'ping', 'delivery': uuid.uuid4().hex, 'attempt': 0,
           'body': json.dumps({'event': 'ping', 'ts': time.time(), 'data': {'hook': hook['name']}}).encode()}
    ok, status, error = _send(hook, job)
    _record(hook_id, job, ok, status, error)
    return {'ok': ok, 'status': status, 'error': error}


def _worker():
    while True:
        _wake.wait(timeout=1)
        _wake.clear()
        try:
            drain()
        except Exception as exc:  # noqa: BLE001  # the sender must outlive one bad hook
            print(f'[webhooks] sending failed: {exc}')


def init_webhooks(app, start_background=True):
    from integrations import events
    events.subscribe_once('*', on_event)
    started = threading.Event()

    @app.before_request
    def start_sender_once():
        # Started on the first request, like the status monitor: the debug reloader imports twice.
        if start_background and not started.is_set():
            started.set()
            threading.Thread(target=_worker, name='webhooks', daemon=True).start()
