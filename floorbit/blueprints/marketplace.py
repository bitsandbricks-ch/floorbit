"""The plugin Marketplace (floorbit/marketplace.py, docs/marketplace.md): admins only, through the
``/api/settings`` rule of the request guard. Every install, update, rollback and removal is in the
audit log. Nothing here can trust a key or add a source: that is the operator's, where the server runs.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import marketplace
from ..plugins import PluginError
from ..plugins.bundles import ID_RE

bp = Blueprint('marketplace', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _id(plugin_id):
    return plugin_id if ID_RE.match(plugin_id) else None


@bp.route('/api/settings/marketplace', methods=['GET'])
def catalog():
    force = request.args.get('refresh') in ('1', 'true')
    return jsonify(marketplace.catalog(_registry(), force=force))


@bp.route('/api/settings/marketplace/<plugin_id>', methods=['POST'])
def install(plugin_id):
    if not _id(plugin_id):
        return jsonify({'error': 'No such plugin'}), 404
    body = request.get_json(silent=True) or {}
    version = body.get('version')
    if version is not None and not isinstance(version, str):
        return jsonify({'error': 'version must be text'}), 400
    try:
        done = marketplace.install(_registry(), plugin_id, version, g.get('audit_user'))
    except PluginError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'id': plugin_id, **done})


@bp.route('/api/settings/marketplace/<plugin_id>/rollback', methods=['POST'])
def rollback(plugin_id):
    if not _id(plugin_id):
        return jsonify({'error': 'No such plugin'}), 404
    try:
        done = marketplace.rollback(_registry(), plugin_id, g.get('audit_user'))
    except PluginError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'id': plugin_id, **done})


@bp.route('/api/settings/marketplace/<plugin_id>', methods=['DELETE'])
def uninstall(plugin_id):
    if not _id(plugin_id):
        return jsonify({'error': 'No such plugin'}), 404
    try:
        marketplace.uninstall(_registry(), plugin_id, g.get('audit_user'))
    except PluginError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'id': plugin_id, 'removed': True})
