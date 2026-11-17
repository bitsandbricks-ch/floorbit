"""The LAN cache plugin's hosted part (docs/lancache.md): takes what the agent counted in the
hall, feeds the cache numbers Floorbit already shows (Games, stats wall, health wall) and the DNS
analytics, and answers the LAN cache page."""
import time

from flask import current_app, has_app_context

from floorbit import lancache
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

STALE_AFTER = 300     # seconds without word from the agent: the page says so


def _stats():
    stats = current_app.extensions.get('floorbit_lancache') if has_app_context() else None
    return stats or lancache._stats


def _dns():
    return current_app.extensions.get('floorbit_dns') if has_app_context() else None


class Plugin(Base):
    def agent_stats(self, agent, payload):
        if not isinstance(payload, dict):
            raise PluginError('stats must be an object')
        stats = _stats()
        if stats is None:
            raise PluginError('The LAN cache counter is not running.')
        stats.merge_agent(agent, payload)
        dns = _dns()
        hours = (payload.get('dns') or {}).get('hours')
        if dns is not None and hours:
            dns.merge_hours(hours)
        return {'ok': True}

    def agent_status(self, agent, payload):
        stats = _stats()
        if stats is None or not isinstance(payload, dict):
            return {'ok': False}
        stats.merge_status(agent, payload)
        return {'ok': True}

    def run_clear_cache(self, params):
        answers = self.ctx.agent_action('clear_cache', {})
        failed = [a for a in answers if a.get('error')]
        if failed and len(failed) == len(answers):
            raise PluginError(failed[0]['error'])
        return {'message': (answers[0].get('result') or {}).get('message') or 'Asked the agent.', 'answers': answers}

    def widget_hit_ratio(self):
        snap = _stats().snapshot(hours=1)
        ratio = snap.get('hit_ratio')
        return {'type': 'stat', 'value': '-' if ratio is None else round(ratio * 100), 'unit': '%',
                'tone': 'warn' if ratio is not None and ratio < 0.5 else '',
                'sub': 'From the cache this hour', 'link': '/lancache'}

    def widget_served(self):
        snap = _stats().snapshot(hours=24)
        points = [round((h['hit_bytes'] + h['miss_bytes']) / 1024 ** 3, 1) for h in snap.get('hours') or []]
        saved = round(snap.get('hit_bytes', 0) / 1024 ** 3, 1)
        return {'type': 'sparkline', 'points': points, 'value': points[-1] if points else 0, 'unit': 'GB',
                'min': 0, 'sub': f'{saved} GB from the cache in 24 hours', 'link': '/lancache'}

    def widget_machine(self):
        page = overview(_stats(), None, hours=1)
        items = []
        for a in page['agents']:
            beat, dns, disk = a.get('heartbeat') or {}, a.get('dns_check') or {}, a.get('disk') or {}
            items.append({'label': f"{a['name']}: cache", 'state': _state(beat, a['stale']),
                          'detail': beat.get('error') or (f"{beat.get('ms')} ms" if beat else 'not checked')})
            items.append({'label': f"{a['name']}: DNS", 'state': _state(dns, a['stale']),
                          'detail': dns.get('error') or ('points at the cache' if dns else 'not checked')})
            if disk.get('total'):
                used = round(disk['used'] * 100 / disk['total'])
                items.append({'label': f"{a['name']}: disk", 'state': 'warn' if used >= 90 else 'up',
                              'detail': f'{used} % full'})
        return {'type': 'status', 'items': items, 'link': '/lancache',
                'sub': '' if items else 'No agent has reported on the cache yet.'}

    def widget_downloads(self):
        page = overview(_stats(), None, hours=24)
        items = [{'label': d['item'], 'value': f"{d['clients']} players", 'tone': ''} for d in page['downloads'][:8]]
        return {'type': 'list', 'items': items, 'link': '/lancache',
                'sub': '' if items else 'Nothing downloaded by enough players yet.'}


def _state(check, stale):
    if not check:
        return 'unknown'
    if stale:
        return 'warn'
    return 'up' if check.get('ok') else 'down'


def overview(stats, health=None, hours=24, now=None):
    """Everything the LAN cache page shows. Hall-wide numbers only."""
    now = time.time() if now is None else now
    snap = stats.snapshot(hours=hours, now=now) if stats is not None else {'configured': False}
    agents = []
    downloads, suspects, services = {}, {}, {}
    other = {'hit_bytes': 0, 'miss_bytes': 0, 'requests': 0, 'items': 0}
    clients = {}
    for agent_id, r in sorted((stats.remote if stats is not None else {}).items()):
        status = r.get('status') or {}
        agents.append({'id': agent_id, 'name': r.get('name'), 'updated': r.get('updated'),
                       'stale': not r.get('updated') or now - r['updated'] > STALE_AFTER,
                       'disk': status.get('disk'), 'heartbeat': status.get('heartbeat'),
                       'dns_check': status.get('dns_check'), 'clearing': status.get('clearing'),
                       'health': ((health or {}).get(agent_id) or {}).get('health')})
        for d in r.get('downloads') or []:
            key = (d.get('cache'), d.get('item'))
            row = downloads.setdefault(key, {'cache': key[0], 'item': key[1], 'hit_bytes': 0, 'miss_bytes': 0,
                                             'requests': 0, 'clients': 0})
            for k in ('hit_bytes', 'miss_bytes', 'requests'):
                row[k] += d.get(k) or 0
            row['clients'] = max(row['clients'], d.get('clients') or 0)
        for k in other:
            other[k] += (r.get('other_downloads') or {}).get(k) or 0
        for s in r.get('suspects') or []:
            key = (s.get('cache'), s.get('item'))
            row = suspects.setdefault(key, {'cache': key[0], 'item': key[1], 'files': 0, 'misses': 0})
            row['files'] += s.get('files') or 0
            row['misses'] += s.get('misses') or 0
        for svc, n in (r.get('dns_services') or {}).items():
            services[svc] = services.get(svc, 0) + n
        for h, n in (r.get('clients') or {}).items():
            clients[h] = clients.get(h, 0) + n
    for d in downloads.values():
        total = d['hit_bytes'] + d['miss_bytes']
        d['hit_ratio'] = round(d['hit_bytes'] / total, 4) if total else None
    first = next(iter(stats.remote.values()), {}) if stats is not None and stats.remote else {}
    return {
        **snap,
        'agents': agents,
        'downloads': sorted(downloads.values(), key=lambda d: -(d['hit_bytes'] + d['miss_bytes']))[:50],
        'other_downloads': other,
        'suspects': sorted(suspects.values(), key=lambda s: -s['misses'])[:20],
        'dns_services': sorted(({'cache': k, 'lookups': v} for k, v in services.items()), key=lambda r: -r['lookups']),
        'clients': [{'t': int(h), 'clients': n} for h, n in sorted(clients.items(), key=lambda kv: int(kv[0]))],
        'min_clients': first.get('min_clients') or 5,
        'window_hours': first.get('window_hours') or 24,
        'saved_bytes': snap.get('hit_bytes', 0),
    }
