"""Telegraf's configuration, made from the targets (targets.py). docs/telemetry.md.

Telegraf runs next to the collector (the local agent, or Floorbit itself when self-hosted) and
sends everything to it as line protocol over HTTP; the collector checks the ingest token, keeps
the latest picture (state.py) and stores the series (storage.py). Only numeric OIDs are asked, so
the image needs no MIB files.

Measurement names here are what state.py reads; change them together.
"""
import json
import os

SNMP_PORT = 161
TRAP_PORT = 1162          # in the container; publish 162/udp to it
MDT_PORT = 57000
MDT_CERT_ENV = 'FLOORBIT_TELEGRAF_MDT_CERT'     # paths as Telegraf sees them
MDT_KEY_ENV = 'FLOORBIT_TELEGRAF_MDT_KEY'
MDT_CA_ENV = 'FLOORBIT_TELEGRAF_MDT_CA'        # only devices with a certificate from this CA
GNMI_PORT = {'nxos': 50051, 'iosxe': 9339}
# A port per way of asking (SNMP on 1161 doesn't send gNMI there too); none set: the usual one.
PORT_KINDS = ('snmp', 'gnmi', 'api')


def port(t, kind):
    """The device's port for ``kind`` (PORT_KINDS), or None for the usual one."""
    value = (t.get('ports') or {}).get(kind)
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535 else None

# IF-MIB and friends, as (field name, OID, is_tag, conversion).
IF_FIELDS = (
    ('ifName', '1.3.6.1.2.1.31.1.1.1.1', True, None),
    ('ifAlias', '1.3.6.1.2.1.31.1.1.1.18', False, None),
    ('ifOperStatus', '1.3.6.1.2.1.2.2.1.8', False, None),
    ('ifAdminStatus', '1.3.6.1.2.1.2.2.1.7', False, None),
    ('ifHighSpeed', '1.3.6.1.2.1.31.1.1.1.15', False, None),
    ('ifHCInOctets', '1.3.6.1.2.1.31.1.1.1.6', False, None),
    ('ifHCOutOctets', '1.3.6.1.2.1.31.1.1.1.10', False, None),
    ('ifInErrors', '1.3.6.1.2.1.2.2.1.14', False, None),
    ('ifOutErrors', '1.3.6.1.2.1.2.2.1.20', False, None),
    ('ifLastChange', '1.3.6.1.2.1.2.2.1.9', False, None),
)
DUPLEX_FIELDS = (('dot3StatsDuplexStatus', '1.3.6.1.2.1.10.7.2.1.19', False, None),)
BRIDGE_FIELDS = (('ifIndex', '1.3.6.1.2.1.17.1.4.1.2', False, None),)
FDB_FIELDS = (('dot1dTpFdbPort', '1.3.6.1.2.1.17.4.3.1.2', False, None),
              ('dot1dTpFdbStatus', '1.3.6.1.2.1.17.4.3.1.3', False, None))
QFDB_FIELDS = (('dot1qTpFdbPort', '1.3.6.1.2.1.17.7.1.2.2.1.2', False, None),
               ('dot1qTpFdbStatus', '1.3.6.1.2.1.17.7.1.2.2.1.3', False, None))
# hex, not hwaddr (deprecated) or displayhint (needs the MIBs the agent image doesn't have):
# normalise_mac turns 021ab00a0014 into a MAC.
ARP_FIELDS = (('mac', '1.3.6.1.2.1.4.22.1.2', False, 'hex'),)
LLDP_FIELDS = (('lldpRemPortId', '1.0.8802.1.1.2.1.4.1.1.7', False, None),
               ('lldpRemPortDesc', '1.0.8802.1.1.2.1.4.1.1.8', False, None),
               ('lldpRemSysName', '1.0.8802.1.1.2.1.4.1.1.9', False, None))
LLDP_LOCAL_FIELDS = (('lldpLocPortId', '1.0.8802.1.1.2.1.3.7.1.3', False, None),
                     ('lldpLocPortDesc', '1.0.8802.1.1.2.1.3.7.1.4', False, None))
CDP_FIELDS = (('cdpCacheDeviceId', '1.3.6.1.4.1.9.9.23.1.2.1.1.6', False, None),
              ('cdpCacheDevicePort', '1.3.6.1.4.1.9.9.23.1.2.1.1.7', False, None))
