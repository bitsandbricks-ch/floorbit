"""Refuse a JSON body that is a bare string, number or boolean, or holds NaN or infinity.

Handlers read bodies as ``request.get_json(silent=True) or {}`` and then ``body.get(...)``. A body
of ``"x"`` or ``5`` is truthy, so it reached ``.get`` and answered 500. Objects, lists (some
handlers take one) and ``null`` pass through as before.

Answers go the other way through FiniteJSONProvider: NaN and infinity become null.

Python's JSON reader also takes ``NaN``, ``Infinity`` and ``1e999``, which no browser sends: as a
whole number they raised OverflowError (a 500) in many handlers, and stored as a position they
would make every later answer JSON the browser can't read.
"""
import json
import math

from flask import jsonify, request
from flask.json.provider import DefaultJSONProvider

MESSAGE = 'Send a JSON object.'
NOT_FINITE = 'Numbers must be finite (no NaN or Infinity).'


class _NotFinite(ValueError):
    pass


def _constant(name):
    raise _NotFinite(name)


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        raise _NotFinite(text)
    return value


def _finite(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


class FiniteJSONProvider(DefaultJSONProvider):
    """Answers never hold NaN or Infinity: no browser can read them, so one NaN from a monitoring
    source (Prometheus answers "NaN" for a rate over nothing) broke the whole page. They become null."""

    def dumps(self, obj, **kwargs):
        try:
            return super().dumps(obj, allow_nan=False, **kwargs)
        except ValueError:
            return super().dumps(_finite(obj), **kwargs)


def init_json_body(app):
    app.json = FiniteJSONProvider(app)

    @app.before_request
    def refuse_bare_json_values():
        if request.method not in ('POST', 'PUT', 'PATCH') or not request.is_json:
            return None
        body = request.get_json(silent=True)
        if body is not None and not isinstance(body, dict):
            return jsonify({'error': MESSAGE}), 400
        if body:
            try:
                json.loads(request.get_data(cache=True), parse_constant=_constant, parse_float=_float)
            except _NotFinite:
                return jsonify({'error': NOT_FINITE}), 400
            except ValueError:
                pass
        return None
