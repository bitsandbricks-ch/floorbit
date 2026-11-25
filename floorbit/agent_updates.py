"""Updates of the agents themselves (bitsandbricks-ch/floorbit-agent #98, docs/agent.md, "Updates").

Each agent release carries a signed update: ``floorbit-agent-<version>.tar.gz`` and
``floorbit-agent-bundle.json`` (version, file, sha256, size, image, protocol). This Floorbit fetches
the newest one from the agent's GitHub releases every hour, keeps it in its state folder and offers
it to its agents in their plugin config (``agent_update``). It holds no key: the agent checks the
signature against the key in its image, and runs the update only on the image it was built for.

Which agents get the offer:

* agents that can take one (capability ``self_update``) and run an older version on the same image;
* in an HA group (agent_ha.groups), one at a time: the next only once the one before is back and
  through its probation, and the lease holder last, so the group keeps a primary throughout.

What the agents report about it (``agent_update``) is shown on their page, and each step goes to the
audit log.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

REPO = 'bitsandbricks-ch/floorbit-agent'
RELEASE_URL = f'https://github.com/{REPO}/releases/latest/download/floorbit-agent-bundle.json'
DOWNLOAD_URL = f'https://github.com/{REPO}/releases/download/v{{version}}/{{file}}'
CHECK_EVERY = 3600            # seconds between looks at the releases
MAX_META = 64 * 1024
MAX_BUNDLE = 32 * 1024 * 1024
BACK_WITHIN = 600             # seconds a group waits for an agent that went away during its update
VERSION_RE = re.compile(r'^[0-9][0-9A-Za-z.+-]{0,39}\Z')
FILE_RE = re.compile(r'^floorbit-agent-[0-9][0-9A-Za-z.+-]{0,39}\.tar\.gz\Z')
IMAGE_RE = re.compile(r'^[0-9a-f]{16}\Z')
SHA_RE = re.compile(r'^[0-9a-f]{64}\Z')
EVENTS = ('installed', 'kept', 'rolled back', 'refused', 'dropped')


def folder():
    from . import store
    return Path(store.state_folder()) / 'agent-releases'


def _clean_meta(doc):
    if not isinstance(doc, dict):
        return None
    meta = {'version': str(doc.get('version') or ''), 'file': str(doc.get('file') or ''),
            'sha256': str(doc.get('sha256') or ''), 'image': str(doc.get('image') or ''),
            'protocol': doc.get('protocol')}
    if (not VERSION_RE.match(meta['version']) or '..' in meta['version'] or not FILE_RE.match(meta['file'])
            or not SHA_RE.match(meta['sha256']) or not IMAGE_RE.match(meta['image'])
            or not isinstance(meta['protocol'], int) or isinstance(meta['protocol'], bool)):
        return None
    return meta


def latest():
    """The newest agent release this Floorbit has, with its file on disk, or None."""
    try:
        meta = _clean_meta(json.loads((folder() / 'release.json').read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return None
    if meta is None or not (folder() / meta['file']).is_file():
        return None
    return meta


def bundle_file(name):
    """The path of the release bundle the agents were offered, or None."""
    meta = latest()
    if meta is None or name != meta['file']:
        return None
    return folder() / meta['file']


def refresh(get=None):
    """Fetch the newest release's update when it is new here. Returns its version, or None."""
    from . import marketplace
    get = get or marketplace._get_capped
    meta = _clean_meta(json.loads(get(RELEASE_URL, MAX_META, 15)))
    if meta is None:
        raise ValueError('the release lists no agent update this Floorbit can read')
    have = latest()
    if have and have['version'] == meta['version'] and have['sha256'] == meta['sha256']:
        return None
    data = get(DOWNLOAD_URL.format(**meta), MAX_BUNDLE, 60)
    if hashlib.sha256(data).hexdigest() != meta['sha256']:
        raise ValueError('the update differs from what its release lists')
    out = folder()
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f'.{meta["file"]}.new'
    tmp.write_bytes(data)
    os.replace(tmp, out / meta['file'])
    tmp = out / '.release.json.new'
    tmp.write_text(json.dumps(meta, indent=1), encoding='utf-8')
    os.replace(tmp, out / 'release.json')
    for old in out.glob('floorbit-agent-*.tar.gz'):
        if old.name != meta['file']:
            old.unlink(missing_ok=True)
    log.info('agent update %s ready for the agents', meta['version'])
    return meta['version']


def _loop():
    while True:
        try:
            if refresh():
                from .agent_plugins import reload_agents
                reload_agents()
        except Exception as exc:  # noqa: BLE001  # GitHub away: the agents keep what they run
            log.warning('could not check for agent updates: %s', exc)
        time.sleep(CHECK_EVERY)


def init_app(app, start_background=True):
    started = threading.Event()

    @app.before_request
    def start_agent_updates_once():
        if start_background and not started.is_set():
            started.set()
            threading.Thread(target=_loop, daemon=True, name='agent-updates').start()


# what an agent says ---------------------------------------------------------------------------
def _ver(v):
    v = str(v or '')
    return v if VERSION_RE.match(v) else ''