CISCO_CPU = (('cpu', '1.3.6.1.4.1.9.9.109.1.1.1.1.7', False, None),)          # cpmCPUTotal1minRev
HOST_CPU = (('cpu', '1.3.6.1.2.1.25.3.3.1.2', False, None),)                  # hrProcessorLoad
# CISCO-MEMORY-POOL-MIB: the processor pool's use (mem %) and, used + free, how much there is.
CISCO_MEM = (('memUsed', '1.3.6.1.4.1.9.9.48.1.1.1.5', False, None),
             ('memFree', '1.3.6.1.4.1.9.9.48.1.1.1.6', False, None))
# What a device is, for discovery (floorbit/inventory_discovery.py): asked every few minutes.
FACT_FIELDS = (('sysDescr', '1.3.6.1.2.1.1.1.0'), ('sysLocation', '1.3.6.1.2.1.1.6.0'),
               ('hrMemorySize', '1.3.6.1.2.1.25.2.2.0'))                      # kilobytes
ENTITY_FIELDS = (('entPhysicalDescr', '1.3.6.1.2.1.47.1.1.1.1.2', False, None),
                 ('entPhysicalContainedIn', '1.3.6.1.2.1.47.1.1.1.1.4', False, None),
                 ('entPhysicalClass', '1.3.6.1.2.1.47.1.1.1.1.5', False, None),   # 3: the chassis
                 ('entPhysicalName', '1.3.6.1.2.1.47.1.1.1.1.7', False, None),
                 ('entPhysicalSoftwareRev', '1.3.6.1.2.1.47.1.1.1.1.10', False, None),
                 ('entPhysicalSerialNum', '1.3.6.1.2.1.47.1.1.1.1.11', False, None),
                 ('entPhysicalModelName', '1.3.6.1.2.1.47.1.1.1.1.13', False, None))
# Which interface an ENTITY-MIB row is (index entPhysicalIndex.logical, value ifIndex's OID): an
# optic's port.
ENT_ALIAS_FIELDS = (('entAliasMappingIdentifier', '1.3.6.1.2.1.47.1.3.2.1.2', False, None),)
STORAGE_FIELDS = (('hrStorageType', '1.3.6.1.2.1.25.2.3.1.2', False, None),       # RAM, fixed disk, ...
                  ('hrStorageAllocationUnits', '1.3.6.1.2.1.25.2.3.1.4', False, None),
                  ('hrStorageSize', '1.3.6.1.2.1.25.2.3.1.5', False, None))
# Per interface and per device, for discovery too: MAC, IPv4 addresses, VLANs, access or trunk.
IF_MAC_FIELDS = (('ifPhysAddress', '1.3.6.1.2.1.2.2.1.6', False, 'hwaddr'),)
IP_FIELDS = (('ipAdEntIfIndex', '1.3.6.1.2.1.4.20.1.2', False, None),             # index: the address
             ('ipAdEntNetMask', '1.3.6.1.2.1.4.20.1.3', False, None))
QVLAN_FIELDS = (('dot1qVlanStaticName', '1.3.6.1.2.1.17.7.1.4.3.1.1', False, None),)   # index: VLAN
PVID_FIELDS = (('dot1qPvid', '1.3.6.1.2.1.17.7.1.4.5.1.1', False, None),)             # index: bridge port
VTP_FIELDS = (('vtpVlanName', '1.3.6.1.4.1.9.9.46.1.3.1.1.4', False, None),)          # index: domain.VLAN
CISCO_IF_VLAN = (('vmVlan', '1.3.6.1.4.1.9.9.68.1.2.2.1.2', False, None),             # access VLAN
                 ('vlanTrunkPortDynamicStatus', '1.3.6.1.4.1.9.9.46.1.6.1.1.14', False, None))   # 1: trunking
# POWER-ETHERNET-MIB (RFC 3621), index group.port: PoE per port and each power supply's budget.
POE_FIELDS = (('pethPsePortAdminEnable', '1.3.6.1.2.1.105.1.1.1.3', False, None),        # 1: on
              ('pethPsePortDetectionStatus', '1.3.6.1.2.1.105.1.1.1.6', False, None),    # 3: delivering
              ('pethPsePortPowerClassifications', '1.3.6.1.2.1.105.1.1.1.10', False, None))   # 1-5: class 0-4
