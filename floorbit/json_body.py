"""Refuse a JSON body that is a bare string, number or boolean.

Handlers read bodies as ``request.get_json(silent=True) or {}`` and then ``body.get(...)``. A body
of ``"x"`` or ``5`` is truthy, so it reached ``.get`` and answered 500. Objects, lists (some
handlers take one) and ``null`` pass through as before.

A body nested deeper than MAX_DEPTH is refused too: ``[[[[...`` a megabyte deep made the parser
raise RecursionError (a 500), and a value a few hundred levels deep that got saved could make
every later save of the document fail.
"""
from flask import jsonify, request

MESSAGE = 'Send a JSON object.'
TOO_DEEP = 'The JSON is nested too deeply.'
MAX_DEPTH = 64


def too_deep(value, limit=MAX_DEPTH):
    """True when lists and objects nest more than ``limit`` levels. Walks without recursion."""
    stack = [(value, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, dict):
            value = value.values()
        elif not isinstance(value, list):
            continue
        if depth > limit:
            return True
        stack.extend((v, depth + 1) for v in value if isinstance(v, (dict, list)))
    return False


def init_json_body(app):
    @app.before_request
    def refuse_bare_json_values():
        # DELETE too: a handler, or the audit log after it, may read its body (DELETE /api/notice
        # with a deep one answered 500 from the audit log's after_request).
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE') or not request.is_json:
            return None
        try:
            body = request.get_json(silent=True)
        except RecursionError:
            return jsonify({'error': TOO_DEEP}), 400
        if too_deep(body):
            return jsonify({'error': TOO_DEEP}), 400
        if request.method == 'DELETE':      # its body was never checked for shape: keep it that way
            return None
        if body is not None and not isinstance(body, dict):
            return jsonify({'error': MESSAGE}), 400
        return None
