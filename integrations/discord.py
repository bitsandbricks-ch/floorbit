"""Discord alerts through a channel webhook.

Listens for ``monitor.poll`` events and posts one message per poll that had
changes, so a whole row losing power is one message, not twenty. ``health.changed`` (the
service health wall) posts when a service goes red and when it is back; ``security.finding``
and ``power.alert`` post new findings and circuits that turn red or trip. Sending runs
on its own thread so a slow Discord never delays the status monitor.
"""
import queue
import threading
import time
from datetime import UTC, datetime

import requests

from . import alerting, config, events

COLOR_OFFLINE = 0xF85149
COLOR_ONLINE = 0x3FB950
COLOR_INFO = 0xF0883E   # the app's orange accent
MAX_EMBEDS = 10         # Discord limit per message
SILENT = 4096           # Discord's SUPPRESS_NOTIFICATIONS flag: posted, but no push or sound
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


def _circuits_of_switches():
    """Switch id -> power circuit name, from the Electrics layer (empty when it isn't used)."""
    try:
        from floorbit import store
        circuits = (store.load_data().get('power') or {}).get('circuits') or []
    except Exception:  # noqa: BLE001  # grouping is a nicety; the alert goes out without it
        return {}
    return {sid: c.get('name') for c in circuits if isinstance(c, dict) for sid in c.get('switches') or []}


def _grouped(changes):
    """One line per power circuit (what a row losing power looks like), then the rest."""
    by_circuit = _circuits_of_switches()
    groups = {}
    for c in changes:
        groups.setdefault(by_circuit.get(c['id']), []).append(str(c.get('name'))[:60])
    lines = [f"**Circuit {name}**: {', '.join(sorted(names))}" for name, names in sorted(
        ((k, v) for k, v in groups.items() if k), key=lambda kv: -len(kv[1]))]
    if None in groups:
        rest = sorted(groups[None])
        lines.append(('Other: ' if lines else '') + ', '.join(rest))
    return '\n'.join(lines)


