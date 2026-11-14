"""Switch config backups and diffs (issue #96). See docs/configs.md.

A tech backs up the running config of one or many switches with their own switch login (the
switch commands machinery in floorbit/commands.py), and Floorbit keeps each copy and shows what
changed since the event's baseline: the first copy, or the one a lead marked.

Configs name SNMP communities, password hashes and keys, so before a copy is kept, the values on
lines like that are replaced with ``<removed>``. Copies live in ``configs/`` next to
``data.json``, at most ``CONFIG_KEEP`` (50) per switch, and only a copy that differs from the
switch's last one is kept: an unchanged config just updates when it was last checked.
"""
import contextlib
import difflib
import hashlib
import json
import os
import re
import threading
import time

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


def folder():
    return os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), FOLDER)


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
    try:
        with open(_index_path(), encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _write_index(index):
    os.makedirs(folder(), exist_ok=True)
    tmp = _index_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(index, f, separators=(',', ':'))
    os.replace(tmp, _index_path())


def _file(switch, cid):
    return os.path.join(folder(), switch, f'{cid}.cfg')


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
        os.makedirs(os.path.dirname(_file(switch, cid)), exist_ok=True)
        with open(_file(switch, cid), 'w', encoding='utf-8') as f:
            f.write(clean)
        copy = {'id': cid, 'at': now, 'by': by, 'sha': digest, 'lines': clean.count('\n')}
        entry['copies'].append(copy)
        # The first copy is the baseline until a lead picks another, and pruning never takes it.
        entry['baseline'] = entry.get('baseline') or cid
        while len(entry['copies']) > keep():
            gone = entry['copies'].pop(0 if entry['copies'][0]['id'] != entry['baseline'] else 1)
            with contextlib.suppress(FileNotFoundError):
                os.remove(_file(switch, gone['id']))
        _write_index(index)
        return copy, True


def text(switch, cid):
    entry = _index().get(switch) or {}
    if not any(c['id'] == cid for c in entry.get('copies') or []):
        return None
    try:
        with open(_file(switch, cid), encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


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
                              max_output=MAX_BYTES)
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
