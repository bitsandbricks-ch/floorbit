"""Refuse a JSON body that is a bare string, number or boolean.

Handlers read bodies as ``request.get_json(silent=True) or {}`` and then ``body.get(...)``. A body
of ``"x"`` or ``5`` is truthy, so it reached ``.get`` and answered 500. Objects, lists (some
handlers take one) and ``null`` pass through as before.

A body nested deeper than MAX_DEPTH is refused too: ``[[[[...`` a megabyte deep made the parser
raise RecursionError (a 500), and a value a few hundred levels deep that got saved could make
every later save of the document fail.

So are NaN and Infinity (and 1e999, which reads as Infinity). Python's parser takes them, and
handlers that check with int() failed with OverflowError (a 500). Browsers never send them
(JSON.stringify writes null), and one that got saved would come back out as a bare NaN no browser
parses. The local agent's calls are left alone: its numbers come from devices and its own code
decides what to keep.
"""
import math

from flask import jsonify, request
from flask.json.provider import DefaultJSONProvider

MESSAGE = 'Send a JSON object.'
TOO_DEEP = 'The JSON is nested too deeply.'
NOT_FINITE = 'Numbers must be finite: no NaN or Infinity.'
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


def not_finite(value):
    """True when a number anywhere in the value is NaN or infinite. Walks without recursion."""
    stack = [value]
    while stack:
        value = stack.pop()
        if isinstance(value, float):
            if not math.isfinite(value):
                return True
        elif isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


def finite(value):
    """The value with every NaN and infinite float as None."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    return value


class FiniteJSONProvider(DefaultJSONProvider):
    """Answers never hold a bare NaN or Infinity: JSON.parse refuses them, so one saved before the
    checks above (or read from a device) would stop a whole page from loading. They go out as null
    instead, and the walk only runs when there is one."""

    def dumps(self, obj, **kwargs):
        try:
            return super().dumps(obj, allow_nan=False, **kwargs)
        except ValueError:
            return super().dumps(finite(obj), **kwargs)


def init_json_body(app):
    app.json = FiniteJSONProvider(app)

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
        if not request.path.startswith('/api/agent/') and not_finite(body):
            return jsonify({'error': NOT_FINITE}), 400
        if body is not None and not isinstance(body, dict):
            return jsonify({'error': MESSAGE}), 400
        return None
