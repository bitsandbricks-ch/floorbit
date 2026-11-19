"""Discovery: what the poll learns of a device fills its inventory entry; values set by hand stay."""
import time

import pytest

from floorbit import inventory, inventory_discovery, sources
from floorbit.telemetry import telegraf
from floorbit.telemetry.state import State

SW = 'device=sw-a-01,address=192.0.2.10,driver=snmp'
IOS = ('Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M), Version 15.2(7)E8, RELEASE SOFTWARE (fc1)'
       '\\r\\nTechnical Support: http://www.cisco.com/techsupport\\r\\nCopyright (c) 1986-2023 by Cisco Systems, Inc.')


@pytest.mark.parametrize('descr, platform, os_', [
    (IOS, 'Cisco IOS', 'Cisco IOS 15.2(7)E8'),
    ('Cisco NX-OS(tm) n9000, Software (n9000-dk9), Version 9.3(10), RELEASE SOFTWARE', 'Cisco NX-OS',
     'Cisco NX-OS 9.3(10)'),
    ('Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a, RELEASE SOFTWARE',
     'Cisco IOS-XE', 'Cisco IOS-XE 17.9.4a'),
    ('Linux dns-01 6.1.0-18-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.1.76-1 x86_64', 'Linux', 'Linux 6.1.0-18-amd64'),
    ('FreeBSD fw-01.example.org 14.1-RELEASE-p5 FreeBSD 14.1-RELEASE-p5 amd64', 'FreeBSD', 'FreeBSD 14.1-RELEASE-p5'),
    ('Some appliance', '', 'Some appliance'),
])
def test_the_software_from_sys_descr(descr, platform, os_):
    assert inventory_discovery.software(descr) == (platform, os_)


def test_telegraf_asks_what_the_device_is_every_few_minutes():
    t = {'name': 'sw-a-01', 'address': '192.0.2.10', 'platform': 'ios', 'drivers': ['snmp'], 'kind': 'switch'}
    conf = '\n'.join(telegraf.snmp(t))
    facts = conf[conf.index('name = "fb_facts"') - 400:]
    assert 'interval = "300s"' in facts and '"1.3.6.1.2.1.1.1.0"' in facts and '"1.3.6.1.2.1.1.6.0"' in facts
    assert 'fb_entity' in conf and 'fb_mem' in conf and 'fb_storage' not in conf      # a switch: no disks
    server = '\n'.join(telegraf.snmp({**t, 'platform': 'other', 'kind': 'server'}))
    assert 'fb_storage' in server and 'fb_hrdevice' in server and 'fb_mem' not in server


def facts_poll(at=1_700_000_000):
    ns = int(at * 1e9)
    return '\n'.join([
        f'fb_facts,{SW} sysDescr="{IOS}",sysLocation="Hall A\\, rack 3" {ns}',
        f'fb_entity,{SW},index=1001 entPhysicalClass=3i,entPhysicalModelName="WS-C2960X-48FPD-L",'
        f'entPhysicalSerialNum="FOC0000X0AA",entPhysicalSoftwareRev="15.2(7)E8" {ns}',
        f'fb_entity,{SW},index=1002 entPhysicalClass=10i,entPhysicalModelName="GLC-SX-MMD",'
        f'entPhysicalSerialNum="SFP0001" {ns}',
        f'fb_entity,{SW},index=2001 entPhysicalClass=3i,entPhysicalModelName="WS-C2960X-48FPD-L",'
        f'entPhysicalSerialNum="FOC0000X0BB" {ns}',
        f'fb_mem,{SW},index=1 memUsed=268435456i,memFree=268435456i {ns}',
        f'fb_mem,{SW},index=2 memUsed=1000i,memFree=1000i {ns}',
    ])


def test_the_picture_keeps_what_the_device_said():
    st = State()
    st.apply_text(facts_poll())
    dev = st.devices['sw-a-01']
    # The first chassis of a stack; an optic's serial is not the switch's
    assert dev.summary() == {'descr': IOS.replace('\\r\\n', ' '), 'location': 'Hall A, rack 3',
                             'model': 'WS-C2960X-48FPD-L', 'serial': 'FOC0000X0AA', 'software': '15.2(7)E8',
                             'memory_mb': 512}
    assert dev.mem == 50.0


