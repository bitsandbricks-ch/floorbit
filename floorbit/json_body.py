"""Refuse a JSON body that is a bare string, number or boolean.

Handlers read bodies as ``request.get_json(silent=True) or {}`` and then ``body.get(...)``. A body
of ``"x"`` or ``5`` is truthy, so it reached ``.get`` and answered 500. Objects, lists (some
handlers take one) and ``null`` pass through as before.
"""
from flask import jsonify, request

MESSAGE = 'Send a JSON object.'


def init_json_body(app):
    @app.before_request
    def refuse_bare_json_values():
        if request.method not in ('POST', 'PUT', 'PATCH') or not request.is_json:
            return None
        body = request.get_json(silent=True)
        if body is not None and not isinstance(body, dict):
            return jsonify({'error': MESSAGE}), 400
        return None