# CISCO-POWER-ETHERNET-EXT-MIB extends the same rows: the draw, and the ENTITY-MIB row of the port.
CISCO_POE = (('cpeExtPsePortPwrAllocated', '1.3.6.1.4.1.9.9.402.1.2.1.7', False, None),        # mW
             ('cpeExtPsePortPwrConsumption', '1.3.6.1.4.1.9.9.402.1.2.1.9', False, None),      # mW
             ('cpeExtPsePortEntPhyIndex', '1.3.6.1.4.1.9.9.402.1.2.1.11', False, None))
PSE_FIELDS = (('pethMainPsePower', '1.3.6.1.2.1.105.1.3.1.1.2', False, None),                  # W
              ('pethMainPseOperStatus', '1.3.6.1.2.1.105.1.3.1.1.3', False, None),             # 1: on
              ('pethMainPseConsumptionPower', '1.3.6.1.2.1.105.1.3.1.1.4', False, None))       # W
HR_DEVICE_FIELDS = (('hrDeviceType', '1.3.6.1.2.1.25.3.2.1.2', False, None),      # processors: the CPU
                    ('hrDeviceDescr', '1.3.6.1.2.1.25.3.2.1.3', False, None))


def q(value):
    """A TOML basic string: names and secrets come from the settings page."""
    return json.dumps(str(value), ensure_ascii=False)


def _tags(lines, prefix, target, extra=None):
    lines.append(f'  [{prefix}.tags]')
    tags = {'device': target['name'], 'address': target['address'], 'driver': extra.pop('driver'),
            'kind': target.get('kind') or 'switch', **(extra or {})}
    for key, value in tags.items():
        if value:
            lines.append(f'    {key} = {q(value)}')


def _table(lines, name, fields):
    lines.append('  [[inputs.snmp.table]]')
    lines.append(f'    name = {q(name)}')
    lines.append('    index_as_tag = true')
    for field, oid, is_tag, conversion in fields:
        lines.append('    [[inputs.snmp.table.field]]')
        lines.append(f'      name = {q(field)}')
        lines.append(f'      oid = {q(oid)}')
        if is_tag:
            lines.append('      is_tag = true')
        if conversion:
            lines.append(f'      conversion = {q(conversion)}')


def _snmp_head(lines, t, interval, community=None, context=None):
    lines.append('[[inputs.snmp]]')
    # Telegraf's log names the input by its alias: the agent tells each device's errors apart.
    lines.append(f'  alias = {q(t["name"])}')
    lines.append(f'  agents = [{q("udp://" + _host(t["address"]) + ":" + str(port(t, "snmp") or SNMP_PORT))}]')
    lines.append(f'  interval = {q(interval)}')
    lines.append('  timeout = "5s"')
    lines.append('  retries = 1')
    # "source", as Telegraf 2.0 wants it; state.py reads either.
    lines.append('  agent_host_tag = "source"')
    if t.get('snmp_version') == '3':
        lines.append('  version = 3')
        lines.append(f'  sec_name = {q(t.get("sec_name") or t.get("username") or "")}')
        level = 'authPriv' if t.get('priv_password') else 'authNoPriv' if t.get('auth_password') else 'noAuthNoPriv'
        lines.append(f'  sec_level = {q(level)}')
        if t.get('auth_password'):
            lines.append(f'  auth_protocol = {q(t.get("auth_protocol") or "SHA")}')
            lines.append(f'  auth_password = {q(t["auth_password"])}')
        if t.get('priv_password'):
            lines.append(f'  priv_protocol = {q(t.get("priv_protocol") or "AES")}')
            lines.append(f'  priv_password = {q(t["priv_password"])}')
        if context:
            lines.append(f'  context_name = {q(context)}')
    else:
        lines.append('  version = 2')
        lines.append(f'  community = {q(community or t.get("community") or "public")}')


def _host(address):
    return f'[{address}]' if ':' in address else address