def test_a_server_says_its_cpu_memory_and_disks():
    st = State()
    tags = 'device=hv-01,address=192.0.2.20,driver=snmp,kind=server'
    st.apply_text('\n'.join([
        f'fb_facts,{tags} sysDescr="Linux hv-01 6.8.12-4-pve #1 SMP x86_64",hrMemorySize=263921664i',
        f'fb_storage,{tags},index=1 hrStorageType=".1.3.6.1.2.1.25.2.1.2",hrStorageAllocationUnits=1024i,'
        'hrStorageSize=263921664i',
        f'fb_storage,{tags},index=31 hrStorageType=".1.3.6.1.2.1.25.2.1.4",hrStorageAllocationUnits=4096i,'
        'hrStorageSize=24414062i',
        f'fb_storage,{tags},index=32 hrStorageType=".1.3.6.1.2.1.25.2.1.4",hrStorageAllocationUnits=4096i,'
        'hrStorageSize=97656250i',
        f'fb_storage,{tags},index=40 hrStorageType=".1.3.6.1.2.1.25.2.1.3",hrStorageAllocationUnits=1024i,'
        'hrStorageSize=1000i',
        f'fb_hrdevice,{tags},index=196608 hrDeviceType=".1.3.6.1.2.1.25.3.1.3",'
        'hrDeviceDescr="AuthenticAMD: AMD EPYC 7313 16-Core Processor"',
        f'fb_hrdevice,{tags},index=196609 hrDeviceType=".1.3.6.1.2.1.25.3.1.3",'
        'hrDeviceDescr="AuthenticAMD: AMD EPYC 7313 16-Core Processor"',
        f'fb_hrdevice,{tags},index=1025 hrDeviceType=".1.3.6.1.2.1.25.3.1.4",hrDeviceDescr="network interface eth0"',
    ]))
    facts = st.devices['hv-01'].summary()
    assert facts['memory_mb'] == 257736 and facts['disk_gb'] == 500
    assert facts['cores'] == 2 and facts['cpu'] == 'AMD EPYC 7313 16-Core Processor'
    assert inventory_discovery.fields_of({'facts': facts}) == {
        'platform': 'Linux', 'os': 'Linux 6.8.12-4-pve', 'memory_mb': '257736', 'disk_gb': '500', 'cores': '2',
        'cpu': 'AMD EPYC 7313 16-Core Processor'}


def test_librenms_rows_fill_the_same_fields():
    row = {'hostname': 'sw-a-01', 'hardware': 'WS-C2960X-48FPD-L', 'serial': 'FOC0000X0AA', 'os': 'ios',
           'version': '15.2(7)E8', 'location': 'Hall A'}
    assert inventory_discovery.fields_of(row) == {'model': 'WS-C2960X-48FPD-L', 'serial': 'FOC0000X0AA',
                                                  'platform': 'Cisco IOS', 'os': 'Cisco IOS 15.2(7)E8',
                                                  'location': 'Hall A'}


def test_it_fills_in_and_never_overwrites_what_someone_set():
    dev = inventory.blank(name='sw-a-01', model='', serial='typed-by-hand')
    changed, kept = inventory_discovery.fill(dev, {'model': 'WS-C2960X', 'serial': 'FOC1', 'os': 'Cisco IOS 15.2'})
    assert sorted(changed) == ['model', 'os'] and kept == 1
    assert dev['serial'] == 'typed-by-hand'
    assert dev['fed']['discovery'] == {'model': 'WS-C2960X', 'os': 'Cisco IOS 15.2'}
    # An upgrade: what discovery put there follows the device
    changed, _ = inventory_discovery.fill(dev, {'model': 'WS-C2960X', 'os': 'Cisco IOS 15.2(7)E9'})
    assert changed == ['os'] and dev['os'] == 'Cisco IOS 15.2(7)E9'
    # Changed by hand afterwards: it stays, and discovery lets go of it
    dev['model'] = 'C2960X (spare)'
    changed, kept = inventory_discovery.fill(dev, {'model': 'WS-C2960X', 'os': 'Cisco IOS 15.2(7)E9'})
    assert changed == [] and kept == 1 and dev['model'] == 'C2960X (spare)' and 'model' not in dev['fed']['discovery']
    # Emptied by hand: filled again
    dev['model'] = ''
    assert inventory_discovery.fill(dev, {'model': 'WS-C2960X'})[0] == ['model']
    # A field another plugin locked stays as it is
    dev['locked'] = ['os']
    dev['os'] = ''
    assert inventory_discovery.fill(dev, {'os': 'Cisco IOS 15.2'})[0] == []


class Telemetry(sources.NoMonitoring):
    name = 'telemetry'

    def __init__(self, rows, ports):
        self.rows, self.ports = rows, ports

    def enabled(self):
        return True

    def devices(self):
        return self.rows

    def device_ports(self, hostname):
        return self.ports.get(hostname, [])


