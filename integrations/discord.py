"""Discord alerts through a channel webhook.

Listens for ``monitor.poll`` events and posts one message per poll that had
changes, so a whole row losing power is one message, not twenty. Sending runs
on its own thread so a slow Discord never delays the status monitor.
"""
import queue
import threading
import time
from datetime import UTC, datetime

import requests

from . import config, events

COLOR_OFFLINE = 0xF85149
COLOR_ONLINE = 0x3FB950
COLOR_INFO = 0xF0883E   # the app's orange accent
MAX_EMBEDS = 10         # Discord limit per message


def _fmt_duration(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}s'
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes}m {seconds}s'
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes}m'


class DiscordNotifier:
    def __init__(self):
        self._queue = queue.Queue(maxsize=100)
        self._last_alert = {}     # switch id -> ts
        self._thread = None
        self._lock = threading.Lock()
        self.last_sent = None
        self.last_error = None

    # ── config ────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def webhook():
        return config.get('DISCORD_WEBHOOK_URL', '') or ''

    def enabled(self):
        return bool(self.webhook()) and config.get_bool('DISCORD_ALERTS_ENABLED', True)

    # ── wiring ────────────────────────────────────────────────────────────────────────────
    def attach(self):
        events.subscribe('monitor.poll', self.on_poll)

    def _ensure_worker(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._worker, name='discord-notifier', daemon=True)
            self._thread.start()

    def _worker(self):
        while True:
            payload = self._queue.get()
            try:
                self.send(payload)
            except Exception as exc:  # noqa: BLE001  # keep the sender thread alive
                self.last_error = str(exc)
                print(f"[integrations] Discord send failed: {exc}")

    # ── message building ─────────────────────────────────────────────────────────────
    def on_poll(self, event):
        if not self.enabled():
            return
        payload = self.build_status_message(event['data'].get('changes', []))
        if payload:
            self._ensure_worker()
            try:
                self._queue.put_nowait(payload)
            except queue.Full:
                self.last_error = 'alert queue full, message dropped'

    def build_status_message(self, changes, now=None):
        now = now or time.time()
        cooldown = config.get_int('DISCORD_COOLDOWN', 300, minimum=0)
        notify_recovery = config.get_bool('DISCORD_NOTIFY_RECOVERY', True)

        selected = []
        for c in changes:
            if c['status'] == 'unknown':
                continue
            if c['status'] == 'online' and not notify_recovery:
                continue
            if c['status'] == 'online' and c.get('previous') == 'unknown':
                continue  # newly matched, not a recovery
            last = self._last_alert.get(c['id'])
            if last is not None and now - last < cooldown and c['status'] == 'offline':
                continue
            self._last_alert[c['id']] = now
            selected.append(c)

        if not selected:
            return None

        offline = [c for c in selected if c['status'] == 'offline']
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        ts = datetime.fromtimestamp(now, tz=UTC).isoformat()

        embeds = []
        for c in selected[:MAX_EMBEDS]:
            down = c['status'] == 'offline'
            fields = [{'name': 'Was', 'value': c.get('previous') or 'unknown', 'inline': True}]
            if not down and c.get('down_for'):
                fields.append({'name': 'Down for', 'value': _fmt_duration(c['down_for']), 'inline': True})
            if down and c.get('reason'):
                fields.append({'name': 'Reason', 'value': str(c['reason'])[:200], 'inline': True})
            embed = {
                'title': f"{'🔴' if down else '🟢'} {c['name']} is {'offline' if down else 'back online'}",
                'color': COLOR_OFFLINE if down else COLOR_ONLINE,
                'fields': fields,
                'timestamp': ts,
            }
            if public_url:
                embed['url'] = public_url
            embeds.append(embed)

        content = ''
        if offline:
            mention = config.get('DISCORD_MENTION', '') or ''
            content = f'{mention} ' if mention else ''
            content += (f'{len(offline)} switch{"es" if len(offline) != 1 else ""} went offline'
                        if len(offline) > 1 else '')
        if len(selected) > MAX_EMBEDS:
            content += f' (+{len(selected) - MAX_EMBEDS} more)'

        payload = {
            'username': config.get('DISCORD_USERNAME', 'Floorbit'),
            'embeds': embeds,
            'allowed_mentions': {'parse': ['roles', 'everyone', 'users']},
        }
        if content.strip():
            payload['content'] = content.strip()
        return payload

    def build_test_message(self):
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        embed = {
            'title': '✅ Discord alerts are connected',
            'description': ('This channel will get a message when a switch on the floor plan '
                            'goes offline or comes back.'),
            'color': COLOR_INFO,
            'timestamp': datetime.now(tz=UTC).isoformat(),
        }
        if public_url:
            embed['url'] = public_url
        return {
            'username': config.get('DISCORD_USERNAME', 'Floorbit'),
            'embeds': [embed],
            'allowed_mentions': {'parse': []},
        }

    # ── sending ───────────────────────────────────────────────────────────────────────────
    def send(self, payload, retries=2):
        url = self.webhook()
        if not url:
            raise RuntimeError('DISCORD_WEBHOOK_URL is not set')
        for attempt in range(retries + 1):
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 429 and attempt < retries:
                try:
                    wait = float(resp.json().get('retry_after', 1))
                except ValueError:
                    wait = 1.0
                time.sleep(min(wait, 30))
                continue
            if resp.status_code >= 400:
                self.last_error = f'Discord answered {resp.status_code}: {resp.text[:200]}'
                raise RuntimeError(self.last_error)
            self.last_sent = time.time()
            self.last_error = None
            return True
        return False

    def info(self):
        return {
            'enabled': self.enabled(),
            'configured': bool(self.webhook()),
            'last_sent': self.last_sent,
            'last_error': self.last_error,
        }
