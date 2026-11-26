"""The flow lookup (#1481, C): the raw flows of a seat, an address, an owner or a port, for an incident.

- ``/flow-lookup``: the page.
- ``POST /api/traffic/lookup`` ``{seat, source, destination, ports, window | since + until, reason,
  csv}``: asks every connected agent (the netflow-relay plugin's ``lookup`` call,
  floorbit/flows/lookup.py) and answers what they found, newest first. ``csv: true`` answers a CSV
  of the same search.

Needs ``traffic.investigate`` (Admin and Lead by default, auth/roles.py) and a reason. Every search
and every CSV goes to the audit log with its reason, before the agents are asked, so a search that
fails is logged too. Floorbit keeps no result.
"""
import csv
import io
import ipaddress
import re
import time

from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import agent_plugins, audit, spa
from ..flows import lookup, seat_maps
from ..plugins.base import PluginError

bp = Blueprint('flow_lookup', __name__)

WINDOWS = {'15m': 900, '1h': 3600, '6h': 6 * 3600, '24h': 86400, '7d': 7 * 86400}
REASON_MIN, REASON_MAX = 5, 300
ASN_RE = re.compile(r'^(?:as)?\s*(\d{1,10})$', re.I)
CSV_COLUMNS = ('time', 'source', 'source_seat', 'destination', 'destination_seat', 'protocol', 'source_port',
               'destination_port', 'owner', 'application', 'bytes', 'packets')


@bp.route('/flow-lookup')
def flow_lookup_page():
    return spa.render('Flow lookup')


def _query(body, now):
    """(args for the agents, what to write in the audit log) or raises QueryError."""
    seat = str(body.get('seat') or '').strip()
    source = str(body.get('source') or '').strip()
    destination = str(body.get('destination') or '').strip()
    ports = str(body.get('ports') or '').strip()
    args, said = {}, []
    if seat:
        seat_of, _ = seat_maps()
        ips = sorted(ip for ip, s in seat_of.items() if s.lower() == seat.lower())
        if not ips:
            raise lookup.QueryError(f'No seat {seat} with a known address.')
        args['sources'] = ips
        said.append(f'seat {seat}')
    if source:
        try:
            ipaddress.ip_address(source)
        except ValueError as exc:
            raise lookup.QueryError(f'"{source}" is not an address') from exc
        args['sources'] = sorted(set(args.get('sources') or []) | {source})
        said.append(source)
    if destination:
        m = ASN_RE.match(destination)
        if m:
            args['asn'] = int(m.group(1))
        else:
            args['destination'] = [destination]
        said.append(f'to {destination}')
    if ports:
        lookup.parse_ports(ports)
        args['ports'] = ports
        said.append(ports)
    window = body.get('window') or '1h'
    if body.get('since') or body.get('until'):
        try:
            args['since'], args['until'] = float(body.get('since') or 0), float(body.get('until') or now)
        except (TypeError, ValueError) as exc:
            raise lookup.QueryError('since and until are unix times') from exc
        said.append(time.strftime('%Y-%m-%d %H:%M', time.localtime(args['since'])) + ' to '
                    + time.strftime('%Y-%m-%d %H:%M', time.localtime(args['until'])))
    elif window in WINDOWS:
        args['since'], args['until'] = now - WINDOWS[window], now
        said.append(f'last {window}')
    else:
        raise lookup.QueryError(f'Pick a time: one of {", ".join(WINDOWS)}, or from and to.')
    lookup.Query(args, now=now)   # the same checks the agent makes, with the German texts here
    return args, ', '.join(said)


@bp.route('/api/traffic/lookup', methods=['POST'])
def search():
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    reason = ' '.join(str(body.get('reason') or '').split())
    if len(reason) < REASON_MIN:
        return jsonify({'error': 'Say why you look: the reason goes to the audit log.'}), 400
    if len(reason) > REASON_MAX:
        return jsonify({'error': f'Keep the reason to {REASON_MAX} characters.'}), 400
    now = time.time()
    try:
        args, said = _query(body, now)
    except lookup.QueryError as exc:
        return jsonify({'error': str(exc)}), 400
    as_csv = bool(body.get('csv'))
    audit.record('traffic', 'Exported a flow lookup' if as_csv else 'Searched the raw flows',
                 g.get('audit_user'), said, reason=reason)
    spec = current_app.extensions['floorbit_plugins'].specs.get('netflow-relay')
    if spec is None:
        return jsonify({'error': 'The Traffic from the hall plugin is missing.'}), 404
    try:
        answers = agent_plugins.ask(spec, 'call', 'lookup', args)
    except PluginError as exc:
        print(f'[flows] the flow lookup could not ask the agents: {exc}')
        return jsonify({'error': 'No local agent answered. Is one connected?'}), 502
    result = _merge(answers, args)
    if as_csv:
        return _csv(result['rows'])
    return jsonify(result)


def _merge(answers, args):
    seat_of, _ = seat_maps()
    rows, agents = [], []
    total = size = 0
    peers, stopped = None, False
    for a in answers:
        res = a.get('result') if isinstance(a.get('result'), dict) else {}
        error = a.get('error') or res.get('error')
        agents.append({'name': a.get('name'), 'total': res.get('total') if not error else None,
                       'error': str(error)[:300] if error else None, 'oldest': res.get('oldest'),
                       'stopped': bool(res.get('stopped'))})
        if error:
            continue
        for row in res.get('rows') or []:
            if isinstance(row, dict):
                rows.append({**row, 'agent': a.get('name'), 'src_seat': seat_of.get(row.get('src')),
                             'dst_seat': seat_of.get(row.get('dst'))})
        total += int(res.get('total') or 0)
        size += int(res.get('bytes') or 0)
        if res.get('peers') is not None:
            peers = (peers or 0) + int(res['peers'])
        stopped = stopped or bool(res.get('stopped'))
    rows.sort(key=lambda r: (r.get('t') or 0, r.get('bytes') or 0), reverse=True)
    return {'rows': rows[:lookup.LIMIT], 'total': total, 'bytes': size, 'peers': peers, 'stopped': stopped,
            'agents': agents, 'since': args['since'], 'until': args['until']}


def _csv(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        owner = r.get('owner') or {}
        writer.writerow([
            time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(r.get('t') or 0)),
            r.get('src'), r.get('src_seat') or '', r.get('dst'), r.get('dst_seat') or '',
            r.get('protocol'), r.get('sport'), r.get('dport'),
            f"AS{owner['asn']} {owner.get('name') or ''}".strip() if owner.get('asn') else '',
            r.get('application') or '', r.get('bytes'), r.get('packets')])
    filename = f"floorbit-flows-{time.strftime('%Y%m%d-%H%M')}.csv"
    return Response(out.getvalue().encode('utf-8-sig'), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store'})
