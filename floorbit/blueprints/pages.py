"""The HTML pages of the editor and the kiosk view, and the list of pages for "Go to"."""
from flask import Blueprint, current_app, jsonify, render_template

from .. import page_index

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/kiosk')
def kiosk():
    """Read-only floor plan for a big screen (see docs/kiosk.md)."""
    return render_template('kiosk.html')


@bp.route('/api/pages')
def page_list():
    """The pages this account may open now, for "Go to" (Ctrl+K) on every page (issue #250)."""
    ctx = {}
    # The same context the floor plan's top bar is drawn with: features, permissions, set-up flags.
    current_app.update_template_context(ctx)
    return jsonify({'pages': page_index.for_context(ctx)})
