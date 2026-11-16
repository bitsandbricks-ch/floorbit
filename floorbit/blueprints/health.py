"""The service health wall (issue #28). The checks come from health plugins (floorbit/health.py).

- ``GET /health``: the wall, for the ops screen or a kiosk browser (``?theme=`` sticks per screen).
- ``GET /api/health``: every service with its status, summary and metrics, and until when it is
  muted (issue #260; who muted it and why stay on the Problems page).
- ``POST /api/health/check``: ask every health plugin now instead of waiting for the next poll.
- ``GET /healthz``: "the app answers", for the Docker healthcheck and load balancers. Open without
  signing in, so it says nothing else; 503 when the database (``FLOORBIT_DATABASE_URL``) doesn't answer.
"""
from flask import Blueprint, current_app, jsonify

from integrations import alerting

from .. import database, spa

bp = Blueprint('health', __name__)


def _wall():
    return current_app.extensions['floorbit_health']


@bp.route('/healthz')
def alive():
    # Without its database Floorbit can't keep anything: say so, so the orchestrator restarts it
    # or the load balancer stops sending users (docs/database.md).
    if not database.status()['ok']:
        return jsonify({'ok': False}), 503
    return jsonify({'ok': True})


alive._auth_public = True   # what auth.public_endpoint sets


@bp.route('/health')
def health_page():
    return spa.render('Service health')


def _with_mutes(wall):
    muted = alerting.mutes()
    checks = [{**c, 'muted_until': (muted.get(alerting.service_key(c['id'])) or {}).get('until')}
              for c in wall.get('checks') or []]
    return {**wall, 'checks': checks}


@bp.route('/api/health', methods=['GET'])
def health():
    return jsonify(_with_mutes(_wall().fresh()))


@bp.route('/api/health/check', methods=['POST'])
def check_now():
    _wall().poll_once()
    return jsonify(_with_mutes(_wall().snapshot()))
