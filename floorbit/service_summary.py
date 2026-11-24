"""One count of the event's services (issue #1037), so the Services page, the service health
panes and the dashboards say the same numbers.

The rows are the service health wall's checks (floorbit/health.py: DHCP, DNS, the LAN cache, game
servers, internet lines, firewalls and what plugins add), with one change: the wall shows the
internet sites as one tile, the Services page as one row each, so here each site is a row too.

    {"rows": [{"id", "name", "kind", "status", "summary", "link"}], "total": 30,
     "counts": {"up": 26, "warn": 2, "down": 2, "unknown": 0},
     "by_kind": {"firewall": {"up": 9, "warn": 0, "down": 1, "unknown": 0, "total": 10}, ...}}
"""
from .health import STATES

FIELDS = ('id', 'name', 'kind', 'status', 'summary', 'link')


def _count(rows):
    return {s: sum(r['status'] == s for r in rows) for s in STATES}


def summary(checks, sites=None):
    """``checks``: the wall's checks; ``sites``: the Services page's sites with their status, or
    None to keep the wall's one sites tile."""
    rows = []
    for check in checks or []:
        if check.get('kind') == 'web' and sites is not None and check.get('id') == 'sites':
            rows += [{'id': f"site:{s['id']}", 'name': s.get('name') or '', 'kind': 'web',
                      'status': s.get('status') if s.get('status') in STATES else 'unknown',
                      'summary': s.get('error') or '', 'link': '/services'} for s in sites]
            continue
        row = {k: check.get(k) for k in FIELDS}
        row['status'] = row['status'] if row['status'] in STATES else 'unknown'
        rows.append(row)
    kinds = {}
    for row in rows:
        kinds.setdefault(row['kind'], []).append(row)
    return {'rows': rows, 'total': len(rows), 'counts': _count(rows),
            'by_kind': {k: {**_count(v), 'total': len(v)} for k, v in kinds.items()}}
