"""Feature switches (issue #114). Rules in floorbit/features.py.

- ``GET /api/features``: which features are off, for the navigation. Anyone who sees the floor plan.
- ``GET /settings/features``: the page (React), admins only.
- ``GET|PUT /api/settings/features``: every feature with its state; ``{"power": false}`` turns one off.
- ``GET /api/settings/capabilities``: each capability (floorbit/capabilities.py), on, off or partly,
  with what it still needs. ``PUT /api/settings/capabilities/<id>`` ``{"on": true}`` switches its parts.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import events

from .. import audit, capabilities, features, spa

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


def _capabilities():
    from .. import agent_link, sources
    return capabilities.status(current_app.extensions['floorbit_settings'], sources.registry,
                               agents=agent_link.all_agents())


@bp.route('/api/settings/capabilities', methods=['GET'])
def list_capabilities():
    return jsonify({'capabilities': _capabilities()})


@bp.route('/api/settings/capabilities/<cap_id>', methods=['PUT'])
def switch_capability(cap_id):
    from .. import agent_plugins, runtime, sources
    body = request.get_json(silent=True) or {}
    settings = current_app.extensions['floorbit_settings']
    try:
        changed = capabilities.switch(cap_id, body.get('on'), settings, sources.registry)
    except capabilities.CapabilityError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if changed:
        runtime.apply(settings)
        agent_plugins.reload_agents()     # the agents pull it within a minute anyway
        audit.record('settings', 'Turned a capability on' if body['on'] else 'Turned a capability off',
                     user=g.get('audit_user'), target=f"{cap_id}: {', '.join(changed)}")
        events.publish('features.changed', {})
    return jsonify({'capabilities': _capabilities()})