def test_sync_now_discovers_the_inventory_devices(client):
    add(client, name='sw-a-01', serial='S-BY-HAND')
    add(client, name='hv-01', role='server', mgmt_ip='192.0.2.20')
    add(client, name='not-polled')
    rows = [{'hostname': 'sw-a-01.example.org', 'status': 1,
             'facts': {'descr': IOS, 'model': 'WS-C2960X-48FPD-L', 'serial': 'FOC0000X0AA', 'location': 'Hall A',
                       'memory_mb': 512}},
            {'hostname': 'hv-01-telemetry', 'ip': '192.0.2.20', 'status': 1,
             'facts': {'descr': 'Linux hv-01 6.8.12-4-pve #1 SMP x86_64', 'cores': 32}},
            {'hostname': 'unknown-01', 'facts': {'model': 'X'}}]
    ports = {'sw-a-01': [{'name': 'Gi1/0/1', 'speed_bps': 1e9, 'state': 'up', 'description': 'A-1'},
                         {'name': 'Gi1/0/2', 'speed_bps': 1e9, 'state': 'disabled'}]}
    before = sources.use(Telemetry(rows, ports))
    try:
        listing = client.get('/api/inventory').get_json()
        assert any(s['id'] == 'discovery' and s['last_sync'] is None for s in listing['sources'])
        r = client.post('/api/inventory/sync')
        assert r.status_code == 200, r.data
        report = next(x for x in r.get_json()['reports'] if x['plugin'] == 'discovery')
    finally:
        sources.use(before)
    assert report['received'] == 2 and report['updated'] == 2 and report['locked'] == 1
    assert report['added'] == 2
    devices = {d['name']: d for d in client.get('/api/inventory').get_json()['devices']}
    sw = devices['sw-a-01']
    assert (sw['model'], sw['serial'], sw['platform'], sw['os'], sw['location'], sw['memory_mb']) == (
        'WS-C2960X-48FPD-L', 'S-BY-HAND', 'Cisco IOS', 'Cisco IOS 15.2(7)E8', 'Hall A', '512')
    assert sw['interface_count'] == 2 and sw['role'] == 'switch'
    assert devices['hv-01']['cores'] == '32' and devices['hv-01']['os'] == 'Linux 6.8.12-4-pve'
    assert devices['not-polled']['model'] == ''
    assert len(devices) == 3                    # nothing added


def test_the_schedule_runs_discovery_on_its_own_clock(client, monkeypatch):
    before = sources.use(Telemetry([], {}))
    try:
        assert inventory_discovery.every_minutes() == 15
        first = inventory_discovery.tick()
        assert first is not None and first['received'] == 0
        assert inventory_discovery.tick(now=time.time() + 60) is None        # not due yet
        assert inventory_discovery.tick(now=time.time() + 15 * 60 + 5) is not None
        monkeypatch.setenv('DISCOVERY_MINUTES', '0')
        assert inventory_discovery.every_minutes() == 0
    finally:
        sources.use(before)


def add(client, **body):
    r = client.post('/api/inventory', json={'role': 'switch', **body})
    assert r.status_code == 201, r.data
    return r.get_json()


def test_drift_shows_where_the_inventory_and_the_device_disagree(client):
    add(client, name='sw-a-01', serial='S-BY-HAND', mgmt_ip='192.0.2.10', memory_mb='520')
    sw = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'sw-a-01')
    r = client.post(f"/api/inventory/{sw['id']}/interfaces", json={'name': 'Gi1/0/99'})
    assert r.status_code in (200, 201), r.data
    rows = [{'hostname': 'sw-a-01', 'sysName': 'sw-b-07.example.org', 'ip': '192.0.2.99', 'status': 1,
             'facts': {'serial': 'FOC0000X0AA', 'memory_mb': 512}}]
    ports = {'sw-a-01': [{'name': 'Gi1/0/1', 'speed_bps': 1e9, 'state': 'up'}]}
    before = sources.use(Telemetry(rows, ports))
    try:
        assert client.post('/api/inventory/sync').status_code == 200
        drift = client.get(f"/api/inventory/{sw['id']}").get_json()['drift']
        since = {(d['kind'], d['field']): d['since'] for d in drift}
        client.post('/api/inventory/sync')
        again = client.get(f"/api/inventory/{sw['id']}").get_json()['drift']
    finally:
        sources.use(before)
    found = {(d['kind'], d['field']): (d['configured'], d['actual']) for d in drift}
    assert found == {('field', 'serial'): ('S-BY-HAND', 'FOC0000X0AA'),      # memory 520 vs 512: close enough
                     ('hostname', 'name'): ('sw-a-01', 'sw-b-07.example.org'),
                     ('address', 'mgmt_ip'): ('192.0.2.10', '192.0.2.99'),
                     ('interface', 'Gi1/0/99'): ('present', 'missing')}
    assert {(d['kind'], d['field']): d['since'] for d in again} == since      # first seen stays
    listed = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'sw-a-01')
    assert listed['drift'] == 4
    all_drift = client.get('/api/inventory/drift').get_json()['devices']
    assert [d['name'] for d in all_drift] == ['sw-a-01']


