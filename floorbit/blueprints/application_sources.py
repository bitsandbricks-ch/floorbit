"""Rule sources for the applications (issue #1503): files fetched on a schedule. Rules in
floorbit/application_sources.py, docs in docs/applications.md. All of it needs settings.manage
(auth/roles.py): a source's URL can carry a token.

- ``GET /api/applications/sources``: the sources, how each last fetch went, and whether they are frozen.
- ``POST /api/applications/sources``: add one ``{name, url, every_hours, on}``.
- ``PUT /api/applications/sources/<id>``: change one (also ``position`` in the list: higher wins).
- ``DELETE /api/applications/sources/<id>``: remove one and its copy.
- ``POST /api/applications/sources/<id>/sync``: fetch it now (refused while frozen).
- ``PUT /api/applications/sources-frozen``: ``{frozen}``, stop or start fetching.
"""
from flask import Blueprint, g, jsonify, request

from .. import application_sources as sources
from .. import audit

bp = Blueprint('application_sources', __name__)


def _answer():
    return {'sources': sources.status(), 'frozen': sources.frozen()}


def _failed(exc):
    return jsonify({'error': exc.message}), exc.status


@bp.route('/api/applications/sources', methods=['GET'])
def list_sources():
    return jsonify(_answer())


@bp.route('/api/applications/sources', methods=['POST'])
def add_source():
    try:
        entry = sources.add(request.get_json(silent=True))
    except sources.SourceError as exc:
        return _failed(exc)
    audit.record('applications', 'Added a rule source', g.get('audit_user'), entry['name'])
    return jsonify(entry), 201


@bp.route('/api/applications/sources/<source_id>', methods=['PUT'])
def change_source(source_id):
    body = request.get_json(silent=True)
    try:
        entry = sources.change(source_id, body)
    except sources.SourceError as exc:
        return _failed(exc)
    audit.record('applications', 'Changed a rule source', g.get('audit_user'), entry['name'],
                 fields=sorted(k for k in (body or {}) if k in ('name', 'url', 'every_hours', 'on', 'position')))
    return jsonify(entry)


@bp.route('/api/applications/sources/<source_id>', methods=['DELETE'])
def remove_source(source_id):
    gone = sources.remove(source_id)
    if gone is None:
        return jsonify({'error': 'No such source.'}), 404
    audit.record('applications', 'Removed a rule source', g.get('audit_user'), gone['name'])
    return jsonify({'ok': True})


@bp.route('/api/applications/sources/<source_id>/sync', methods=['POST'])
def sync_source(source_id):
    if sources.frozen():
        return jsonify({'error': 'The sources are frozen: unfreeze them to fetch.'}), 409
    try:
        row = sources.sync(source_id)
    except sources.SourceError as exc:
        return _failed(exc)
    audit.record('applications', 'Fetched a rule source', g.get('audit_user'), row['name'], ok=bool(row['ok']))
    return jsonify(row)


@bp.route('/api/applications/sources-frozen', methods=['PUT'])
def freeze_sources():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('frozen'), bool):
        return jsonify({'error': 'Send {"frozen": true} or {"frozen": false}.'}), 400
    sources.set_frozen(body['frozen'])
    audit.record('applications', 'Froze the rule sources' if body['frozen'] else 'Unfroze the rule sources',
                 g.get('audit_user'))
    return jsonify(_answer())
