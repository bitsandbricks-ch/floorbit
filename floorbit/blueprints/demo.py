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
        save_data(data)
    return {'placed': placed, 'blocks': len(blocks)}


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