def snmp(t, interval='30s', tables_interval='60s', facts_interval='300s'):
    """Polling for one device: ports every ``interval``, tables (ARP, MAC, neighbours) less often,
    and what the device is (model, serial, software, memory, disks) every ``facts_interval``."""
    lines = []
    cisco = t.get('platform') in ('nxos', 'iosxe', 'ios')
    _snmp_head(lines, t, interval)
    lines.append('  name = "fb_system"')
    for field, oid in (('sysName', '1.3.6.1.2.1.1.5.0'), ('sysUpTime', '1.3.6.1.2.1.1.3.0')):
        lines += ['  [[inputs.snmp.field]]', f'    name = {q(field)}', f'    oid = {q(oid)}']
    _tags(lines, 'inputs.snmp', t, {'driver': 'snmp'})
    _table(lines, 'fb_if', IF_FIELDS)
    _table(lines, 'fb_if', DUPLEX_FIELDS)
    _table(lines, 'fb_cpu', CISCO_CPU if cisco else HOST_CPU)
    if cisco:
        _table(lines, 'fb_mem', CISCO_MEM)
    lines.append('')
    _snmp_head(lines, t, facts_interval)
    lines.append('  name = "fb_facts"')
    for field, oid in FACT_FIELDS:
        lines += ['  [[inputs.snmp.field]]', f'    name = {q(field)}', f'    oid = {q(oid)}']
    _tags(lines, 'inputs.snmp', t, {'driver': 'snmp'})
    _table(lines, 'fb_entity', ENTITY_FIELDS)
    _table(lines, 'fb_entalias', ENT_ALIAS_FIELDS)
    _table(lines, 'fb_ifmac', IF_MAC_FIELDS)
    _table(lines, 'fb_ip', IP_FIELDS)
    if cisco:
        _table(lines, 'fb_vtp', VTP_FIELDS)
        _table(lines, 'fb_ifvlan', CISCO_IF_VLAN)
    else:
        _table(lines, 'fb_storage', STORAGE_FIELDS)
        _table(lines, 'fb_hrdevice', HR_DEVICE_FIELDS)
        _table(lines, 'fb_qvlan', QVLAN_FIELDS)
        _table(lines, 'fb_bridge', BRIDGE_FIELDS)
        _table(lines, 'fb_pvid', PVID_FIELDS)
    if t.get('tables', True):
        lines.append('')
        _snmp_head(lines, t, tables_interval)
        lines.append('  name = "fb_tables"')
        _tags(lines, 'inputs.snmp', t, {'driver': 'snmp'})
        _table(lines, 'fb_arp', ARP_FIELDS)
        if t.get('kind', 'switch') == 'switch':
            _table(lines, 'fb_poe', POE_FIELDS)
            if cisco:
                _table(lines, 'fb_poe', CISCO_POE)
            _table(lines, 'fb_pse', PSE_FIELDS)
        _table(lines, 'fb_lldp', LLDP_FIELDS)
        _table(lines, 'fb_lldp_loc', LLDP_LOCAL_FIELDS)
        if cisco:
            _table(lines, 'fb_cdp', CDP_FIELDS)
        if t.get('fdb') in ('qbridge', 'bridge'):
            _table(lines, 'fb_bridge', BRIDGE_FIELDS)
            _table(lines, 'fb_qfdb' if t['fdb'] == 'qbridge' else 'fb_fdb',
                   QFDB_FIELDS if t['fdb'] == 'qbridge' else FDB_FIELDS)
        if t.get('fdb') == 'cisco_vlans':
            # Catalyst IOS keeps one bridge per VLAN and answers it under community@vlan (v2c)
            # or the vlan-<id> context (v3): one poll per VLAN.
            for vlan in t.get('vlans') or [1]:
                lines.append('')
                community = f'{t.get("community") or "public"}@{vlan}'
                _snmp_head(lines, t, tables_interval, community=community, context=f'vlan-{vlan}')
                lines.append('  name = "fb_vlan"')
                _tags(lines, 'inputs.snmp', t, {'driver': 'snmp', 'vlan': str(vlan)})
                _table(lines, 'fb_bridge', BRIDGE_FIELDS)
                _table(lines, 'fb_fdb', FDB_FIELDS)
    return lines


