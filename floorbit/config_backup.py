"""Switch config backups and diffs (issue #96). See docs/configs.md.

A tech backs up the running config of one or many switches (the switch commands machinery in
floorbit/commands.py), with a typed login or the stored one (floorbit/credentials.py). Every night
at ``CONFIG_BACKUP_HOUR`` Floorbit also backs up each switch a stored login covers, so nobody has to
remember. Floorbit keeps each copy and shows what changed since the event's baseline: the first
copy, or the one a lead marked.

Configs name SNMP communities, password hashes and keys, so before a copy is kept, the values on
lines like that are replaced with ``<removed>``. Copies are documents under ``configs/`` (the
database when there is one, else files next to ``data.json``), at most ``CONFIG_KEEP`` (50) per
switch, and only a copy that differs from the switch's last one is kept: an unchanged config just
updates when it was last checked.
"""
import difflib
import hashlib
import os
import re
import threading
import time
from datetime import datetime

from integrations import config

from . import commands, store

FOLDER = 'configs'
MAX_BYTES = 2 * 1024 * 1024        # per config
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
SHOW_RUN = {'juniper_junos': ['show configuration | display set'], '*': ['show running-config']}
# Lines whose value is a secret. Group 1 is what stays; the rest becomes <removed>.
SECRETS = (
    re.compile(r'^(\s*(?:enable\s+)?(?:secret|password)\s+(?:\d+\s+)?)\S.*$', re.I),
    re.compile(r'^(\s*username\s+\S+(?:\s+privilege\s+\d+)?\s+(?:secret|password)\s+(?:\d+\s+)?)\S.*$', re.I),
    re.compile(r'^(\s*snmp-server\s+community\s+)\S+(.*)$', re.I),
    re.compile(r'^(\s*snmp-server\s+(?:user|host)\s+.*?\b(?:auth|priv|md5|sha|aes|des|version\s+2c)\s+)\S.*$', re.I),
    re.compile(r'^(\s*(?:tacacs|radius)-server\s+.*?\bkey\s+(?:\d+\s+)?)\S.*$', re.I),
    re.compile(r'^(\s*(?:key|key-string|pre-shared-key|ip ospf (?:authentication|message-digest)-key.*?)'
               r'\s+(?:\d+\s+)?)\S.*$', re.I),
    re.compile(r'^(\s*crypto\s+(?:isakmp\s+)?key\s+)\S.*$', re.I),
    re.compile(r'^(.*\b(?:encrypted-password|authentication-key|secret|community|pre-shared-key)\s+)"?[^"\s]+"?(.*)$',
               re.I),
)
# Lines that change without anyone changing the config.
VOLATILE = re.compile(r'^(?:! (?:Last configuration change|NVRAM config last updated|Time:)|Current configuration :'
                      r'|Building configuration|ntp clock-period|## Last commit|show running-config|Running config)',
                      re.I)
_lock = threading.Lock()


def keep():
    return config.get_int('CONFIG_KEEP', 50, minimum=2)


NIGHTLY_USER = 'nightly backup'
NIGHTLY_HOUR = 4


def folder():
    return store.event_path(FOLDER)


def scrub(text):
    """The config without secrets and without the lines that change by themselves."""
    out = []
    for line in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if VOLATILE.match(line.strip()):
            continue
        for rx in SECRETS:
            m = rx.match(line)
            if m:
                line = m.group(1) + '<removed>' + (m.group(2) if rx.groups > 1 and m.group(2) else '')
                break
        out.append(line.rstrip())
    while out and not out[-1]:
        out.pop()
    return '\n'.join(out) + '\n'


def _index_path():
    return os.path.join(folder(), 'index.json')


def _index():
    found = store.read_json(_index_path(), {})
    return found if isinstance(found, dict) else {}


def _write(path, body):
    from . import database
    if database.backend().kind == 'files':
        os.makedirs(os.path.dirname(path), exist_ok=True)
    store.write_json(path, body)


def _write_index(index):
    _write(_index_path(), index)


def _nightly_path():
    return os.path.join(folder(), 'nightly.json')


def _file(switch, cid):
    return os.path.join(folder(), switch, f'{cid}.json')


