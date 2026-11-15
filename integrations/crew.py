"""The crew's Discord channel (issue #32): incidents as messages with a thread each.

Needs a Discord bot (``DISCORD_BOT_TOKEN``) in the crew's channel (``DISCORD_CREW_CHANNEL``). A
webhook can't open threads in a text channel or edit buttons, so this uses the bot's REST API.
It needs no gateway connection.

- A new incident is posted as one message, with a thread under it.
- When the incident changes, the message is edited to match. The thread gets a line for each
  change (taken, back on the board, fixed, reopened) and each new note. A fixed incident's
  thread is archived. It opens again when the incident is reopened.
- The message has "Take it" and "Fixed" buttons once ``DISCORD_APP_PUBLIC_KEY`` is set and
  the app's Interactions Endpoint URL points at ``/api/discord/interactions``. A click counts
  as the Floorbit account that has that Discord user linked (Discord sign-in, #9). Discord
  users with no linked account are told how to link one, and nothing changes.
- With no webhook set, the switch, health, security and power alerts go to this channel too. A
  switch-offline or service-down alert then has a "Mute … for 1 h" button for crew with
  ``incidents.work`` (issues #272, #274); a webhook can't carry buttons.
- An incident nobody has taken for ``DISCORD_CREW_WAITING_MINUTES`` gets one line in its
  thread saying so, with a ping for ``DISCORD_CREW_WAITING_ROLE`` when that is set (issue #298).
- A job sent to a tech who hasn't said "On my way" after ``DISCORD_CREW_UNSEEN_MINUTES`` gets one
  line in its thread too, so a lead can send it to someone else (issue #366).

Talking to Discord runs on its own thread, so a slow Discord never holds up a request. Which
Discord message and thread belong to which incident is kept in its own small file next to
data.json (``crew-discord.json``). Background writes to data.json could race the app's own.
Nothing personal goes out: no IPs, MACs or nicks. An attendee's seat report shows only its seat.
"""
import hashlib
import json
import os
import queue
import threading
import time
from datetime import UTC, datetime

import requests

from . import config, events

API = 'https://discord.com/api/v10'
TIMEOUT = 10
USER_AGENT = 'DiscordBot (https://github.com/bitsandbricks-ch/floorbit, 1)'   # the form Discord asks bots for
COLOR = {'open': 0xF85149, 'assigned': 0xF0883E, 'fixed': 0x3FB950}
STATUS_TEXT = {'open': 'Open', 'assigned': 'Taken', 'fixed': 'Fixed'}
MAX_LINE = 1800           # under Discord's 2000-character message limit
MAX_TRACKED = 3000        # oldest incidents are forgotten beyond this
ARCHIVE_AFTER = 1440      # minutes; Discord archives a quiet thread after this anyway
ACTION_PREFIX = 'fb'      # custom_id: fb:<action>:<incident id>, or fb:mute:<switch id>
ACTIONS = ('take', 'fixed', 'mute')
MUTE_MINUTES = 60         # what "Mute 1 h" under a switch alert means (issue #272)
CHECK_EVERY = 60          # seconds between looks for incidents nobody has taken (issue #298)


class CrewError(RuntimeError):
    pass


def bot_token():
    return str(config.get('DISCORD_BOT_TOKEN', '') or '').strip()


def channel_id():
    return str(config.get('DISCORD_CREW_CHANNEL', '') or '').strip()


def public_key():
    return str(config.get('DISCORD_APP_PUBLIC_KEY', '') or '').strip()


def _public_url():
    return (config.get('PUBLIC_URL', '') or '').rstrip('/')


def _state_file():
    configured = config.get('DISCORD_CREW_FILE', '') or ''
    if configured:
        return configured
    from floorbit import store
    return os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), 'crew-discord.json')


def custom_id(action, incident_id):
    return f'{ACTION_PREFIX}:{action}:{incident_id}'


def parse_custom_id(value):
    """(action, incident id), or None for a button this app didn't make."""
    parts = str(value or '').split(':', 2)
    if len(parts) != 3 or parts[0] != ACTION_PREFIX or parts[1] not in ACTIONS:
        return None
    # Incident ids are plain; switch ids may be uuids or NetBox names with dashes and dots, and a
    # service's mute key is health:<plugin>:<check> (issue #274).
    allowed = parts[2]
    if parts[1] == 'mute':
        for ch in '-_.:':
            allowed = allowed.replace(ch, '')
    if not allowed.isalnum():
        return None
    return parts[1], parts[2]