class DiscordNotifier:
    def __init__(self, crew=None):
        self.crew = crew          # CrewBridge: with no webhook, alerts go to the crew channel
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

    def _via_crew(self):
        return not self.webhook() and self.crew is not None and self.crew.enabled()

    def enabled(self):
        return (bool(self.webhook()) or self._via_crew()) and config.get_bool('DISCORD_ALERTS_ENABLED', True)

    # ── wiring ────────────────────────────────────────────────────────────────────────────
    def attach(self):
        events.subscribe('monitor.poll', self.on_poll)
        events.subscribe('monitoring.offline', self.on_source)
        events.subscribe('monitoring.online', self.on_source)
        events.subscribe('health.changed', self.on_health)
        events.subscribe('security.finding', self.on_security)
        events.subscribe('power.alert', self.on_power)

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

    def post(self, payload):
        """Queue a message. In quiet hours it goes out silently, without the mention."""
        if alerting.quiet_now():
            mention = config.get('DISCORD_MENTION', '') or ''
            content = (payload.get('content') or '').replace(mention, '').strip() if mention else payload.get('content')
            payload = {**payload, 'allowed_mentions': {'parse': []}, 'flags': SILENT}
            payload.pop('content', None)
            if content:
                payload['content'] = content
        self._ensure_worker()
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self.last_error = 'alert queue full, message dropped'

    # ── message building ─────────────────────────────────────────────────────────────
    def on_poll(self, event):
        if not self.enabled():
            return
        payload = self.build_status_message(event['data'].get('changes', []))
        if payload:
            self.post(payload)

    def on_source(self, event):
        """The monitoring source itself went away or came back: one message, not one per switch."""
        if not self.enabled():
            return
        self.post(self.build_source_message(event['type'], event.get('data') or {}))

    def on_health(self, event):
        if not self.enabled() or not config.get_bool('DISCORD_HEALTH_ALERTS', True):
            return
        payload = self.build_health_message((event.get('data') or {}).get('changes', []))
        if payload:
            self.post(payload)

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
            self.post(payload)

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

    def on_power(self, event):
        if not self.enabled() or not config.get_bool('DISCORD_POWER_ALERTS', True):
            return
        payload = self.build_power_message(event.get('data') or {})
        if payload:
            self.post(payload)

    def build_power_message(self, alert, now=None):
        """A circuit turned red or its breaker tripped: which one, and what goes dark."""
        if alert.get('state') not in ('crit', 'tripped'):
            return None
        now = now or time.time()
        key = f"power:{alert.get('id')}:{alert.get('state')}"
        last = self._last_alert.get(key)
        if last is not None and now - last < config.get_int('DISCORD_COOLDOWN', 300, minimum=0):
            return None
        self._last_alert[key] = now
        tripped = alert['state'] == 'tripped'
        name = str(alert.get('name') or 'A circuit')[:80]
        title = f'⚡ Breaker tripped: {name}' if tripped else f"⚡ {name} at {alert.get('pct')} %"
        fields = [{'name': 'Board', 'value': str(alert.get('board') or '?')[:40], 'inline': True},
                  {'name': 'Phase', 'value': str(alert.get('phase') or '?')[:4], 'inline': True}]
        if alert.get('rating_a'):
            fields.append({'name': 'Fuse', 'value': f"{alert['rating_a']:g} A", 'inline': True})
        feeds = []
        if alert.get('seats'):
            feeds.append(f"{alert['seats']} seats")
        if alert.get('switches'):
            feeds.append(', '.join(str(s) for s in alert['switches'][:6])[:200])
        if feeds:
            fields.append({'name': 'Feeds', 'value': ' and '.join(feeds)[:250], 'inline': False})
        embed = {'title': title[:200], 'color': COLOR_OFFLINE if tripped else COLOR_INFO, 'fields': fields,
                 'timestamp': datetime.fromtimestamp(now, tz=UTC).isoformat()}
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        if public_url:
            embed['url'] = public_url + '/power'
        payload = {'username': config.get('DISCORD_USERNAME', 'Floorbit'), 'embeds': [embed],
                   'allowed_mentions': {'parse': []}}
        mention = config.get('DISCORD_MENTION', '') or ''
        if mention and tripped:
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
        """Switches that went offline or came back in one poll. Muted switches are left out; past
        ``ALERT_GROUP_AFTER`` changes they become one message grouped by power circuit, so a row
        losing power is one alert, not fifty."""
        now = now or time.time()
        cooldown = config.get_int('DISCORD_COOLDOWN', 300, minimum=0)
        notify_recovery = config.get_bool('DISCORD_NOTIFY_RECOVERY', True)
        muted = alerting.mutes(now) if changes else {}

        selected = []
        for c in changes:
            if c['status'] == 'unknown' or c['id'] in muted:
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
        back = [c for c in selected if c['status'] != 'offline']
        public_url = (config.get('PUBLIC_URL', '') or '').rstrip('/')
        ts = datetime.fromtimestamp(now, tz=UTC).isoformat()
        group_after = config.get_int('ALERT_GROUP_AFTER', 3, minimum=1)

        embeds = []
        if len(selected) > min(group_after, MAX_EMBEDS):
            for items, down in ((offline, True), (back, False)):
                if not items:
                    continue
                embed = {'title': (f"{'🔴' if down else '🟢'} {len(items)} switch{'es' if len(items) != 1 else ''} "
                                   f"{'offline' if down else 'back online'}"),
                         'description': _grouped(items)[:4000],
                         'color': COLOR_OFFLINE if down else COLOR_ONLINE, 'timestamp': ts}
                if public_url:
                    embed['url'] = public_url + '/problems'
                embeds.append(embed)
        else:
            for c in selected:
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
        if not url and self._via_crew():
            self.crew.post_alert(payload)
            self.last_sent, self.last_error = time.time(), None
            return True
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
            'configured': bool(self.webhook()) or self._via_crew(),
            'via': 'webhook' if self.webhook() else ('crew channel' if self._via_crew() else None),
            'last_sent': self.last_sent,
            'last_error': self.last_error,
        }
