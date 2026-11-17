"""Telegraf's configuration, made from the targets (targets.py). docs/telemetry.md.

Telegraf runs next to the collector (the local agent, or Floorbit itself when self-hosted) and
sends everything to it as line protocol over HTTP; the collector checks the ingest token, keeps
the latest picture (state.py) and stores the series (storage.py). Only numeric OIDs are asked, so
the image needs no MIB files.

Measurement names here are what state.py reads; change them together.
"""
import json

SNMP_PORT = 161
TRAP_PORT = 1162          # in the container; publish 162/udp to it
MDT_PORT = 57000
GNMI_PORT = {'nxos': 50051, 'iosxe': 9339}

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
ARP_FIELDS = (('mac', '1.3.6.1.2.1.4.22.1.2', False, 'hwaddr'),)
LLDP_FIELDS = (('lldpRemPortId', '1.0.8802.1.1.2.1.4.1.1.7', False, None),
               ('lldpRemPortDesc', '1.0.8802.1.1.2.1.4.1.1.8', False, None),
               ('lldpRemSysName', '1.0.8802.1.1.2.1.4.1.1.9', False, None))
LLDP_LOCAL_FIELDS = (('lldpLocPortId', '1.0.8802.1.1.2.1.3.7.1.3', False, None),
                     ('lldpLocPortDesc', '1.0.8802.1.1.2.1.3.7.1.4', False, None))
CDP_FIELDS = (('cdpCacheDeviceId', '1.3.6.1.4.1.9.9.23.1.2.1.1.6', False, None),
              ('cdpCacheDevicePort', '1.3.6.1.4.1.9.9.23.1.2.1.1.7', False, None))
CISCO_CPU = (('cpu', '1.3.6.1.4.1.9.9.109.1.1.1.1.7', False, None),)          # cpmCPUTotal1minRev
HOST_CPU = (('cpu', '1.3.6.1.2.1.25.3.3.1.2', False, None),)                  # hrProcessorLoad


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
    lines.append(f'  agents = [{q("udp://" + _host(t["address"]) + ":" + str(t.get("port") or SNMP_PORT))}]')
    lines.append(f'  interval = {q(interval)}')
    lines.append('  timeout = "5s"')
    lines.append('  retries = 1')
    lines.append('  agent_host_tag = "agent_host"')
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


def snmp(t, interval='30s', tables_interval='60s'):
    """Polling for one device: ports every ``interval``, tables (ARP, MAC, neighbours) less often."""
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
    if t.get('tables', True):
        lines.append('')
        _snmp_head(lines, t, tables_interval)
        lines.append('  name = "fb_tables"')
        _tags(lines, 'inputs.snmp', t, {'driver': 'snmp'})
        _table(lines, 'fb_arp', ARP_FIELDS)
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
    port = t.get('port') or GNMI_PORT.get(t.get('platform'), 50051)
    lines = ['[[inputs.gnmi]]', f'  addresses = [{q(_host(t["address"]) + ":" + str(port))}]',
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


def render(targets, output_url, token, interval='30s', tables_interval='60s', listen_traps=True, listen_mdt=True):
    """The whole telegraf.conf. ``targets`` with secrets opened (targets.opened)."""
    lines = ['# Made by Floorbit from Settings > Telemetry (docs/telemetry.md). Changes here are',
             '# overwritten: change the devices there instead.', '',
             '[agent]', f'  interval = {q(interval)}', '  round_interval = true', '  flush_interval = "5s"',
             '  metric_buffer_limit = 100000', '  omit_hostname = true', '',
             '[[outputs.http]]', f'  url = {q(output_url)}', '  method = "POST"', '  data_format = "influx"',
             '  content_encoding = "gzip"', '  timeout = "10s"', '  [outputs.http.headers]',
             f'    Authorization = {q("Token " + token)}', '']
    traps = [t for t in targets if 'traps' in t['drivers']]
    mdt = [t for t in targets if 'mdt' in t['drivers']]
    for t in targets:
        if 'snmp' in t['drivers']:
            lines += [*snmp(t, interval, tables_interval), '']
        if 'gnmi' in t['drivers']:
            lines += [*gnmi(t), '']
    if traps and listen_traps:
        lines += ['[[inputs.snmp_trap]]', f'  service_address = {q(f"udp://:{TRAP_PORT}")}', '  timeout = "5s"']
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
        lines += ['[[inputs.cisco_telemetry_mdt]]', '  transport = "grpc"', f'  service_address = {q(f":{MDT_PORT}")}',
                  '  source_field_name = "mdt_source"', '  [inputs.cisco_telemetry_mdt.aliases]',
                  '    fb_mdt_if = "openconfig-interfaces:interfaces/interface/state"',
                  '    fb_mdt_ietf_if = "ietf-interfaces:interfaces-state/interface/statistics"',
                  '    fb_mdt_iosxe_if = "Cisco-IOS-XE-interfaces-oper:interfaces/interface"',
                  '    fb_mdt_nxos_if = "sys/intf"',
                  '    fb_mdt_iosxe_arp = "Cisco-IOS-XE-arp-oper:arp-data/arp-vrf/arp-oper"',
                  '  [inputs.cisco_telemetry_mdt.tags]', '    driver = "mdt"', '']
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
        if t.get('platform') == 'nxos':
            out.append('feature telemetry\ntelemetry\n  destination-group 1\n'
                       f'    ip address {collector} port {MDT_PORT} protocol gRPC encoding GPB\n'
                       '  sensor-group 1\n    data-source YANG\n'
                       '    path openconfig-interfaces:interfaces/interface/state\n'
                       '  subscription 1\n    dst-grp 1\n    snsr-grp 1 sample-interval 10000')
        elif t.get('platform') == 'iosxe':
            out.append('telemetry ietf subscription 101\n encoding encode-kvgpb\n'
                       ' filter xpath /interfaces-ios-xe-oper:interfaces/interface\n stream yang-push\n'
                       ' update-policy periodic 1000\n'
                       f' receiver ip address {collector} {MDT_PORT} protocol grpc-tcp')
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
