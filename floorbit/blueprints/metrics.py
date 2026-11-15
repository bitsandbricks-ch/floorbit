"""Prometheus metrics (issue #153). The counts live in floorbit/metrics.py; docs in docs/metrics.md.

- ``GET /api/metrics``: the Prometheus text format. 404 until Settings > Prometheus metrics turns it
  on. Needs ``floorplan.view`` like every read, so a scraper uses a read-only API token.
"""
from flask import Blueprint, Response, current_app, jsonify

from .. import metrics

bp = Blueprint('metrics', __name__)


@bp.route('/api/metrics')
def prometheus():
    if not current_app.extensions['floorbit_settings'].get('metrics.enabled'):
        return jsonify({'error': 'Prometheus metrics are switched off.'}), 404
    return Response(metrics.render(), mimetype='text/plain; version=0.0.4')
