"""Sidebar sections of your own (floorbit/nav_sections.py, docs/navigation.md).

- ``GET /settings/sidebar``: the editor (React), admins only.
- ``GET|PUT /api/settings/sidebar``: all sections as saved, admins only (auth/roles.py ``/api/settings``).
  Everyone else gets the sections they may see with the page list (``GET /api/pages``, floorbit/nav.py).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, nav_sections, spa

bp = Blueprint('nav_sections', __name__)


@bp.route('/settings/sidebar')
def sidebar_page():
    return spa.render('Sidebar sections')


@bp.route('/api/settings/sidebar', methods=['GET'])
def get_sections():
    return jsonify({'sections': nav_sections.saved(), 'icons': list(nav_sections.ICONS)})


@bp.route('/api/settings/sidebar', methods=['PUT'])
def save_sections():
    user = g.get('audit_user')
    try:
        sections = nav_sections.save(request.get_json(silent=True), user)
    except nav_sections.SectionError as exc:
        return jsonify({'error': str(exc)}), 400
    audit.record('settings', 'Changed the sidebar sections', user, ', '.join(s['name'] for s in sections) or '-')
    events.publish('nav.changed', {})
    return jsonify({'sections': sections, 'icons': list(nav_sections.ICONS)})
