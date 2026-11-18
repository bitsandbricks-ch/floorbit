"""Refuse a JSON body that is a bare string, number or boolean, or holds NaN or infinity.

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

A whole number of hundreds of digits (no browser sends one) raised OverflowError the same way
wherever it became a float, so numbers have at most MAX_DIGITS digits. Answers go the other way
through FiniteJSONProvider: NaN and infinity become null.
"""
import json
import math

from flask import jsonify, request
from flask.json.provider import DefaultJSONProvider

MESSAGE = 'Send a JSON object.'
TOO_DEEP = 'The JSON is nested too deeply.'
NOT_FINITE = 'Numbers must be finite (no NaN or Infinity).'
MAX_DEPTH = 64
TOO_LONG = 'Numbers can have at most 30 digits.'
MAX_DIGITS = 30        # far past any count or id here; a float holds about 300


class _TooLong(ValueError):
    pass


class _NotFinite(ValueError):
    pass


def _constant(name):
    raise _NotFinite(name)


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        raise _NotFinite(text)
    return value


def _int(text):
    if len(text.lstrip('-')) > MAX_DIGITS:
        raise _TooLong(text[:40])
    return int(text)


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


_finite = finite     # the name master's callers use


class FiniteJSONProvider(DefaultJSONProvider):
    """Answers never hold NaN or Infinity: no browser can read them, so one NaN from a monitoring
    source (Prometheus answers "NaN" for a rate over nothing) broke the whole page. They become null."""

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
        if body and not request.path.startswith('/api/agent/'):
            try:
                json.loads(request.get_data(cache=True), parse_constant=_constant, parse_float=_float,
                           parse_int=_int)
            except _NotFinite:
                return jsonify({'error': NOT_FINITE}), 400
            except _TooLong:
                return jsonify({'error': TOO_LONG}), 400
            except ValueError:
                pass
        return None
