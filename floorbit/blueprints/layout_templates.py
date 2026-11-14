"""The floor plan template library (issue #48). Rules live in floorbit/layout_templates.py.

- ``GET /templates``: the library page (React).
- ``GET /api/templates``; ``POST /api/templates`` ``{name, description, hall?}`` saves the floor plan
  (or one hall) as a new template.
- ``PATCH``/``DELETE /api/templates/<id>``; ``POST /api/templates/<id>/versions`` ``{hall?}`` saves it again
  as a new version; ``POST /api/templates/<id>/duplicate``.
- ``GET /api/templates/<id>/export?version=``, ``POST /api/templates/import``: a template as a file.
- ``POST /api/templates/<id>/apply`` ``{version?, hall?}``: start from it, replacing the floor plan.
"""
import json
import time

from flask import Blueprint, Response, jsonify, request

from .. import layout_templates as lib
from .. import spa
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('layout_templates', __name__)

MAX_BODY = 64 * 1024 * 1024   # background images travel inline, like in a backup


def _error(exc, status=400):
    return jsonify({'error': str(exc)}), status


def _hall(body):
    return body.get('hall') or None


@bp.route('/templates')
def templates_page():
    return spa.render('Templates')


@bp.route('/api/templates', methods=['GET'])
def list_templates():
    return jsonify({'templates': lib.all_templates()})


@bp.route('/api/templates', methods=['POST'])
def save_template():
    body = request.get_json(silent=True) or {}
    try:
        template = lib.create(body.get('name'), body.get('description'), lib.snapshot(load_data(), _hall(body)))
    except lib.TemplateError as exc:
        return _error(exc)
    return jsonify(lib.meta(template)), 201


@bp.route('/api/templates/<template_id>', methods=['PATCH'])
def change_template(template_id):
    try:
        template = lib.change(template_id, request.get_json(silent=True) or {})
    except KeyError:
        return _error('No such template', 404)
    except lib.TemplateError as exc:
        return _error(exc)
    return jsonify(lib.meta(template))


@bp.route('/api/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    try:
        lib.delete(template_id)
    except KeyError:
        return _error('No such template', 404)
    return jsonify({'success': True})


@bp.route('/api/templates/<template_id>/versions', methods=['POST'])
def save_version(template_id):
    body = request.get_json(silent=True) or {}
    try:
        template = lib.add_version(template_id, lib.snapshot(load_data(), _hall(body)))
    except KeyError:
        return _error('No such template', 404)
    except lib.TemplateError as exc:
        return _error(exc)
    return jsonify(lib.meta(template)), 201


@bp.route('/api/templates/<template_id>/duplicate', methods=['POST'])
def duplicate_template(template_id):
    try:
        template = lib.duplicate(template_id)
    except KeyError:
        return _error('No such template', 404)
    except lib.TemplateError as exc:
        return _error(exc)
    return jsonify(lib.meta(template)), 201


@bp.route('/api/templates/<template_id>/export', methods=['GET'])
def export_template(template_id):
    try:
        out = lib.export(lib.load(template_id), request.args.get('version'))
    except KeyError:
        return _error('No such template', 404)
    except lib.TemplateError as exc:
        return _error(exc, 404)
    slug = ''.join(c if c.isalnum() else '-' for c in out['name'].lower()).strip('-')[:40] or 'template'
    filename = f"floorbit-template-{slug}-{time.strftime('%Y%m%d')}.json"
    return Response(json.dumps(out, indent=2) + '\n', mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store'})


@bp.route('/api/templates/import', methods=['POST'])
def import_template():
    if (request.content_length or 0) > MAX_BODY:
        return _error(f'A template is at most {MAX_BODY // (1024 * 1024)} MB', 413)
    try:
        name, description, layout, dropped = lib.from_file(request.get_json(silent=True))
        template = lib.create(name, description, layout)
    except lib.TemplateError as exc:
        return _error(exc)
    return jsonify({**lib.meta(template), 'dropped': dropped}), 201


@bp.route('/api/templates/<template_id>/apply', methods=['POST'])
def apply_template(template_id):
    body = request.get_json(silent=True) or {}
    try:
        layout = lib.version(lib.load(template_id), body.get('version'))['layout']
    except KeyError:
        return _error('No such template', 404)
    except lib.TemplateError as exc:
        return _error(exc, 404)
    with data_lock:
        data = load_data()
        try:
            result = lib.apply(data, layout, _hall(body))
        except KeyError:
            return _error('No such hall', 404)
        except lib.TemplateError as exc:
            return _error(exc, 409)
        save_data(data)
    return jsonify(result)
