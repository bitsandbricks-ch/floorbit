"""Network > Switches (issue #902): the page only. Its rows are the inventory list
(``GET /api/inventory``), which carries the live columns."""
from flask import Blueprint

from .. import spa

bp = Blueprint('switches_page', __name__)


@bp.route('/switches')
def switches_page():
    return spa.render('Switches')
