"""The machines in the hall from the telemetry picture: each MAC on the access port it is plugged
into, with the IPs ARP gives it. Fed to floorbit/endpoints.py every minute (on the agent: sent to
the hosted Floorbit as the telemetry plugin's ``endpoints``).

ARP lives on the core (Nexus) and MAC tables on the access switches: a MAC's port is the one that
learned it and isn't an uplink (an LLDP/CDP neighbour, or more than ``EDGE_PORT_MACS`` MACs:
floorbit/edge_ports.py), the port with the fewest MACs when several are left.
"""
from ..edge_ports import EDGE_PORT_MACS
from . import state as state_mod


def uplinks(dev, most):
    """Port keys that lead to other switches, and the MAC count per port."""
    counts = {}
    for port, _seen in dev.fdb.values():
        counts[port] = counts.get(port, 0) + 1
    ups = {p for p, n in counts.items() if n > most}
    ups |= {row['local'] for row, _ in dev.cdp.values()}
    for row, _ in dev.lldp.values():
        ups.add(row['local'])            # often the ifIndex
        name = dev.lldp_local.get(row['local'])
        if name:
            ups.update(k for k, i in dev.interfaces.items() if i.name == name)
    return ups, counts


def sightings(st=None, exclude=()):
    """``[{mac, ip, device, port, vlan}]``: one per MAC and IP. A MAC only in ARP (a firewall, a
    server behind a router) comes with the device that has the ARP entry and no port."""
    st = st or state_mod.state
    excludes = [str(x).strip().lower() for x in exclude or () if str(x).strip()]
    best = {}
    ips = {}
    with st._lock:
        for dev in st.devices.values():
            for ip, (mac, _port, _seen) in dev.arp.items():
                ips.setdefault(mac, {}).setdefault(ip, dev.name)
            if not dev.fdb:
                continue
            ups, counts = uplinks(dev, EDGE_PORT_MACS)
            for (mac, vlan), (port, _seen) in dev.fdb.items():
                name = dev.port_name(port)
                if not name or port in ups or any(x in name.lower() for x in excludes):
                    continue
                rank = (counts.get(port, 0), dev.name, name)
                if mac not in best or rank < best[mac][0]:
                    best[mac] = (rank, dev.name, name, vlan)
    out = []
    for mac, (_rank, device, port, vlan) in best.items():
        for ip in sorted(ips.get(mac) or ['']):
            out.append({'mac': mac, 'ip': ip, 'device': device, 'port': port, 'vlan': vlan or None})
    for mac, by_ip in ips.items():
        if mac not in best:
            out += [{'mac': mac, 'ip': ip, 'device': device, 'port': '', 'vlan': None} for ip, device in by_ip.items()]
    return out