def clean(raw):
    """The agent's ``agent_update`` report (floorbit_agent/self_update.py). Not trusted: known shapes only."""
    if not isinstance(raw, dict):
        return None
    pending = raw.get('pending') if isinstance(raw.get('pending'), dict) else None
    events = []
    for e in (raw.get('events') or [])[-10:] if isinstance(raw.get('events'), list) else ():
        if (isinstance(e, dict) and e.get('event') in EVENTS and isinstance(e.get('at'), (int, float))
                and not isinstance(e.get('at'), bool)):
            events.append({'at': e['at'], 'event': e['event'], 'version': _ver(e.get('version')),
                           'detail': str(e.get('detail') or '')[:300]})
    image_id = str(raw.get('image_id') or '')
    return {'policy': raw.get('policy') if raw.get('policy') in ('auto', 'approve', 'off') else 'auto',
            'running': _ver(raw.get('running')), 'image': _ver(raw.get('image')),
            'image_id': image_id if IMAGE_RE.match(image_id) else '',
            'booted': bool(raw.get('booted')), 'signed': bool(raw.get('keys')), 'trial': bool(raw.get('trial')),
            'pending': {'version': _ver(pending.get('version')), 'why': str(pending.get('why') or '')[:300]}
            if pending else None,
            'rolled_back': [_ver(v) for v in (raw.get('rolled_back') or [])[:10] if _ver(v)]
            if isinstance(raw.get('rolled_back'), list) else [],
            'events': events}


def note(agent_id, before, after, now=None):
    """Audit-log each step of an agent's update it reported for the first time."""
    from . import agent_link, audit
    events = ((after or {}).get('agent_update') or {}).get('events') or []
    if not events:
        return
    since = (before or {}).get('at') or ((time.time() if now is None else now) - 90)
    seen = {(e['at'], e['event'], e['version'])
            for e in ((before or {}).get('agent_update') or {}).get('events') or []}
    fresh = [e for e in events if (e['at'], e['event'], e['version']) not in seen and e['at'] >= since]
    if not fresh:
        return
    names = {a['id']: a['name'] for a in agent_link.load_data().get(agent_link.KEY) or []}
    who = names.get(agent_id, agent_id)
    for e in fresh:
        ver, why = e['version'], e['detail'][:160] or '-'
        if e['event'] == 'installed':
            audit.record('agents', f'{who}: installed agent update {ver}', user='agent', target=agent_id)
        elif e['event'] == 'kept':
            audit.record('agents', f'{who}: kept agent update {ver}', user='agent', target=agent_id)
        elif e['event'] == 'rolled back':
            audit.record('agents', f'{who}: rolled back agent update {ver} ({why})', user='agent',
                         target=agent_id, ok=False)
        else:
            audit.record('agents', f'{who}: refused agent update {ver} ({why})', user='agent',
                         target=agent_id, ok=False)


# who gets it ----------------------------------------------------------------------------------
def needs(agent, meta):
    """Why the agent can't take ``meta`` (a short key for the page), '' when it can, None when it
    already runs it or something newer."""
    from . import agent_link
    from .agent_ha import can
    from .plugins.bundles import newer
    report = agent.get('report') or {}
    mine = report.get('agent_update') or {}
    running = mine.get('running') or agent.get('version') or '0'
    if not newer(meta['version'], running):
        return None
    if not can(report, 'self_update'):
        return 'pull'                     # an agent from before #98: the pull command, as before
    if meta['protocol'] > agent_link.PROTOCOL:
        return 'floorbit'                 # this Floorbit is older than the agent release
    if mine.get('image_id') != meta['image']:
        return 'image'                    # built for another image: pull the new image
    return ''


def _busy(member, meta, now):
    """Is this member of the group in the middle of an update (gone for it, or on probation)?"""
    mine = ((member.get('report') or {}).get('agent_update') or {})
    if mine.get('trial'):
        return True
    if not member.get('connected'):
        last = member.get('last_seen') or 0
        return now - last < BACK_WITHIN
    return False


def offer_for(agent_id, agents=None, now=None, meta=None):
    """The ``agent_update`` for this agent's plugin config, or None."""
    from . import agent_link
    from .agent_ha import _group_of, lease_holder
    meta = latest() if meta is None else meta
    if meta is None:
        return None
    now = time.time() if now is None else now
    agents = agent_link.all_agents(now=now) if agents is None else agents
    me, members = _group_of(agent_id, agents)
    if me is None or needs(me, meta) != '':
        return None
    others = [m for m in members if m['id'] != agent_id]
    if any(_busy(m, meta, now) for m in others):
        return None
    if others:
        # One at a time, in a fixed order every pod agrees on; the primary last, so the lease moves
        # to an agent already updated while it restarts.
        primary = lease_holder(members)
        waiting = sorted((m['id'] for m in members if m.get('connected') and needs(m, meta) == ''),
                         key=lambda i: (i == primary, i))
        if not waiting or waiting[0] != agent_id:
            return None
    return {k: meta[k] for k in ('version', 'file', 'sha256', 'image')}


def status(agent, meta=None):
    """For the agent's page: ``{latest, state, why}``. state: current, updating, installing, approve,
    off, image, pull, floorbit, refused, rolled_back or none (no release known here)."""
    meta = latest() if meta is None else meta
    mine = ((agent.get('report') or {}).get('agent_update') or {})
    out = {'latest': meta['version'] if meta else None, 'state': 'none', 'why': ''}
    if mine.get('trial'):
        out['state'] = 'updating'
        return out
    if meta is None:
        return out
    need = needs(agent, meta)
    pending = mine.get('pending') or {}
    if need is None:
        out['state'] = 'current'
    elif need:
        out['state'] = need
    elif meta['version'] in (mine.get('rolled_back') or []):
        out['state'] = 'rolled_back'
    elif pending.get('version') == meta['version']:
        why = pending.get('why') or ''
        out['why'] = why
        out['state'] = ('approve' if 'approval' in why else 'off' if 'off here' in why
                        else 'refused' if why.startswith('refused') else 'installing')
    else:
        out['state'] = 'installing'
    return out
