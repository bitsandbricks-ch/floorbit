"""Traffic insights from NetFlow and IPFIX (issue #25). See docs/flows.md.

The collector (``python -m floorbit.flows``, its own optional container) listens for flow packets,
keeps aggregates only (``aggregate.py``) and publishes a summary to Redis, where the app's
``/api/flows`` reads it. Installs without NetFlow don't run it and see an empty page.
"""
from integrations import seat_sources

from ..power import block_rows
from ..store import load_data


def seat_maps():
    """({ip: seat}, {seat: area}) from the seat sources and the seat blocks on the floor plan."""
    seat_of = {}
    for seat, info in (seat_sources.load() or {}).items():
        ip = (info or {}).get('ip_address')
        if ip:
            seat_of[str(ip)] = seat
    area_of = {}
    for block in load_data().get('seat_blocks') or []:
        for row in block_rows(block):
            for seat in row:
                area_of[seat] = block.get('name') or block['id']
    return seat_of, area_of