def gnmi(t, interval='10s'):
    at = port(t, 'gnmi') or GNMI_PORT.get(t.get('platform'), 50051)
    lines = ['[[inputs.gnmi]]', f'  alias = {q(t["name"])}',
             f'  addresses = [{q(_host(t["address"]) + ":" + str(at))}]',
             f'  username = {q(t.get("username") or "")}', f'  password = {q(t.get("password") or "")}',
             f'  encoding = {q("json_ietf" if t.get("platform") == "iosxe" else "json")}',
             '  redial = "10s"', '  tls_enable = true',
             f'  insecure_skip_verify = {"false" if t.get("verify_tls", True) else "true"}']
    _tags(lines, 'inputs.gnmi', t, {'driver': 'gnmi'})
    for name, path, mode in (('fb_gnmi_if', '/interfaces/interface/state', 'sample'),
                             ('fb_gnmi_if', '/interfaces/interface/state/oper-status', 'on_change')):
        lines += ['  [[inputs.gnmi.subscription]]', f'    name = {q(name)}', '    origin = "openconfig"',
                  f'    path = {q(path)}', f'    subscription_mode = {q(mode)}']
        if mode == 'sample':
            lines.append(f'    sample_interval = {q(interval)}')
    return lines


def render(targets, output_url, token, interval='30s', tables_interval='60s', listen_traps=True, listen_mdt=True,
           output_insecure=False, poll=True):
    """The whole telegraf.conf. ``targets`` with secrets opened (targets.opened). ``poll=False``
    (a standby agent): only the listeners, so a device is never polled by two agents."""
    lines = ['# Made by Floorbit from the inventory (docs/telemetry.md). Changes here are',
             '# overwritten: change the devices there instead.', '',
             '[agent]', f'  interval = {q(interval)}', '  round_interval = true', '  flush_interval = "5s"',
             '  metric_buffer_limit = 100000', '  omit_hostname = true',
             # gosmi: Telegraf's own MIB reader. The default (netsnmp) runs net-snmp's snmptranslate
             # for every trap and drops the trap when it can't name an OID, and the agent image has
             # neither it nor the MIB files. Every OID here is numeric, so polling doesn't change.
             '  snmp_translator = "gosmi"',
             # Said out loud, so Telegraf 1.40 doesn't warn about its coming default (no aggregators here).
             '  skip_processors_after_aggregators = false', '',
             '[[outputs.http]]', f'  url = {q(output_url)}', '  method = "POST"', '  data_format = "influx"',
             # No gzip: with it Telegraf sends the body in chunks without a length, which older agents
             # dropped (a broken pipe in Telegraf's log). The agent is on the same host or LAN anyway.
             '  timeout = "10s"',
             *(['  insecure_skip_verify = true'] if output_insecure else []), '  [outputs.http.headers]',
             f'    Authorization = {q("Token " + token)}', '']
    traps = [t for t in targets if 'traps' in t['drivers']]
    mdt = [t for t in targets if 'mdt' in t['drivers']]
    # A standby agent still polls the devices given to it by name (targets.for_agent).
    for t in [t for t in targets if poll or t.get('mine')]:
        if 'snmp' in t['drivers']:
            lines += [*snmp(t, interval, tables_interval), '']
        if 'gnmi' in t['drivers']:
            lines += [*gnmi(t), '']
    if traps and listen_traps:
        lines += ['[[inputs.snmp_trap]]', '  alias = "traps"', f'  service_address = {q(f"udp://:{TRAP_PORT}")}',
                  '  timeout = "5s"']
        v3 = next((t for t in traps if t.get('snmp_version') == '3'), None)
        if v3:
            lines += ['  version = "3"', f'  sec_name = {q(v3.get("sec_name") or v3.get("username") or "")}',
                      f'  sec_level = {q("authPriv" if v3.get("priv_password") else "authNoPriv")}',
                      f'  auth_protocol = {q(v3.get("auth_protocol") or "SHA")}',
                      f'  auth_password = {q(v3.get("auth_password") or "")}']
            if v3.get('priv_password'):
                lines += [f'  priv_protocol = {q(v3.get("priv_protocol") or "AES")}',
                          f'  priv_password = {q(v3["priv_password"])}']
        lines += ['  [inputs.snmp_trap.tags]', '    driver = "traps"', '']
    if mdt and listen_mdt:
        lines += ['[[inputs.cisco_telemetry_mdt]]', '  alias = "mdt"', '  transport = "grpc"',
                  f'  service_address = {q(f":{MDT_PORT}")}',
                  '  source_field_name = "mdt_source"']
        cert, key = os.environ.get(MDT_CERT_ENV), os.environ.get(MDT_KEY_ENV)
        if cert and key:
            # Plain gRPC lets anyone on the management network send counters: with a certificate
            # Telegraf takes MDT over TLS only (the devices dial out with "protocol grpc-tls").
            lines += [f'  tls_cert = {q(cert)}', f'  tls_key = {q(key)}']
            ca = os.environ.get(MDT_CA_ENV)
            if ca:
                lines.append(f'  tls_allowed_cacerts = [{q(ca)}]')
        lines += ['  [inputs.cisco_telemetry_mdt.aliases]',
                  '    fb_mdt_if = "openconfig-interfaces:interfaces/interface/state"',
                  '    fb_mdt_ietf_if = "ietf-interfaces:interfaces-state/interface/statistics"',
                  '    fb_mdt_iosxe_if = "Cisco-IOS-XE-interfaces-oper:interfaces/interface"',
                  '    fb_mdt_nxos_if = "sys/intf"',
                  '    fb_mdt_iosxe_arp = "Cisco-IOS-XE-arp-oper:arp-data/arp-vrf/arp-oper"',
                  '  [inputs.cisco_telemetry_mdt.tags]', '    driver = "mdt"', '']
    if not any(line.startswith('[[inputs.') for line in lines):
        # Telegraf won't start without an input: one that never sends anything keeps it waiting.
        lines += ['[[inputs.internal]]', '  collect_memstats = false', '  namedrop = ["*"]', '']
    return '\n'.join(lines) + '\n'