def save(switch, text, by, now=None):
    """Keep a copy if it changed. Returns (entry, changed)."""
    if not NAME_RE.match(switch):
        raise ValueError('Bad switch name.')
    now = time.time() if now is None else now
    clean = scrub(text)[:MAX_BYTES]
    digest = hashlib.sha256(clean.encode('utf-8')).hexdigest()[:16]
    with _lock:
        index = _index()
        entry = index.setdefault(switch, {'copies': [], 'baseline': None, 'checked': None})
        entry['checked'] = {'at': now, 'by': by}
        last = entry['copies'][-1] if entry['copies'] else None
        if last and last['sha'] == digest:
            _write_index(index)
            return last, False
        cid = f"{int(now)}-{digest[:6]}"
        _write(_file(switch, cid), {'text': clean})
        copy = {'id': cid, 'at': now, 'by': by, 'sha': digest, 'lines': clean.count('\n')}
        entry['copies'].append(copy)
        # The first copy is the baseline until a lead picks another, and pruning never takes it.
        entry['baseline'] = entry.get('baseline') or cid
        while len(entry['copies']) > keep():
            gone = entry['copies'].pop(0 if entry['copies'][0]['id'] != entry['baseline'] else 1)
            store.delete_json(_file(switch, gone['id']))
        _write_index(index)
        return copy, True


def text(switch, cid):
    entry = _index().get(switch) or {}
    if not any(c['id'] == cid for c in entry.get('copies') or []):
        return None
    found = store.read_json(_file(switch, cid))
    return found.get('text') if isinstance(found, dict) else None


def baseline_of(entry):
    copies = entry.get('copies') or []
    return next((c for c in copies if c['id'] == entry.get('baseline')), copies[0] if copies else None)


def set_baseline(switch, cid):
    with _lock:
        index = _index()
        entry = index.get(switch)
        if not entry or not any(c['id'] == cid for c in entry['copies']):
            return False
        entry['baseline'] = cid
        _write_index(index)
    return True


def diff(switch, old_id=None, new_id=None):
    """Unified diff lines from the baseline (or old_id) to the latest (or new_id)."""
    entry = _index().get(switch) or {}
    copies = entry.get('copies') or []
    if not copies:
        return None
    old = next((c for c in copies if c['id'] == old_id), None) if old_id else baseline_of(entry)
    new = next((c for c in copies if c['id'] == new_id), None) if new_id else copies[-1]
    if not old or not new:
        return None
    a, b = text(switch, old['id']) or '', text(switch, new['id']) or ''
    lines = list(difflib.unified_diff(a.splitlines(), b.splitlines(), old['id'], new['id'], n=3, lineterm=''))
    added = sum(1 for ln in lines if ln.startswith('+') and not ln.startswith('+++'))
    removed = sum(1 for ln in lines if ln.startswith('-') and not ln.startswith('---'))
    return {'from': old, 'to': new, 'lines': lines, 'added': added, 'removed': removed}


def overview(switches):
    """One row per switch: its last copy and whether it changed since the baseline."""
    index = _index()
    rows = []
    for name in switches:
        entry = index.get(name) or {}
        copies = entry.get('copies') or []
        base = baseline_of(entry)
        rows.append({'switch': name, 'copies': len(copies), 'last': copies[-1] if copies else None,
                     'checked': entry.get('checked'), 'baseline': base,
                     'changed': bool(copies and base and copies[-1]['id'] != base['id'])})
    return rows


def history(switch):
    entry = _index().get(switch) or {}
    base = baseline_of(entry)
    return {'switch': switch, 'copies': list(reversed(entry.get('copies') or [])),
            'baseline': base['id'] if base else None, 'checked': entry.get('checked')}


