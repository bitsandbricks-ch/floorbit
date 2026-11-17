"""Traffic insights from NetFlow and IPFIX (issue #25). See docs/flows.md.

- ``GET /traffic``: the page.
- ``GET /api/flows``: the collector's latest summary. Hall, area and service numbers for everyone
  who may see the floor plan; per-seat volumes and which seat an anomaly is at only for
  ``seats.view``, like security findings.
"""
import time

from flask import Blueprint, current_app, jsonify, request

from .. import i18n, spa
from ..flows import classify, store

bp = Blueprint('flows', __name__)

ANOMALY_KINDS = {'p2p': 'P2P or torrent traffic', 'burst': 'Packet burst', 'rogue-dhcp': 'DHCP server at a seat',
                 'rogue-dns': 'DNS server at a seat'}


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


def current():
    """The summary to show: the collector's, or the demo hall's. None when nothing sends flows."""
    demo = current_app.extensions.get('floorbit_demo_flows')
    if demo is not None:
        return demo.snapshot()
    return store.latest()


def public(snap, may_see_people):
    if may_see_people:
        return snap
    out = {k: v for k, v in snap.items() if k != 'seats'}
    out['seats'] = None
    out['anomalies'] = [{'id': a['id'].split(':')[0] + ':' + str(i), 'kind': a['kind'], 'seat': None,
                         'area': a.get('area'), 'title': ANOMALY_KINDS.get(a['kind'], 'Anomaly'), 'detail': '',
                         'first_seen': a['first_seen'], 'last_seen': a['last_seen']}
                        for i, a in enumerate(snap.get('anomalies') or [])]
    return out


@bp.route('/traffic')
def traffic_page():
    return spa.render('Traffic')


@bp.route('/api/flows', methods=['GET'])
def get_flows():
    _rules, rules_error = classify.load_rules()
    snap = current()
    may_see_people = _can('seats.view')
    if not snap:
        return jsonify({'collector': False, 'rules_error': rules_error, 'can_see_seats': may_see_people})
    out = dict(public(snap, may_see_people))   # a copy: the answer below is per request
    out['collector'] = True
    out['stale'] = time.time() - (snap.get('updated') or 0) > 60
    out['rules_error'] = rules_error
    out['can_see_seats'] = may_see_people
    lang = i18n.language(request.headers.get('Accept-Language'))
    if out.get('anomalies') and lang != 'en':
        # The summary keeps them in English (the agent sends it too); a new list, so it stays that way.
        out['anomalies'] = [{**a, 'title': i18n.log_text(a.get('title'), lang),
                             'detail': i18n.log_text(a.get('detail'), lang)} for a in out['anomalies']]
    return jsonify(out)


def init_demo_flows(app):
    """FLOORBIT_DEMO=1: flows for the demo hall, without a collector (floorbit/flows/demo.py)."""
    from ..flows.demo import DemoFlows
    demo = DemoFlows()
    app.extensions['floorbit_demo_flows'] = demo
    try:
        demo.start()
    except Exception as exc:  # noqa: BLE001  # a demo hiccup must not stop the app
        print(f'[demo] no demo flows: {exc}')
