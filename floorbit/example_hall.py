"""An example hall to start from (Mike's hall plan): rows in pairs with a letter each, a standing
row along the side, walls, exits, toilets, showers, the bar and a side events area.

It is a new hall next to the ones there are, so nothing is replaced. The rows start at the first
letter no seat uses yet, so its seats never clash with the plan's.
"""
from . import halls, plan_marks, seat_names
from .blueprints.seat_blocks import make_block

NAME = 'Example hall'
PAIRS, SEATS = 8, 24          # 8 pairs of rows of 24 seats: 384 seats, plus a standing row of 16


def next_row(data):
    """The first row letter after every seat name that starts with letters."""
    nxt = 0
    for b in data.get('seat_blocks') or []:
        for seat in seat_names.seats(b):
            prefix = seat.split('-')[0].upper()
            if seat_names.LETTERS_RE.match(prefix):
                nxt = max(nxt, seat_names.letter_index(prefix) + 1)
    return nxt


def _marks():
    m = []
    wall = lambda x, y, x2, y2, style='solid': m.append(  # noqa: E731
        {'kind': 'wall', 'x': x, 'y': y, 'x2': x2, 'y2': y2, 'style': style})
    # The outer walls, with a gap for the entrance at the bottom.
    wall(4, 4, 96, 4)
    wall(4, 4, 4, 96)
    wall(96, 4, 96, 96)
    wall(4, 96, 44, 96)
    wall(56, 96, 96, 96)
    # The side events area on the left, behind a fence.
    wall(22, 60, 22, 96, 'dashed')
    wall(4, 60, 22, 60, 'dashed')
    m += [
        {'kind': 'zone', 'x': 5, 'y': 61, 'w': 16, 'h': 34, 'label': 'Side events', 'color': 'trace'},
        {'kind': 'zone', 'x': 80, 'y': 80, 'w': 15, 'h': 15, 'label': 'Bar', 'color': 'warn'},
        {'kind': 'zone', 'x': 80, 'y': 5, 'w': 15, 'h': 12, 'label': 'Crew', 'color': 'bit'},
        {'kind': 'text', 'x': 50, 'y': 7, 'text': NAME, 'size': 'l'},
        {'kind': 'text', 'x': 50, 'y': 99, 'text': 'Entrance', 'size': 's'},
        {'kind': 'icon', 'x': 46, 'y': 96, 'icon': 'arrow-up'},
        {'kind': 'icon', 'x': 54, 'y': 96, 'icon': 'arrow-up'},
        {'kind': 'icon', 'x': 4, 'y': 30, 'icon': 'exit'},
        {'kind': 'icon', 'x': 96, 'y': 45, 'icon': 'exit'},
        {'kind': 'icon', 'x': 96, 'y': 60, 'icon': 'wc'},
        {'kind': 'icon', 'x': 96, 'y': 66, 'icon': 'shower'},
        {'kind': 'icon', 'x': 87.5, 'y': 89, 'icon': 'bar'},
        {'kind': 'icon', 'x': 87.5, 'y': 13, 'icon': 'first-aid'},
        {'kind': 'icon', 'x': 60, 'y': 92, 'icon': 'info'},
        {'kind': 'icon', 'x': 13, 'y': 85, 'icon': 'games'},
    ]
    return m


def add(data):
    """Adds the example hall to ``data`` and returns it (as ``halls.public``)."""
    hall = halls.create(data, _free_name(data))
    start = next_row(data)
    blocks = []
    for i in range(PAIRS):
        blocks.append(make_block({'x': 52, 'y': 14 + i * 9.5, 'cols': SEATS, 'rows': 2, 'naming': 'rows',
                                  'row_start': seat_names.row_letter(start + 2 * i)}, hall['id']))
    # A standing row along the side events fence, read from the top.
    blocks.append(make_block({'x': 14, 'y': 31, 'cols': 14, 'rows': 1, 'rotation': 90, 'naming': 'rows',
                              'row_start': seat_names.row_letter(start + 2 * PAIRS)}, hall['id']))
    data.setdefault('seat_blocks', []).extend(blocks)
    for mark in _marks():
        plan_marks.add(data, {**mark, 'hall_id': hall['id']})
    return halls.public(data, hall)


def _free_name(data):
    taken = {h['name'] for h in halls.halls(data)}
    n, name = 1, NAME
    while name in taken:
        n += 1
        name = f'{NAME} {n}'
    return name
