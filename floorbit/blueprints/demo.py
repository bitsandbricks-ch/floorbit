"""Demo mode: the built-in ``demo`` plugin's made-up data, laid out on an empty floor plan.

The plugin (floorbit/builtin_plugins/demo) feeds the inventory, the seat mapping and the live
data. This module only places its switches and seat blocks, and only on a floor plan that is
still empty, so turning the demo on never moves anything someone placed by hand.

- ``POST /api/demo/layout`` (admins): sync the inventory and lay out the demo hall.
- With ``FLOORBIT_DEMO=1`` that happens once at start-up.
- Every page shows a "Demo data" banner while the plugin is on (``_theme_head.html``).
"""
import os
import uuid

from flask import Blueprint, current_app, jsonify

from .. import inventory
from ..store import load_data, save_data
from .inventory import data_lock, run_sync

bp = Blueprint('demo', __name__)


def _registry(app=None):
    return (app or current_app).extensions.get('floorbit_plugins')


def demo_on(app=None):
    registry = _registry(app)
    return bool(registry and registry.demo_on())


@bp.app_context_processor
def inject_demo():
    return {'demo_mode': demo_on()}


def _layout():
    spec = _registry().specs.get('demo')
    return getattr(spec.module, 'LAYOUT', None) if spec and spec.module else None


def seed():
    """Place the demo hall on an empty floor plan. Returns what it did."""
    layout = _layout()
    if not layout:
        return {'placed': 0, 'blocks': 0, 'skipped': 'the demo plugin has no layout'}
    run_sync()
    with data_lock:
        data = load_data()
        placed_already = any(d.get('x') is not None for d in inventory.devices(data))
        if placed_already or data.get('seat_blocks'):
            return {'placed': 0, 'blocks': 0, 'skipped': 'the floor plan is not empty'}
        placed = 0
        for dev in inventory.devices(data):
            pos = layout['devices'].get(dev['name'])
            if pos and 'demo' in (dev.get('refs') or {}):
                inventory.update(data, dev['id'], {'x': pos[0], 'y': pos[1]})
                placed += 1
        blocks = [{'id': str(uuid.uuid4()), 'seat_width': 3, 'seat_height': 3, 'spacing_x': 0.5,
                   'spacing_y': 1, 'rotation': 0, 'reverse_numbers': False, **b} for b in layout['blocks']]
        data['seat_blocks'] = blocks
        _seed_power(data, layout)
        save_data(data)
    return {'placed': placed, 'blocks': len(blocks)}


def _seed_power(data, layout):
    """The demo boards and circuits, on the blocks and switches just placed."""
    spec = layout.get('power')
    if not spec or (data.get('power') or {}).get('circuits'):
        return
    blocks = {b['name']: b['id'] for b in data.get('seat_blocks') or [] if b.get('name')}
    devices = {d['name']: d['id'] for d in inventory.devices(data)}
    boards = [{'id': uuid.uuid4().hex[:10], **b} for b in spec['boards']]
    board_ids = {b['name']: b['id'] for b in boards}
    circuits = []
    for c in spec['circuits']:
        circuits.append({'id': uuid.uuid4().hex[:10], 'board': board_ids[c['board']], 'name': c['name'],
                         'phase': c['phase'], 'rating_a': float(c['rating_a']), 'meter': c['meter'],
                         'blocks': [{'block': blocks[c['block']], 'rows': c.get('rows') or []}]
                         if c.get('block') in blocks else [],
                         'switches': [devices[n] for n in c.get('switches') or [] if n in devices],
                         'tripped': None, 'reading': None})
    data['power'] = {'boards': boards, 'circuits': circuits}


@bp.route('/api/demo/layout', methods=['POST'])
def lay_out():
    if not demo_on():
        return jsonify({'error': 'Turn on the demo data plugin first (Settings > Plugins).'}), 409
    return jsonify(seed())


def seed_on_start(app):
    """FLOORBIT_DEMO=1: one switch for a filled-in demo. Never fatal."""
    if os.environ.get('FLOORBIT_DEMO', '').strip().lower() not in ('1', 'true', 'yes', 'on'):
        return
    with app.app_context():
        try:
            result = seed()
            print(f"[demo] {result}")
        except Exception as exc:  # noqa: BLE001  # a demo hiccup must not stop the app
            print(f"[demo] could not lay out the demo hall: {exc}")
        stats = app.extensions.get('floorbit_stats')
        if stats is not None:
            stats.backfill(demo_history())
        from .flows import init_demo_flows
        init_demo_flows(app)


def demo_history(now=None, step=120):
    """A made-up last day for the stats dashboard: quiet at night, busy in the evening."""
    import math
    import time
    now = time.time() if now is None else now
    out = []
    for k in range(24 * 3600 // step, 0, -1):
        t = now - k * step
        hour = time.localtime(t).tm_hour + time.localtime(t).tm_min / 60
        busy = 0.15 + 0.85 * max(0.0, math.sin((hour - 9) / 24 * 2 * math.pi)) ** 2
        jitter = 0.9 + 0.2 * math.sin(t / 700) * math.cos(t / 1900)
        online = round(70 + 15 * busy)
        down = 3.3e9 * (0.55 + 0.45 * busy) * jitter   # about what the live demo hall sends
        out.append({'t': t, 'down': round(down), 'up': round(down * 0.14), 'online': online,
                    'ports_up': online + 12, 'ports_down': 96 - online, 'ports_errors': 0})
    return out
