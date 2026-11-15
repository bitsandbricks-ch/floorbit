"""Feature switches (issue #114). Rules in floorbit/features.py.

- ``GET /api/features``: which features are off, for the navigation. Anyone who sees the floor plan.
- ``GET /settings/features``: the page (React), admins only.
- ``GET|PUT /api/settings/features``: every feature with its state; ``{"power": false}`` turns one off.
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, features, spa

bp = Blueprint('features', __name__)


@bp.route('/settings/features')
def features_page():
    return spa.render('Features')


@bp.route('/api/features', methods=['GET'])
def features_off():
    return jsonify({'off': sorted(features.off())})


@bp.route('/api/settings/features', methods=['GET'])
def list_features():
    return jsonify({'features': features.status(), 'env': features.ENV})


@bp.route('/api/settings/features', methods=['PUT'])
def change_features():
    body = request.get_json(silent=True)
    try:
        changed = features.update(body)
    except features.FeatureError as exc:
        return jsonify({'error': str(exc)}), 400
    if changed:
        words = ', '.join(f"{k} {'on' if body[k] else 'off'}" for k in changed)
        audit.record('settings', 'Turned features on or off', user=g.get('audit_user'), target=words)
        events.publish('features.changed', {})
    return jsonify({'features': features.status(), 'env': features.ENV})
