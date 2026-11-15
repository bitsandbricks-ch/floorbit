"""Logs (issue #91): what switches, firewalls and DHCP servers sent by syslog. Receiving and keeping
lives in floorbit/syslog.py.

- ``GET /logs``: the page.
- ``GET /api/logs``: newest lines first, with the receiver's status. Filters: ``q`` (words that all
  have to be in the line), ``device``, ``seat``, ``port`` (``Gi1/0/4`` or ``GigabitEthernet1/0/4``),
  ``severity`` (the least severe level to show, ``warning`` shows emerg to warning), ``after`` (only
  lines newer than this id, for the live tail), ``before`` (only older, for paging) and ``limit``
  (1 to 1000, 200 by default). Needs ``seats.view``: logs name MACs and IPs.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import spa, syslog

bp = Blueprint('logs', __name__)


@bp.app_context_processor
def syslog_flags():
    receiver = current_app.extensions.get('floorbit_syslog')
    return {'syslog_on': bool(receiver and (syslog.settings()['enabled'] or receiver.demo))}


@bp.route('/logs')
def logs_page():
    return spa.render('Logs')


def _int(name, default, low, high):
    raw = request.args.get(name)
    if raw in (None, ''):
        return default
    value = int(raw)   # ValueError is answered below
    if not low <= value <= high:
        raise ValueError
    return value


@bp.route('/api/logs', methods=['GET'])
def get_logs():
    args = request.args
    try:
        after = _int('after', 0, 0, 2**53)
        before = _int('before', None, 1, 2**53)
        limit = _int('limit', 200, 1, 1000)
    except ValueError:
        return jsonify({'error': 'after and before are line ids; limit is a whole number from 1 to 1000.'}), 400
    severity = (args.get('severity') or '').strip().lower()
    if severity and severity not in syslog.SEVERITIES:
        return jsonify({'error': f"severity is one of {', '.join(syslog.SEVERITIES)}."}), 400
    receiver = current_app.extensions['floorbit_syslog']
    lines = receiver.search(q=args.get('q', ''), device=args.get('device', ''), seat=args.get('seat', ''),
                            port=args.get('port', ''), severity=severity, after=after, before=before, limit=limit)
    return jsonify({'lines': lines, 'status': receiver.status()})
