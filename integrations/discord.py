"""Discord alerts through a channel webhook.

Listens for ``monitor.poll`` events and posts one message per poll that had
changes, so a whole row losing power is one message, not twenty. ``health.changed`` (the
service health wall) posts when a service goes red and when it is back. Sending runs
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
SECURITY_KINDS = {'rogue-dhcp': 'Rogue DHCP server', 'arp-spoof': 'ARP spoofing', 'mac-flap': 'MAC flapping',
                  'loop': 'Network loop', 'storm': 'Broadcast storm', 'other': 'Security finding'}


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
        events.subscribe('monitoring.offline', self.on_source)
        events.subscribe('monitoring.online', self.on_source)
        events.subscribe('health.changed', self.on_health)
        events.subscribe('security.finding', self.on_security)

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

    def on_source(self, event):
        """The monitoring source itself went away or came back: one message, not one per switch."""
        if not self.enabled():
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait(self.build_source_message(event['type'], event.get('data') or {}))
        except queue.Full:
            self.last_error = 'alert queue full, message dropped'

    def on_health(self, event):
        if not self.enabled() or not config.get_bool('DISCORD_HEALTH_ALERTS', True):
            return
        payload = self.build_health_message((event.get('data') or {}).get('changes', []))
        if payload:
            self._ensure_worker()
            try:
                self._queue.put_nowait(payload)
            except queue.Full:
                self.last_error = 'alert queue full, message dropped'

    def build_health_message(self, changes, now=None):
        """Red services, and (if wanted) services that were red and are back. Amber pages nobody."""
        now = now or time.time()
        cooldown = config.get_int('DISCORD_COOLDOWN', 300, minimum=0)
        notify_recovery = config.get_bool('DISCORD_NOTIFY_RECOVERY', True)
        selected = []
        for c in changes:
            down = c.get('status') == 'down'
            back = c.get('previous') == 'down' and c.get('status') in ('up', 'warn')
            if not down and not (back and notify_recovery):
                continue
            key = 'health:' + str(c.get('id'))
            last = self._last_alert.get(key)
            if down and last is not None and now - last < cooldown:
                continue
            self._last_alert[key] = now
            selected.append(c)
        if not selected:
            return None
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        ts = datetime.fromtimestamp(now, tz=UTC).isoformat()
        embeds = []
        for c in selected[:MAX_EMBEDS]:
            down = c['status'] == 'down'
            embed = {'title': f"{'🔴' if down else '🟢'} {str(c.get('name'))[:100]} is {'down' if down else 'back'}",
                     'color': COLOR_OFFLINE if down else COLOR_ONLINE, 'timestamp': ts}
            if c.get('summary'):
                embed['description'] = str(c['summary'])[:200]
            if public_url:
                embed['url'] = public_url + '/health'
            embeds.append(embed)
        payload = {'username': config.get('DISCORD_USERNAME', 'Floorbit'), 'embeds': embeds,
                   'allowed_mentions': {'parse': ['roles', 'everyone', 'users']}}
        mention = config.get('DISCORD_MENTION', '') or ''
        if mention and any(c['status'] == 'down' for c in selected):
            payload['content'] = mention
        else:
            payload['allowed_mentions'] = {'parse': []}
        return payload

    def on_security(self, event):
        if not self.enabled() or not config.get_bool('DISCORD_SECURITY_ALERTS', True):
            return
        payload = self.build_security_message(event.get('data') or {})
        if payload:
            self._ensure_worker()
            try:
                self._queue.put_nowait(payload)
            except queue.Full:
                self.last_error = 'alert queue full, message dropped'

    def build_security_message(self, finding, now=None):
        """High and medium findings. Where, not who: no MAC or IP goes to Discord."""
        if finding.get('severity') not in ('high', 'medium'):
            return None
        now = now or time.time()
        key = 'security:' + str(finding.get('id'))
        last = self._last_alert.get(key)
        if last is not None and now - last < config.get_int('DISCORD_COOLDOWN', 300, minimum=0):
            return None
        self._last_alert[key] = now
        where = ' '.join(str(finding.get(k) or '') for k in ('switch', 'port')).strip() or 'unknown port'
        fields = [{'name': 'Where', 'value': where[:100], 'inline': True}]
        if finding.get('seat'):
            fields.append({'name': 'Seat', 'value': str(finding['seat'])[:20], 'inline': True})
        fields.append({'name': 'Severity', 'value': str(finding.get('severity')), 'inline': True})
        embed = {'title': f"🛡️ {SECURITY_KINDS.get(finding.get('kind'), 'Security finding')}",
                 'color': COLOR_OFFLINE if finding.get('severity') == 'high' else COLOR_INFO,
                 'fields': fields, 'timestamp': datetime.fromtimestamp(now, tz=UTC).isoformat()}
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        if public_url:
            embed['url'] = public_url + '/security'
        payload = {'username': config.get('DISCORD_USERNAME', 'Floorbit'), 'embeds': [embed],
                   'allowed_mentions': {'parse': []}}
        mention = config.get('DISCORD_MENTION', '') or ''
        if mention and finding.get('severity') == 'high':
            payload['content'] = mention
            payload['allowed_mentions'] = {'parse': ['roles', 'everyone', 'users']}
        return payload

    def build_source_message(self, kind, data, now=None):
        now = now or time.time()
        down = kind == 'monitoring.offline'
        source = data.get('source') or 'The monitoring source'
        embed = {
            'title': f"{'⚠️' if down else '✅'} {source} is {'unreachable' if down else 'back'}",
            'description': ('Switch status is frozen at the last good data and no switch alerts are sent '
                            'until it answers again.' if down else
                            f"Down for {_fmt_duration(data.get('down_for') or 0)}. Switch alerts are back on."),
            'color': COLOR_OFFLINE if down else COLOR_ONLINE,
            'timestamp': datetime.fromtimestamp(now, tz=UTC).isoformat(),
        }
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        if public_url:
            embed['url'] = public_url
        return {'username': config.get('DISCORD_USERNAME', 'Floorbit'), 'embeds': [embed],
                'allowed_mentions': {'parse': []}}

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
