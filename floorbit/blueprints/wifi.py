"""Wi-Fi view (issue #98). The rules live in floorbit/wifi.py.

- ``GET /wifi``: the page (React).
- ``GET /api/wifi?hall=``: every access point with its radios (channel, load, client count), where
  it is on the floor plan, totals, busy APs and channel overlaps, and the hall's drawing.

Client counts only, never who: reading needs ``floorplan.view``, like the floor plan.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import halls, spa, wifi
from ..store import load_data
from .screen import PLAN_H, PLAN_W, plan

bp = Blueprint('wifi', __name__)
REACH = 140   # room around an AP on the drawing, in plan units: most of its circle


def _registry():
    return current_app.extensions['floorbit_plugins']


@bp.app_context_processor
def wifi_flags():
    try:
        return {'wifi_on': bool(_registry().feeders('wifi'))}
    except Exception:  # noqa: BLE001 - a nav link must never break a page
        return {'wifi_on': False}


@bp.route('/wifi')
def wifi_page():
    return spa.render('Wi-Fi')


@bp.route('/api/wifi', methods=['GET'])
def overview():
    data = load_data()
    all_halls = halls.halls(data)
    hall_id = request.args.get('hall') or halls.default_id(data)
    if hall_id not in {h['id'] for h in all_halls}:
        return jsonify({'error': 'No such hall.'}), 404
    body = wifi.overview(_registry(), data)
    drawing, _found = plan(data, hall_id=hall_id)
    # Plan coordinates, so the page can draw APs on the same drawing as the seat blocks.
    xs, ys = [], []
    for ap in body['aps']:
        here = ap['placed'] and ap['hall_id'] == hall_id
        ap['on_plan'] = here
        ap['px'] = round(ap['x'] / 100 * PLAN_W, 1) if here else None
        ap['py'] = round(ap['y'] / 100 * PLAN_H, 1) if here else None
        if here:
            xs += [ap['px'] - REACH, ap['px'] + REACH]
            ys += [ap['py'] - REACH, ap['py'] + REACH]
    if xs:
        # The drawing is cropped to the seat blocks: grow it so every AP and its circle fit.
        if drawing:
            x, y, w, h = (float(v) for v in drawing['box'].split())
            xs += [x, x + w]
            ys += [y, y + h]
        else:
            drawing = {'shapes': [], 'cell': 32}
        drawing['box'] = ' '.join(f'{v:.0f}' for v in (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    body.update(drawing=drawing, plan={'w': PLAN_W, 'h': PLAN_H}, hall=hall_id,
                halls=[{'id': h['id'], 'name': h['name']} for h in all_halls])
    return jsonify(body)
