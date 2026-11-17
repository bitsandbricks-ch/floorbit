"""IP and MAC history (docs/endpoints.md): where each machine was seen. ``seats.view`` (auth/roles.py).

- ``GET /endpoints``: the page (React).
- ``GET /api/endpoints?q=``: rows whose IP starts with ``q`` or whose MAC holds it.
- ``GET /api/endpoints?device=&port=``: a switch port's history.
- ``GET /api/endpoints?seat=``: a seat's history.
"""
from flask import Blueprint, jsonify, request

from .. import endpoints, spa
from ..database import DatabaseError

bp = Blueprint('endpoints', __name__)


@bp.route('/endpoints')
def endpoints_page():
    return spa.render('Endpoints')


@bp.route('/api/endpoints')
def find():
    args = request.args
    history = endpoints.history()
    try:
        if args.get('seat'):
            rows = history.at_seat(args['seat'][:60])
        elif args.get('device') and args.get('port'):
            rows = history.at_port(args['device'][:120], args['port'][:120])
        else:
            rows = history.search(args.get('q', ''))
    except DatabaseError:
        return jsonify({'error': 'The database does not answer right now.'}), 503
    return jsonify({'rows': rows, 'status': history.status()})