# ── interfaces, VLANs and networks (issue #919) ─────────────────────────────────────────────────

def test_a_cisco_switch_says_its_ports_macs_ips_and_vlans():
    st = State()
    st.apply_text('\n'.join([
        f'fb_if,{SW},index=10101,ifName=Gi1/0/1 ifOperStatus=1i',
        f'fb_if,{SW},index=10148,ifName=Te1/0/1 ifOperStatus=1i',
        f'fb_if,{SW},index=1010,ifName=Vlan10 ifOperStatus=1i',
        f'fb_ifmac,{SW},index=10101 ifPhysAddress="02:00:00:aa:00:01"',
        f'fb_ip,{SW},index=192.0.2.1 ipAdEntIfIndex=1010i,ipAdEntNetMask="255.255.255.0"',
        f'fb_ip,{SW},index=127.0.0.1 ipAdEntIfIndex=1i,ipAdEntNetMask="255.0.0.0"',
        f'fb_vtp,{SW},index=1.10 vtpVlanName="seats"',
        f'fb_vtp,{SW},index=1.99 vtpVlanName="mgmt"',
        f'fb_ifvlan,{SW},index=10101 vmVlan=10i,vlanTrunkPortDynamicStatus=2i',
        f'fb_ifvlan,{SW},index=10148 vlanTrunkPortDynamicStatus=1i',
    ]))
    dev = st.devices['sw-a-01']
    ports = {i.name: dev.port_facts(i) for i in dev.interfaces.values()}
    assert ports['Gi1/0/1'] == {'mac': '02:00:00:aa:00:01', 'vlan': 10, 'mode': 'access'}
    assert ports['Te1/0/1'] == {'mode': 'trunk'}
    assert ports['Vlan10'] == {'ips': ['192.0.2.1/24']}
    summary = dev.summary()
    assert summary['vlans'] == {'10': 'seats', '99': 'mgmt'} and summary['networks'] == ['192.0.2.0/24']


def test_a_qbridge_switch_says_its_access_vlans_through_the_bridge_ports():
    st = State()
    tags = 'device=sw-x-01,address=192.0.2.30,driver=snmp'
    st.apply_text('\n'.join([
        f'fb_if,{tags},index=5,ifName=ge-0/0/5 ifOperStatus=1i',
        f'fb_bridge,{tags},index=5 ifIndex=5i',
        f'fb_pvid,{tags},index=5 dot1qPvid=20i',
        f'fb_qvlan,{tags},index=20 dot1qVlanStaticName="crew"',
    ]))
    dev = st.devices['sw-x-01']
    assert dev.port_facts(next(iter(dev.interfaces.values()))) == {'vlan': 20}
    assert dev.summary()['vlans'] == {'20': 'crew'}


def test_discovery_fills_interfaces_and_the_vlan_entries(client):
    add(client, name='sw-a-01')
    rows = [{'hostname': 'sw-a-01', 'status': 1,
             'facts': {'vlans': {'10': 'seats', '20': ''}, 'networks': ['192.0.2.0/24']}}]
    ports = {'sw-a-01': [{'name': 'Gi1/0/1', 'state': 'up', 'mac': '02:00:00:aa:00:01', 'vlan': 10,
                          'mode': 'access'},
                         {'name': 'Vlan10', 'state': 'up', 'ips': ['192.0.2.1/24']}]}
    before = sources.use(Telemetry(rows, ports))
    try:
        r = client.post('/api/inventory/sync')
        report = next(x for x in r.get_json()['reports'] if x['plugin'] == 'discovery')
        sw = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'sw-a-01')
        detail = client.get(f"/api/inventory/{sw['id']}").get_json()
    finally:
        sources.use(before)
    assert report['entries']['added'] == 3
    ifaces = {i['name']: i for i in detail['interfaces']}
    assert (ifaces['Gi1/0/1']['mac'], ifaces['Gi1/0/1']['vlan'], ifaces['Gi1/0/1']['mode']) == (
        '02:00:00:aa:00:01', 10, 'access')
    assert ifaces['Vlan10']['ips'] == ['192.0.2.1/24']
    assert detail['discovered']['vlans'] == [{'id': 10, 'name': 'seats'}, {'id': 20, 'name': ''}]
    assert detail['discovered']['networks'] == ['192.0.2.0/24']
    entries = client.get('/api/inventory/entries?type=vlan').get_json()
    names = sorted(e['name'] for e in entries.get('entries', entries if isinstance(entries, list) else []))
    assert names == ['192.0.2.0/24', 'VLAN 20', 'seats']
