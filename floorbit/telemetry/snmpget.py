"""One-off SNMP GETs from the local agent (issue #946, docs/segments.md).

Telegraf polls on a schedule and can't be asked for one value now, so a check-in that needs one
PC's port asks the switches directly: a few GETs, no table walks (issue #947).

- ``mac_of_ip``: IP to MAC from the core's ARP entry (ipNetToMediaPhysAddress.<ifIndex>.<ip>).
- ``port_of_mac``: MAC to the port a switch learned it on (BRIDGE-MIB dot1dTpFdbPort.<mac>, or
  Q-BRIDGE dot1qTpFdbPort.<fdb>.<mac>), then the port's ifIndex (dot1dBasePortIfIndex).

Cisco IOS keeps one bridge per VLAN: SNMPv2c asks it as ``community@vlan``, SNMPv3 in the
``vlan-<id>`` context, the same as Telegraf's table walks (telegraf.py). One request at a time per
switch, a 2 s timeout, no retries: a lookup must never load a switch. Logins are never logged.
"""
import asyncio
import ipaddress
import threading

ARP_MAC = '1.3.6.1.2.1.4.22.1.2'           # ipNetToMediaPhysAddress.<ifIndex>.<a.b.c.d>
FDB_PORT = '1.3.6.1.2.1.17.4.3.1.2'        # dot1dTpFdbPort.<mac as 6 numbers>
QFDB_PORT = '1.3.6.1.2.1.17.7.1.2.2.1.2'   # dot1qTpFdbPort.<fdb id>.<mac as 6 numbers>
BASE_PORT_IFINDEX = '1.3.6.1.2.1.17.1.4.1.2'   # dot1dBasePortIfIndex.<bridge port>
TIMEOUT = 2.0

_locks = {}
_locks_lock = threading.Lock()


class SnmpError(Exception):
    pass


def _lock(address):
    with _locks_lock:
        return _locks.setdefault(address, threading.Lock())


def mac_index(mac):
    """aa:bb:cc:dd:ee:ff as the six numbers an SNMP index uses, or None."""
    from ..sources import normalise_mac
    clean = normalise_mac(mac)
    return '.'.join(str(int(part, 16)) for part in clean.split(':')) if clean else None


def _value(var):
    """A varbind's value: None when the switch has no such entry, bytes as hex, numbers as int."""
    name = type(var).__name__
    if name in ('NoSuchInstance', 'NoSuchObject', 'EndOfMibView', 'Null'):
        return None
    if name == 'OctetString':
        return bytes(var).hex()
    try:
        return int(var)
    except (TypeError, ValueError):
        return str(var)


def _auth(target, vlan):
    from pysnmp.hlapi.v3arch import asyncio as hl
    if str(target.get('snmp_version') or '2c') == '3':
        auth = {'SHA': hl.usmHMACSHAAuthProtocol, 'MD5': hl.usmHMACMD5AuthProtocol,
                'SHA256': hl.usmHMAC192SHA256AuthProtocol}.get(str(target.get('auth_protocol') or 'SHA').upper(),
                                                              hl.usmHMACSHAAuthProtocol)
        priv = {'AES': hl.usmAesCfb128Protocol, 'DES': hl.usmDESPrivProtocol}.get(
            str(target.get('priv_protocol') or 'AES').upper(), hl.usmAesCfb128Protocol)
        user = hl.UsmUserData(str(target.get('sec_name') or target.get('username') or ''),
                              authKey=target.get('auth_password') or None, authProtocol=auth,
                              privKey=target.get('priv_password') or None,
                              privProtocol=priv if target.get('priv_password') else hl.usmNoPrivProtocol)
        return user, hl.ContextData(contextName=f'vlan-{vlan}' if vlan else '')
    community = str(target.get('community') or 'public')
    return hl.CommunityData(f'{community}@{vlan}' if vlan else community, mpModel=1), hl.ContextData()


async def _get_async(target, oids, vlan, timeout):
    from pysnmp.hlapi.v3arch import asyncio as hl
    auth, context = _auth(target, vlan)
    address = str(target.get('address') or '')
    transport = await hl.UdpTransportTarget.create((address, int(target.get('snmp_port') or 161)),
                                                    timeout=timeout, retries=0)
    engine = hl.SnmpEngine()
    try:
        error, status, _index, binds = await hl.get_cmd(
            engine, auth, transport, context, *[hl.ObjectType(hl.ObjectIdentity(o)) for o in oids])
    finally:
        engine.close_dispatcher()
    if error:
        raise SnmpError(f'{target.get("name") or address}: {error}')
    if status:
        raise SnmpError(f'{target.get("name") or address}: {status.prettyPrint()}')
    return {str(name): _value(value) for name, value in binds}


def get(target, oids, vlan=None, timeout=TIMEOUT):
    """{oid: value} for ``oids`` on ``target`` (a telemetry target: address, community or v3 login,
    snmp_version). One request in flight per switch."""
    with _lock(str(target.get('address'))):
        return asyncio.run(_get_async(target, list(oids), vlan, timeout))


def mac_of_ip(core, if_index, ip, get=get):
    """The MAC the core's ARP entry gives ``ip`` on the VLAN interface ``if_index``, or None."""
    try:
        address = str(ipaddress.IPv4Address(str(ip)))
    except ValueError:
        return None
    oid = f'{ARP_MAC}.{int(if_index)}.{address}'
    value = get(core, [oid]).get(oid)
    from ..sources import normalise_mac
    return normalise_mac(value) if isinstance(value, str) else None


def port_of_mac(switch, mac, vlan, get=get):
    """The ifIndex of the port ``switch`` learned ``mac`` on in ``vlan``, or None when it doesn't
    know the MAC. Q-BRIDGE switches (``fdb: qbridge``) answer in one table for every VLAN."""
    index = mac_index(mac)
    if not index:
        return None
    if switch.get('fdb') == 'qbridge':
        oid = f'{QFDB_PORT}.{int(vlan)}.{index}'
        port = get(switch, [oid]).get(oid)
    else:
        oid = f'{FDB_PORT}.{index}'
        port = get(switch, [oid], vlan=vlan if switch.get('fdb', 'cisco_vlans') == 'cisco_vlans' else None).get(oid)
    if not isinstance(port, int) or port <= 0:
        return None
    oid = f'{BASE_PORT_IFINDEX}.{port}'
    if_index = get(switch, [oid], vlan=vlan if switch.get('fdb', 'cisco_vlans') == 'cisco_vlans' else None).get(oid)
    return if_index if isinstance(if_index, int) and if_index > 0 else None