def where(incident):
    if incident.get('seat'):
        return f"Seat {incident['seat']}"
    if incident.get('circuit_id'):
        return f"Circuit {incident.get('circuit_name') or incident['circuit_id']}"
    return f"Switch {incident.get('switch_name') or incident.get('switch_id')}"


def digest(body):
    return hashlib.sha1(json.dumps(body, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[:16]


def _name(username, users=None):
    if not username:
        return None
    found = users.get(username) if users else None
    return (found or {}).get('display_name') or username


def _waited(seconds):
    minutes = int(seconds // 60)
    return f'{minutes} min' if minutes < 60 else f'{minutes // 60} h {minutes % 60} min'


class CrewBridge:
    def __init__(self, users=None, app=None):
        self.users = users          # auth's UserStore, for display names
        self.app = app
        self.request = requests.request   # tests swap in a fake
        self._queue = queue.Queue(maxsize=500)
        self._thread = None
        self._ticker = None
        self._lock = threading.Lock()
        self._file_lock = threading.Lock()
        self.last_sent = None
        self.last_error = None

    # config -------------------------------------------------------------------------------
    def enabled(self):
        return bool(bot_token() and channel_id()) and config.get_bool('DISCORD_CREW_ENABLED', True)

    def buttons(self):
        return bool(public_key())

    def info(self):
        return {'enabled': self.enabled(), 'configured': bool(bot_token() and channel_id()),
                'buttons': self.buttons(), 'tracked': len(self._read()),
                'last_sent': self.last_sent, 'last_error': self.last_error,
                'interactions_url': (_public_url() + '/api/discord/interactions') if _public_url() else None}

    # wiring -------------------------------------------------------------------------------
    def attach(self):
        events.subscribe('incident.changed', self.on_incident)
        events.subscribe('notice.changed', self.on_notice)

    def on_incident(self, event):
        if not self.enabled() or not config.get_bool('DISCORD_CREW_INCIDENTS', True):
            return
        incident_id = (event.get('data') or {}).get('id')
        if not incident_id:
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait(incident_id)
        except queue.Full:
            self.last_error = 'crew channel queue full, an update was dropped'

    def on_notice(self, event):
        """A lead put up a crew notice (issue #248). Taking one down posts nothing."""
        notice = (event.get('data') or {}).get('notice')
        if not notice or not self.enabled() or not config.get_bool('DISCORD_CREW_NOTICES', True):
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait(('notice', notice))
        except queue.Full:
            self.last_error = 'crew channel queue full, a notice was dropped'

    @staticmethod
    def notice_message(notice):
        # Durations, not clock times: the server's time zone may not be the hall's.
        hours = round((notice['until'] - notice['at']) / 3600) if notice.get('until') else 0
        head = '⚠️ **Crew notice**' if notice.get('level') == 'warn' else '📣 **Crew notice**'
        meta = [f"from {notice['by']}" if notice.get('by') else '',
                f"for {hours} hour{'s' if hours != 1 else ''}" if hours else 'until taken down']
        quoted = '\n'.join('> ' + line for line in notice['text'].splitlines() or [''])
        return f"{head} ({', '.join(m for m in meta if m)})\n{quoted}"

    def post_notice(self, notice):
        return self._call('POST', f'/channels/{channel_id()}/messages',
                          {'content': self.notice_message(notice), 'allowed_mentions': {'parse': []}})

    def _ensure_worker(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._worker, name='discord-crew', daemon=True)
            self._thread.start()

    def start(self):
        """Look for incidents nobody has taken once a minute, on a thread of its own (issue #298)."""
        with self._lock:
            if self._ticker and self._ticker.is_alive():
                return
            self._ticker = threading.Thread(target=self._tick, name='discord-crew-waiting', daemon=True)
            self._ticker.start()

    def _tick(self):
        while True:
            time.sleep(CHECK_EVERY)
            try:
                if self.app is not None:
                    with self.app.app_context():
                        self.nudge_waiting()
                        self.nudge_unseen()
                else:
                    self.nudge_waiting()
                    self.nudge_unseen()
            except Exception as exc:  # noqa: BLE001  # keep checking after a failed send
                self.last_error = str(exc)[:300]

    def _handle(self, item):
        # Incidents are queued by id; a crew notice as ('notice', notice).
        if isinstance(item, tuple):
            return self.post_notice(item[1])
        return self.sync(item)

    def _worker(self):
        while True:
            item = self._queue.get()
            try:
                if self.app is not None:
                    with self.app.app_context():
                        self._handle(item)
                else:
                    self._handle(item)
            except Exception as exc:  # noqa: BLE001  # keep the sender thread alive
                self.last_error = str(exc)[:300]
                print(f'[integrations] crew channel update failed: {exc}')

    # state file ---------------------------------------------------------------------------
    def _read(self):
        from floorbit.store import read_json
        try:
            found = read_json(_state_file(), {})
        except ValueError:
            found = {}
        return found if isinstance(found, dict) else {}

    def _write(self, state):
        from floorbit.store import write_json
        if len(state) > MAX_TRACKED:
            keep = sorted(state, key=lambda k: state[k].get('at', 0))[-MAX_TRACKED:]
            state = {k: state[k] for k in keep}
        write_json(_state_file(), state)

    def tracked(self, incident_id):
        return self._read().get(incident_id)

    # building -----------------------------------------------------------------------------
    def message(self, incident):
        """The incident's message in the channel: an embed, and buttons while it is not fixed."""
        from auth import teams
        status = incident.get('status', 'open')
        fields = [{'name': 'Where', 'value': where(incident)[:100], 'inline': True},
                  {'name': 'Status', 'value': STATUS_TEXT.get(status, status), 'inline': True}]
        team = (teams.all_teams().get(incident.get('team') or '') or {}).get('name')
        if team:
            fields.append({'name': 'Team', 'value': str(team)[:40], 'inline': True})
        if incident.get('assignee') and status != 'open':
            fields.append({'name': 'With', 'value': str(_name(incident['assignee'], self.users))[:60],
                           'inline': True})
        zone = self._match_zone(incident)
        if zone:
            fields.append({'name': 'Match seat', 'value': str(zone)[:60], 'inline': True})
        if int(incident.get('reports') or 1) > 1:
            fields.append({'name': 'Reports', 'value': str(incident['reports']), 'inline': True})
        embed = {'title': f"{'✅' if status == 'fixed' else '🔧'} {incident.get('title') or 'Incident'}"[:250],
                 'color': COLOR.get(status, COLOR['open']), 'fields': fields,
                 'timestamp': datetime.fromtimestamp(incident.get('created_at') or time.time(), tz=UTC).isoformat()}
        if incident.get('source') == 'helpdesk':
            embed['footer'] = {'text': "Reported from the seat's QR code"}
        if _public_url():
            embed['url'] = _public_url() + '/incidents'
        row = []
        if status != 'fixed' and self.buttons():
            if status == 'open':
                row.append({'type': 2, 'style': 1, 'label': 'Take it', 'custom_id': custom_id('take', incident['id'])})
            row.append({'type': 2, 'style': 3, 'label': 'Fixed', 'custom_id': custom_id('fixed', incident['id'])})
        if _public_url():
            row.append({'type': 2, 'style': 5, 'label': 'Open in Floorbit', 'url': _public_url() + '/incidents'})
        return {'embeds': [embed], 'components': [{'type': 1, 'components': row}] if row else [],
                'allowed_mentions': {'parse': []}}

    @staticmethod
    def _match_zone(incident):
        if not incident.get('seat'):
            return None
        try:
            from floorbit import tournament
            return tournament.zone_of(incident['seat'])
        except Exception:  # noqa: BLE001  # the zone is a nicety; the message goes out without it
            return None

    def changes(self, before, incident):
        """Thread lines for what happened since the last sync."""
        lines = []
        status, assignee = incident.get('status'), incident.get('assignee')
        if before.get('status') != status or before.get('assignee') != assignee:
            who = _name(assignee, self.users)
            if status == 'fixed':
                lines.append('✅ Fixed' + (f' ({who})' if who else '') + '.')
            elif before.get('status') == 'fixed':
                lines.append('🔁 Reopened.' + (f' {who} has it.' if who else ''))
            elif status == 'assigned' and who:
                sent = incident.get('dispatched_at') and not incident.get('taken_at')
                lines.append(f'📟 Sent to {who}.' if sent else f'🙋 {who} has it.')
            elif status == 'open':
                lines.append('↩️ Back on the board. Nobody has it.')
        ok = incident.get('seat_ok_at')
        if ok and ok != before.get('seat_ok') and incident.get('status') != 'fixed':
            # Issue #374: the attendee says it fixed itself. Tell the thread so nobody walks over for nothing.
            lines.append('👍 The seat says it works again. Check or ask before marking it fixed.')
        for note in (incident.get('notes') or [])[int(before.get('notes') or 0):]:
            by = _name(note.get('by'), self.users) or 'Seat report'
            lines.append(f"💬 **{by}**: {note.get('text') or ''}"[:MAX_LINE])
        return lines

    # syncing ------------------------------------------------------------------------------
    def sync(self, incident_id):
        """Bring the channel in line with the incident. Safe to call again: it only sends what changed."""
        from floorbit import incidents
        incident = incidents.get(incident_id)
        if not incident or not self.enabled():
            return None
        with self._file_lock:
            state = self._read()
            before = state.get(incident_id)
            body = self.message(incident)
            if before is None:
                if incident.get('status') == 'fixed':
                    return None   # fixed before the bridge saw it: nothing for the crew to do
                record = self._post_new(incident, body)
            else:
                record = self._update(incident, before, body)
            state[incident_id] = record
            self._write(state)
            return record

    def _post_new(self, incident, body):
        ch = channel_id()
        msg = self._call('POST', f'/channels/{ch}/messages', body)
        record = {'message': msg['id'], 'thread': None, 'status': incident['status'],
                  'assignee': incident.get('assignee'), 'notes': 0, 'at': time.time(), 'shown': digest(body),
                  'seat_ok': incident.get('seat_ok_at')}
        try:
            thread = self._call('POST', f"/channels/{ch}/messages/{msg['id']}/threads",
                                {'name': f"{where(incident)}: {incident.get('title') or 'Incident'}"[:100],
                                 'auto_archive_duration': ARCHIVE_AFTER})
            record['thread'] = thread['id']
        except CrewError as exc:
            # The message stays useful without a thread (the bot may lack "Create Public Threads").
            self.last_error = str(exc)
            return record
        lines = self.changes({'status': 'open', 'assignee': None, 'notes': 0}, incident)
        if incident.get('status') == 'open':
            lines = [line for line in lines if not line.startswith('↩️')]
        self._thread_lines(record['thread'], lines)
        record['notes'] = len(incident.get('notes') or [])
        return record

    def _update(self, incident, before, body):
        ch = channel_id()
        record = {**before, 'status': incident['status'], 'assignee': incident.get('assignee'),
                  'notes': len(incident.get('notes') or []), 'at': time.time(), 'shown': digest(body),
                  'seat_ok': incident.get('seat_ok_at')}
        lines = self.changes(before, incident)
        if not lines and before.get('shown') == record['shown']:
            return {**record, 'at': before.get('at', record['at'])}
        try:
            self._call('PATCH', f"/channels/{ch}/messages/{before['message']}", body)
        except CrewError as exc:
            if '404' not in str(exc):
                raise
            # The message was deleted in Discord: post it again rather than lose the incident.
            return self._post_new(incident, body)
        thread = before.get('thread')
        if thread:
            if before.get('status') == 'fixed' and incident['status'] != 'fixed':
                self._call('PATCH', f'/channels/{thread}', {'archived': False})
            self._thread_lines(thread, lines)
            if incident['status'] == 'fixed' and before.get('status') != 'fixed':
                self._call('PATCH', f'/channels/{thread}', {'archived': True})
        return record

    def nudge_waiting(self, now=None):
        """Say once in each thread whose incident nobody has taken for a while (issue #298).

        Same rule as the board's "Waiting" badge: open, nobody on it, opened that long ago. Only
        once per incident, so a reopened one doesn't ping again."""
        minutes = config.get_int('DISCORD_CREW_WAITING_MINUTES', 10, minimum=0)
        if not minutes or not self.enabled():
            return []
        from floorbit import incidents
        now = now or time.time()
        role = ''.join(ch for ch in config.get('DISCORD_CREW_WAITING_ROLE', '') if ch.isdigit())
        nudged = []
        with self._file_lock:
            state = self._read()
            for incident in incidents.list_all():
                record = state.get(incident['id'])
                if not record or not record.get('thread') or record.get('nudged'):
                    continue
                waited = now - (incident.get('created_at') or now)
                if incident.get('status') != 'open' or incident.get('assignee') or waited < minutes * 60:
                    continue
                if incident.get('seat_ok_at'):
                    continue   # the seat says it works again: no reason to ping the crew about it
                text = f'⏳ Waiting {_waited(waited)}. Nobody has taken it yet.'
                self._call('POST', f"/channels/{record['thread']}/messages",
                           {'content': f'<@&{role}> {text}' if role else text,
                            'allowed_mentions': {'parse': [], 'roles': [role] if role else []}})
                record['nudged'] = True
                nudged.append(incident['id'])
            if nudged:
                self._write(state)
        return nudged

    def nudge_unseen(self, now=None):
        """Say once in a thread when the tech a job was sent to hasn't seen it for a while (issue #366).

        Same rule as the board's "not seen for" line. Once per sending: sent again, it can say so again.
        No ping: the tech's phone is the problem, and the lead reads the thread."""
        minutes = config.get_int('DISCORD_CREW_UNSEEN_MINUTES', 5, minimum=0)
        if not minutes or not self.enabled():
            return []
        from floorbit import incidents
        now = now or time.time()
        nudged = []
        with self._file_lock:
            state = self._read()
            for incident in incidents.list_all():
                record = state.get(incident['id'])
                sent = incident.get('dispatched_at')
                if not record or not record.get('thread') or not sent or record.get('unseen_for') == sent:
                    continue
                if incident.get('status') == 'fixed' or not incident.get('assignee') or incident.get('taken_at') \
                        or now - sent < minutes * 60:
                    continue
                text = f"📵 Sent to {incident['assignee']} {_waited(now - sent)} ago, not seen yet."
                self._call('POST', f"/channels/{record['thread']}/messages",
                           {'content': text, 'allowed_mentions': {'parse': []}})
                record['unseen_for'] = sent
                nudged.append(incident['id'])
            if nudged:
                self._write(state)
        return nudged

    def _thread_lines(self, thread, lines):
        if not thread or not lines:
            return
        text = ''
        for line in lines:   # as few messages as fit, in order
            if text and len(text) + len(line) + 1 > MAX_LINE:
                self._call('POST', f'/channels/{thread}/messages', {'content': text, 'allowed_mentions': {'parse': []}})
                text = ''
            text = f'{text}\n{line}' if text else line
        if text:
            self._call('POST', f'/channels/{thread}/messages', {'content': text, 'allowed_mentions': {'parse': []}})

    # alerts -------------------------------------------------------------------------------
    def post_alert(self, payload):
        """An alert from DiscordNotifier, when there is no webhook. Bots can't set a display name."""
        body = {k: v for k, v in payload.items() if k not in ('username', 'avatar_url') and not k.startswith('_')}
        if payload.get('_mute') and self.buttons():
            row = [{'type': 2, 'style': 2, 'label': f'Mute {str(name)[:60]} for 1 h',
                    'custom_id': custom_id('mute', sid)} for sid, name in payload['_mute']
                   if len(custom_id('mute', sid)) <= 100]   # Discord's custom_id limit
            if row:
                body['components'] = [{'type': 1, 'components': row}]
        return self._call('POST', f'/channels/{channel_id()}/messages', body)

    # HTTP ---------------------------------------------------------------------------------
    def _call(self, method, path, body=None, retries=2):
        token = bot_token()
        if not token:
            raise CrewError('DISCORD_BOT_TOKEN is not set')
        for attempt in range(retries + 1):
            try:
                resp = self.request(method, API + path, json=body, timeout=TIMEOUT,
                                    headers={'Authorization': f'Bot {token}', 'User-Agent': USER_AGENT})
            except requests.RequestException as exc:
                raise CrewError(f'Discord could not be reached: {exc.__class__.__name__}') from None
            if resp.status_code == 429 and attempt < retries:
                try:
                    wait = float(resp.json().get('retry_after', 1))
                except ValueError:
                    wait = 1.0
                time.sleep(min(wait, 30))
                continue
            if resp.status_code >= 400:
                where_to = path.split('/')[1]
                self.last_error = f'Discord answered {resp.status_code} to {method} {where_to}: {resp.text[:200]}'
                raise CrewError(self.last_error)
            self.last_sent = time.time()
            self.last_error = None
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        raise CrewError('Discord kept asking to slow down')
