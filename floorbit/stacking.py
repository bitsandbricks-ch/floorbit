"""Which seat block or mark is drawn over which: ``z`` (a whole number, higher on top, 0 by default).

The editor's Bring to front / Send to back set it; every view draws blocks and marks in this order.
"""
Z_MAX = 1_000_000


class StackError(ValueError):
    pass


def z_of(value):
    """``value`` as a z order; raises StackError."""
    if value in (None, ''):
        return 0
    try:
        z = int(value)
    except (TypeError, ValueError):
        raise StackError('z is a whole number') from None
    if not -Z_MAX <= z <= Z_MAX:
        raise StackError('z is a whole number from -1000000 to 1000000')
    return z


def by_z(items):
    """``items`` from the bottom up; the same z keeps the order they were added in."""
    return sorted(items, key=lambda i: i['z'] if isinstance(i.get('z'), int) else 0)
