"""Build planner (issue #34). Rules in floorbit/planner.py.

- ``GET /planner``: the page (React).
- ``GET /api/planner``: the plan from the seat blocks, the settings and the switch models.
- ``PUT /api/planner/settings``: ports, spare ports, VLANs, names and the management network.
- ``GET|PUT|DELETE /api/planner/templates/<id>``: a switch model's config template (Jinja, sandboxed).
- ``GET /api/planner/config/<switch>``: one switch's config, to read before downloading.
- ``GET /api/planner/configs.zip``, ``/api/planner/plan.csv``, ``/api/planner/labels.pdf``: downloads.
- ``POST /api/planner/apply``: add the planned switches that don't exist yet to the floor plan.

All of it needs ``floorplan.edit``: the configs are the network's design.
"""
from flask import Blueprint, Response, current_app, jsonify, request

from integrations import events

from .. import planner, spa
from ..store import load_data

bp = Blueprint('planner', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _event_name():
    return current_app.extensions['floorbit_settings'].get('theme.name') or ''


def _models(data):
    return [{k: v for k, v in t.items() if k != 'text'} for t in planner.templates(data).values()]


@bp.route('/planner')
def planner_page():
    return spa.render('Build planner')


@bp.route('/api/planner', methods=['GET'])
def get_plan():
    data = load_data()
    try:
        plan = planner.build(data)
    except planner.PlannerError as exc:
        return _error(exc)
    return jsonify({'plan': plan, 'models': _models(data)})


@bp.route('/api/planner/settings', methods=['PUT'])
def put_settings():
    try:
        saved = planner.save_settings(request.get_json(silent=True) or {})
    except planner.PlannerError as exc:
        return _error(exc)
    return jsonify(saved)


@bp.route('/api/planner/templates/<template_id>', methods=['GET'])
def get_template(template_id):
    found = planner.templates().get(template_id)
    if not found:
        return jsonify({'error': 'No such switch model.'}), 404
    return jsonify(found)


@bp.route('/api/planner/templates/<template_id>', methods=['PUT'])
def put_template(template_id):
    try:
        return jsonify(planner.save_template(template_id, request.get_json(silent=True) or {}))
    except planner.PlannerError as exc:
        return _error(exc)


@bp.route('/api/planner/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    try:
        planner.delete_template(template_id)
    except planner.PlannerError as exc:
        return _error(exc)
    return jsonify({'ok': True})


def _plan():
    data = load_data()
    return data, planner.build(data)


@bp.route('/api/planner/config/<name>', methods=['GET'])
def one_config(name):
    try:
        data, plan = _plan()
        sw = next((s for s in plan['switches'] if s['name'] == name), None)
        if not sw:
            return jsonify({'error': 'No such switch in the plan.'}), 404
        return jsonify({'name': name, 'config': planner.render(plan, sw, data, _event_name())})
    except planner.PlannerError as exc:
        return _error(exc)


def _download(body, mimetype, filename):
    return Response(body, mimetype=mimetype, headers={'Content-Disposition': f'attachment; filename="{filename}"',
                                                      'Cache-Control': 'no-store'})


@bp.route('/api/planner/configs.zip', methods=['GET'])
def configs():
    try:
        data, plan = _plan()
        return _download(planner.configs_zip(plan, data, _event_name()), 'application/zip', 'switch-configs.zip')
    except planner.PlannerError as exc:
        return _error(exc)


@bp.route('/api/planner/plan.csv', methods=['GET'])
def plan_csv():
    try:
        _, plan = _plan()
    except planner.PlannerError as exc:
        return _error(exc)
    return _download(planner.plan_csv(plan), 'text/csv', 'port-plan.csv')


@bp.route('/api/planner/labels.pdf', methods=['GET'])
def labels():
    try:
        _, plan = _plan()
    except planner.PlannerError as exc:
        return _error(exc)
    copies = request.args.get('copies', '2')
    block = (request.args.get('block') or '').upper() or None
    return _download(planner.labels_pdf(plan, copies=int(copies) if copies.isdigit() else 2, block=block),
                     'application/pdf', 'cable-labels.pdf')


@bp.route('/api/planner/apply', methods=['POST'])
def apply():
    try:
        _, plan = _plan()
    except planner.PlannerError as exc:
        return _error(exc)
    added = planner.add_switches(plan)
    if added:
        events.publish('data.changed', {'resource': 'switches', 'method': 'POST', 'path': request.path})
    return jsonify({'added': added})
