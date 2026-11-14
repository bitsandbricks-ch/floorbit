"""The service health wall (issue #28). The checks come from health plugins (floorbit/health.py).

- ``GET /health``: the wall, for the ops screen or a kiosk browser (``?theme=`` sticks per screen).
- ``GET /api/health``: every service with its status, summary and metrics.
- ``POST /api/health/check``: ask every health plugin now instead of waiting for the next poll.
"""
from flask import Blueprint, current_app, jsonify

from .. import spa

bp = Blueprint('health', __name__)


def _wall():
    return current_app.extensions['floorbit_health']


@bp.route('/health')
def health_page():
    return spa.render('Service health')


@bp.route('/api/health', methods=['GET'])
def health():
    return jsonify(_wall().fresh())


@bp.route('/api/health/check', methods=['POST'])
def check_now():
    _wall().poll_once()
    return jsonify(_wall().snapshot())
