"""The HTML pages of the editor and the kiosk view."""
from flask import Blueprint, render_template

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/kiosk')
def kiosk():
    """Read-only floor plan for a big screen (see docs/kiosk.md)."""
    return render_template('kiosk.html')