def device_config(t, collector):
    """What to paste on the device so it sends to the collector (``collector``: its address as the
    device reaches it). Shown on the settings page; secrets are left as placeholders."""
    out = []
    if 'traps' in t['drivers']:
        if t.get('platform') == 'nxos':
            out.append(f'snmp-server host {collector} traps version 2c <community> udp-port 162\n'
                       'snmp-server enable traps link')
        elif t.get('platform') in ('ios', 'iosxe'):
            out.append('snmp-server enable traps snmp linkdown linkup\n'
                       f'snmp-server host {collector} version 2c <community>')
    if 'mdt' in t['drivers']:
        tls = bool(os.environ.get(MDT_CERT_ENV) and os.environ.get(MDT_KEY_ENV))
        if t.get('platform') == 'nxos':
            out.append('feature telemetry\ntelemetry\n  destination-group 1\n'
                       f'    ip address {collector} port {MDT_PORT} protocol gRPC encoding GPB\n'
                       + ('    certificate <collector-ca.pem> <collector name>\n' if tls else '')
                       +
                       '  sensor-group 1\n    data-source YANG\n'
                       '    path openconfig-interfaces:interfaces/interface/state\n'
                       '  subscription 1\n    dst-grp 1\n    snsr-grp 1 sample-interval 10000')
        elif t.get('platform') == 'iosxe':
            out.append('telemetry ietf subscription 101\n encoding encode-kvgpb\n'
                       ' filter xpath /interfaces-ios-xe-oper:interfaces/interface\n stream yang-push\n'
                       ' update-policy periodic 1000\n'
                       f' receiver ip address {collector} {MDT_PORT} protocol '
                       + ('grpc-tls profile <trustpoint>' if tls else 'grpc-tcp'))
    if 'gnmi' in t['drivers']:
        if t.get('platform') == 'nxos':
            out.append('feature grpc\ngrpc port 50051\ngrpc certificate <trustpoint>\nfeature openconfig')
        elif t.get('platform') == 'iosxe':
            out.append('gnxi\ngnxi secure-server\ngnxi secure-trustpoint <trustpoint>\ngnxi secure-port 9339')
    if 'nxapi' in t['drivers']:
        out.append('feature nxapi\nnxapi https port 443')
    if 'restconf' in t['drivers']:
        out.append('ip http secure-server\nrestconf')
    return '\n!\n'.join(out)