def backup(registry, account, body):
    """Take the running config of ``body['switches']`` now. Returns one result per switch."""
    spec = commands.plugin(registry)
    if not spec:
        raise commands.CommandError('No plugin that can run switch commands is on. An admin turns on SSH port '
                                    'actions under Settings > Plugins.', 409)
    plat = commands.platform(registry, spec)
    results = commands.run_on(registry, spec, account, body, SHOW_RUN.get(plat) or SHOW_RUN['*'],
                              max_output=MAX_BYTES, feature='configs')
    out = []
    for r in results:
        row = {'switch': r['switch'], 'ok': r['ok'], 'error': r.get('error')}
        if r['ok'] and r['output'].strip():
            copy, changed = save(r['switch'], r['output'], account)
            row.update(copy=copy, changed=changed)
        elif r['ok']:
            row.update(ok=False, error='The switch printed nothing.')
        out.append(row)
    return out


# ── Every night ──────────────────────────────────────────────────────────────────────
def nightly_hour():
    """The hour (0-23, server time) of the nightly backup, or None when it's off."""
    raw = str(config.get('CONFIG_BACKUP_HOUR', NIGHTLY_HOUR)).strip().lower()
    if raw in ('off', 'no', 'false', 'none', '-1'):
        return None
    try:
        hour = int(raw)
    except ValueError:
        return NIGHTLY_HOUR
    return hour if 0 <= hour <= 23 else NIGHTLY_HOUR


def nightly_state(registry):
    """For the page: when it runs, which switches it covers, and how the last run went."""
    from . import credentials
    spec = commands.plugin(registry)
    switches = commands.info(registry, False)['switches'] if spec else []
    covered = [s for s in switches if credentials.covers(s)]
    last = store.read_json(_nightly_path())
    return {'hour': nightly_hour(), 'covered': len(covered), 'switches': len(switches),
            'last': last if isinstance(last, dict) else None}


def run_nightly(registry, now=None):
    """Back up every switch a stored login covers. Returns the run's summary, or None when there is
    nothing to do (off, no plugin, no stored login for any switch)."""
    from . import audit, credentials
    spec = commands.plugin(registry)
    if spec is None or not credentials.any_set():
        return None
    names = [s for s in commands.info(registry, False)['switches'] if credentials.covers(s)]
    if not names:
        return None
    now = time.time() if now is None else now
    done, changed, failed = 0, [], []
    plat = commands.platform(registry, spec)
    for i in range(0, len(names), commands.MAX_SWITCHES):
        batch = names[i:i + commands.MAX_SWITCHES]
        try:
            results = commands.run_on(registry, spec, NIGHTLY_USER, {'switches': batch},
                                      SHOW_RUN.get(plat) or SHOW_RUN['*'], max_output=MAX_BYTES, feature='configs')
        except commands.CommandError as exc:
            failed += [{'switch': n, 'error': str(exc)[:200]} for n in batch]
            continue
        for r in results:
            if r['ok'] and r['output'].strip():
                _copy, was_changed = save(r['switch'], r['output'], NIGHTLY_USER, now)
                done += 1
                if was_changed:
                    changed.append(r['switch'])
            else:
                failed.append({'switch': r['switch'], 'error': (r.get('error') or 'The switch printed nothing.')[:200]})
    summary = {'at': now, 'switches': len(names), 'ok': done, 'changed': changed[:50], 'failed': failed[:50]}
    _write(_nightly_path(), summary)
    what = f'Nightly config backup: {done} of {len(names)} switches'
    if changed:
        what += f', {len(changed)} changed'
    audit.record('configs', what, user=NIGHTLY_USER, target=f'{len(names)} switches', ok=not failed)
    return summary


def due(now, last_at, hour):
    """Is a nightly run due? Once a day, in the hour after ``hour``, and not twice that day."""
    if hour is None:
        return False
    here = datetime.fromtimestamp(now)
    if here.hour != hour:
        return False
    return not last_at or datetime.fromtimestamp(last_at).date() != here.date()


def _loop(app, stop):
    from . import cluster
    while not stop.wait(60):
        try:
            last = store.read_json(_nightly_path()) or {}
            # Only the leader runs it, so several pods back up once (floorbit/cluster.py).
            if cluster.leading() and due(time.time(), last.get('at'), nightly_hour()):
                with app.app_context():
                    run_nightly(app.extensions['floorbit_plugins'])
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad night
            print(f'[configs] nightly backup failed: {exc}')


def init_nightly(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='config-backup', daemon=True).start()
    return stop
