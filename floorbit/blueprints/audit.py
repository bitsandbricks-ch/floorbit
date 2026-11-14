"""Settings > Audit log: the page, its JSON and a CSV download (admins only, under /settings)."""
import csv
import io
import time

from flask import Blueprint, Response, jsonify, render_template, request

from .. import audit

bp = Blueprint('audit', __name__)

CSV_COLUMNS = ('time', 'user', 'area', 'action', 'target', 'fields', 'ok')


def _cell(value):
    """Switch names and usernames are typed by people: keep a spreadsheet from running them."""
    value = str(value)
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


def _query():
    try:
        limit = min(max(int(request.args.get('limit', 100)), 1), 1000)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        raise ValueError('limit and offset must be whole numbers') from None
    area = request.args.get('area') or None
    if area and area not in audit.AREAS:
        raise ValueError(f"area must be one of: {', '.join(audit.AREAS)}")
    return dict(limit=limit, offset=offset, area=area,
                user=request.args.get('user') or None, query=request.args.get('q') or None)


@bp.route('/settings/audit')
def audit_page():
    return render_template('audit.html', areas=audit.AREAS)


@bp.route('/api/settings/audit')
def audit_entries():
    try:
        rows, total = audit.read(**_query())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'entries': rows, 'total': total})


@bp.route('/api/settings/audit.csv')
def audit_csv():
    try:
        q = _query()
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    rows, _ = audit.read(**{**q, 'limit': 100000, 'offset': 0})
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for e in rows:
        writer.writerow([_cell(v) for v in (
            e.get('time', ''), e.get('user') or '', e.get('area', ''), e.get('action', ''),
            e.get('target', ''), ' '.join(e.get('fields', [])), 'no' if e.get('ok') is False else 'yes')])
    filename = f"floorbit-audit-{time.strftime('%Y%m%d-%H%M')}.csv"
    # utf-8-sig so Excel opens umlauts in names correctly
    return Response(out.getvalue().encode('utf-8-sig'), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"',
                             'Cache-Control': 'no-store'})
