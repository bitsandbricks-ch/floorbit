"""DNS analytics (issue #87): what the hall looks up. Counting lives in floorbit/dns.py.

- ``GET /dns``: the page.
- ``GET /api/dns?hours=24``: hall-wide numbers for the last 1 to 168 hours: lookups per hour, the
  top sites, categories, new sites and blocked sites. Only sites at least ``DNS_MIN_SEATS``
  different clients looked up in an hour are named; nothing is per seat or per person.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import spa

bp = Blueprint('dns', __name__)


@bp.route('/dns')
def dns_page():
    return spa.render('Dns')


@bp.route('/api/dns', methods=['GET'])
def get_dns():
    try:
        hours = int(request.args.get('hours', 24))
    except ValueError:
        return jsonify({'error': 'hours is a whole number from 1 to 168.'}), 400
    if not 1 <= hours <= 168:
        return jsonify({'error': 'hours is a whole number from 1 to 168.'}), 400
    return jsonify(current_app.extensions['floorbit_dns'].snapshot(hours))
