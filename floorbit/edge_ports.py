"""What counts as a seat's access port: one PC (and its VMs) behind it, not a switch (issue #954).

Check-in, the seat walk, the IP/MAC history, the planned lookups and both monitoring sources ask
this one rule, so a port is a seat's port everywhere or nowhere. More MACs than this on one port
means something with its own MACs sits behind it: a desk switch, an access point, an uplink.
"""
EDGE_PORT_MACS = 4


def is_edge(macs_on_port):
    """Whether a port that has learned this many MACs can be one seat's. Unknown (None) counts as
    yes: the monitoring source didn't count, and the uplink rules (LLDP/CDP) have already run."""
    try:
        return int(macs_on_port or 0) <= EDGE_PORT_MACS
    except (TypeError, ValueError):
        return True
