"""Whether a switch port leads to more than one seat, so a port action would cut a whole switch (#886).

Shutting or bouncing a seat's port takes one player offline. The same click on a switch's uplink
takes every seat behind it offline, so the port actions refuse it and the Security page offers
"Open the switch" instead. A port counts as an uplink when any of these says so:

- a link in the topology ends on it (``floorbit/links.py``);
- LLDP or CDP sees another device on it (the monitoring source's neighbours);
- its name matches the uplink pattern (``STATS_UPLINK_PATTERN``).

Deliberate work on an uplink stays possible in the switch terminal, which is role-gated and logged.
"""
from . import links
from .syslog import canonical_port


def reason(switch, port, data=None):
    """Why ``port`` on ``switch`` is an uplink, as a short code, or None for an edge port.

    ``topology``: a topology link ends on it; ``neighbour``: LLDP/CDP sees a device on it;
    ``pattern``: its name matches the uplink pattern."""
    name = str(switch or '').lower().split('.')[0]
    want = canonical_port(port)
    if not name or not want:
        return None
    for link in links.all_links(data):
        for end in ('a', 'b'):
            if str(link.get(end) or '').lower().split('.')[0] == name \
                    and canonical_port(link.get(f'{end}_port')) == want:
                return 'topology'
    from . import sources
    try:
        seen = sources.monitoring().neighbours(switch) or []
    except Exception:  # noqa: BLE001  # a source that can't answer doesn't make a port an edge or an uplink
        seen = []
    if any(canonical_port(n.get('port')) == want for n in seen if isinstance(n, dict)):
        return 'neighbour'
    from .plugins.helpers import uplink_pattern
    if uplink_pattern().search(str(port)):
        return 'pattern'
    return None
