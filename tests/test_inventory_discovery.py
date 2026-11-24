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
                             'memory_mb': 512,
                             'transceivers': [{'port': '', 'model': 'GLC-SX-MMD', 'descr': '', 'serial': 'SFP0001'}]}
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
    from floorbit.store import load_data, save_data
    tick = inventory_discovery.tick
    # The session's background inventory-sync loops call tick() too (#1222): keep them out and
    # start from an empty schedule, or one of them takes the first run and ours returns None.
    monkeypatch.setattr(inventory_discovery, 'tick', lambda now=None: None)
    with inventory_discovery.running:
        data = load_data()
        data.pop(inventory_discovery.RUNS, None)
        save_data(data)
    before = sources.use(Telemetry([], {}))
    try:
        assert inventory_discovery.every_minutes() == 15
        first = tick()
        assert first is not None and first['received'] == 0
        assert tick(now=time.time() + 60) is None        # not due yet
        assert tick(now=time.time() + 15 * 60 + 5) is not None
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


# ── transceivers (issue #919) ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('model, descr, expected', [
    ('SFP-10G-SR', '', ('SFP+', 'SR', '10G')),
    ('GLC-LH-SMD', '1000BaseLX SFP', ('SFP', 'LR', '1G')),
    ('GLC-TE', '1000BaseT SFP', ('SFP', 'Copper', '1G')),
    ('QSFP-40G-SR4', '', ('QSFP+', 'SR', '40G')),
    ('QSFP-100G-LR4-S', '', ('QSFP28', 'LR', '100G')),
    ('SFP-25G-SR-S', '', ('SFP28', 'SR', '25G')),
    ('SFP-H10GB-CU3M', '10GBASE-CU SFP+ Cable 3 Meter', ('DAC', 'Copper', '10G')),
    ('GLC-BX-D', '1000BASE-BX10-D', ('SFP', 'BiDi', '1G')),
    ('', 'Some optic', ('', '', '')),
])
def test_an_optics_form_media_and_speed_come_from_its_model(model, descr, expected):
    found = inventory_discovery.optic(model, descr)
    assert (found['form'], found['media'], found['speed']) == expected


def test_a_switch_says_its_optics_and_the_ports_they_sit_in():
    st = State()
    ns = 1_700_000_000_000_000_000
    st.apply_text('\n'.join([
        f'fb_if,{SW},index=10149,ifName=Te1/1/1 ifOperStatus=1i {ns}',
        f'fb_if,{SW},index=10150,ifName=Te1/1/2 ifOperStatus=1i {ns}',
        f'fb_if,{SW},index=10151,ifName=Gi1/0/3 ifOperStatus=1i {ns}',
        # Cisco: the port row maps to the interface, the optic is a module inside it
        f'fb_entity,{SW},index=1050 entPhysicalClass=10i,entPhysicalName="TenGigabitEthernet1/1/1" {ns}',
        f'fb_entity,{SW},index=1051 entPhysicalClass=9i,entPhysicalContainedIn=1050i,'
        f'entPhysicalModelName="SFP-10G-LR",entPhysicalSerialNum="AVX0001",entPhysicalDescr="SFP-10GBase-LR" {ns}',
        f'fb_entalias,{SW},index=1050.0 entAliasMappingIdentifier="iso.3.6.1.2.1.2.2.1.1.10149" {ns}',
        # mapped itself, numeric
        f'fb_entity,{SW},index=1052 entPhysicalClass=10i,entPhysicalModelName="SFP-10G-SR",'
        f'entPhysicalSerialNum="AVX0002" {ns}',
        f'fb_entalias,{SW},index=1052.0 entAliasMappingIdentifier=".1.3.6.1.2.1.2.2.1.1.10150" {ns}',
        # no mapping: by the name
        f'fb_entity,{SW},index=1053 entPhysicalClass=10i,entPhysicalName="Gi1/0/3",entPhysicalModelName="GLC-TE",'
        f'entPhysicalSerialNum="AVX0003" {ns}',
        # a port without an optic, a fan with a serial: not optics
        f'fb_entity,{SW},index=1054 entPhysicalClass=10i,entPhysicalName="GigabitEthernet1/0/4" {ns}',
        f'fb_entity,{SW},index=1055 entPhysicalClass=7i,entPhysicalName="Fan 1",entPhysicalSerialNum="FAN1" {ns}',
    ]))
    optics = st.devices['sw-a-01'].transceivers()
    assert [(o['port'], o['serial']) for o in optics] == [('Te1/1/1', 'AVX0001'), ('Te1/1/2', 'AVX0002'),
                                                          ('Gi1/0/3', 'AVX0003')]


def test_telegraf_asks_for_entity_names_and_their_interfaces():
    t = {'name': 'sw-a-01', 'address': '192.0.2.10', 'platform': 'ios', 'drivers': ['snmp'], 'kind': 'switch'}
    conf = '\n'.join(telegraf.snmp(t))
    assert '"1.3.6.1.2.1.47.1.1.1.1.7"' in conf and '"1.3.6.1.2.1.47.1.3.2.1.2"' in conf


def test_discovery_adds_the_optics_as_transceiver_entries_and_keeps_them_while_a_switch_is_away(client):
    add(client, name='sw-a-01')
    add(client, name='sw-a-02')
    optic = {'port': 'Te1/1/1', 'model': 'SFP-10G-SR', 'descr': '', 'serial': 'AVX0001'}
    rows = [{'hostname': 'sw-a-01', 'status': 1, 'facts': {'transceivers': [optic]}}]
    before = sources.use(Telemetry(rows, {}))
    try:
        report = next(x for x in client.post('/api/inventory/sync').get_json()['reports']
                      if x['plugin'] == 'discovery')
        entries = client.get('/api/inventory/entries?type=transceiver').get_json()
        sw = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'sw-a-01')
        detail = client.get(f"/api/inventory/{sw['id']}").get_json()
        # The switch didn't answer this time: its optic stays where it was.
        sources.use(Telemetry([], {}))
        client.post('/api/inventory/sync')
        after = client.get('/api/inventory/entries?type=transceiver').get_json()
        # The optic moved to the other switch.
        sources.use(Telemetry([{'hostname': 'sw-a-02', 'status': 1,
                                'facts': {'transceivers': [{**optic, 'port': 'Te1/1/4'}]}}], {}))
        client.post('/api/inventory/sync')
        moved = client.get('/api/inventory/entries?type=transceiver').get_json()
    finally:
        sources.use(before)
    assert report['entries']['added'] == 1
    rows = entries.get('entries', entries if isinstance(entries, list) else [])
    assert [(e['name'], e['fields']) for e in rows] == [('SFP-10G-SR AVX0001', {
        'device': 'sw-a-01', 'port': 'Te1/1/1', 'form': 'SFP+', 'media': 'SR', 'speed': '10G', 'serial': 'AVX0001'})]
    assert detail['discovered']['transceivers'][0]['serial'] == 'AVX0001'
    kept = after.get('entries', after if isinstance(after, list) else [])
    assert len(kept) == 1 and not kept[0].get('gone')
    now = moved.get('entries', moved if isinstance(moved, list) else [])
    assert len(now) == 1 and (now[0]['fields']['device'], now[0]['fields']['port']) == ('sw-a-02', 'Te1/1/4')


# ── PoE (issue #919) ────────────────────────────────────────────────────────────────────────────

def test_a_cisco_switch_says_poe_per_port_and_its_budget():
    st = State()
    ns = 1_700_000_000_000_000_000
    st.apply_text('\n'.join([
        f'fb_if,{SW},index=10101,ifName=Gi1/0/1 ifOperStatus=1i {ns}',
        f'fb_if,{SW},index=10102,ifName=Gi1/0/2 ifOperStatus=1i {ns}',
        f'fb_if,{SW},index=1,ifName=Vl1 ifOperStatus=1i {ns}',
        f'fb_entalias,{SW},index=1011.0 entAliasMappingIdentifier="iso.3.6.1.2.1.2.2.1.1.10101" {ns}',
        f'fb_entalias,{SW},index=1012.0 entAliasMappingIdentifier="iso.3.6.1.2.1.2.2.1.1.10102" {ns}',
        f'fb_poe,{SW},index=1.1 pethPsePortAdminEnable=1i,pethPsePortDetectionStatus=3i,'
        f'pethPsePortPowerClassifications=4i {ns}',
        f'fb_poe,{SW},index=1.1 cpeExtPsePortPwrConsumption=6400i,cpeExtPsePortPwrAllocated=15400i,'
        f'cpeExtPsePortEntPhyIndex=1011i {ns}',
        f'fb_poe,{SW},index=1.2 pethPsePortAdminEnable=2i,pethPsePortDetectionStatus=1i {ns}',
        f'fb_poe,{SW},index=1.2 cpeExtPsePortPwrConsumption=0i,cpeExtPsePortEntPhyIndex=1012i {ns}',
        f'fb_pse,{SW},index=1 pethMainPsePower=740i,pethMainPseOperStatus=1i,pethMainPseConsumptionPower=37i {ns}',
        f'fb_pse,{SW},index=2 pethMainPsePower=740i,pethMainPseOperStatus=1i,pethMainPseConsumptionPower=0i {ns}',
    ]))
    dev = st.devices['sw-a-01']
    ports = {i.name: dev.port_facts(i).get('poe') for i in dev.interfaces.values()}
    # Port 1.1 is not ifIndex 1 (the VLAN interface): Cisco says which port through ENTITY-MIB.
    assert ports == {'Gi1/0/1': {'state': 'delivering', 'class': 3, 'draw_w': 6.4, 'allocated_w': 15.4},
                     'Gi1/0/2': {'state': 'off', 'draw_w': 0.0}, 'Vl1': None}
    assert dev.summary()['poe'] == {'budget_w': 1480, 'used_w': 37}


def test_other_switches_number_poe_ports_by_ifindex():
    st = State()
    ns = 1_700_000_000_000_000_000
    st.apply_text('\n'.join([
        f'fb_if,{SW},index=5,ifName=5 ifOperStatus=1i {ns}',
        f'fb_poe,{SW},index=1.5 pethPsePortAdminEnable=1i,pethPsePortDetectionStatus=4i {ns}',
    ]))
    dev = st.devices['sw-a-01']
    assert dev.port_facts(next(iter(dev.interfaces.values())))['poe'] == {'state': 'fault'}


def test_telegraf_asks_switches_for_poe():
    t = {'name': 'sw-a-01', 'address': '192.0.2.10', 'platform': 'ios', 'drivers': ['snmp'], 'kind': 'switch'}
    conf = '\n'.join(telegraf.snmp(t))
    assert 'name = "fb_poe"' in conf and '"1.3.6.1.4.1.9.9.402.1.2.1.9"' in conf and 'name = "fb_pse"' in conf
    server = '\n'.join(telegraf.snmp({**t, 'platform': 'other', 'kind': 'server'}))
    assert 'fb_poe' not in server


def test_discovery_keeps_a_switchs_poe_budget(client):
    add(client, name='sw-a-01')
    rows = [{'hostname': 'sw-a-01', 'status': 1, 'facts': {'poe': {'budget_w': 740, 'used_w': 37}}}]
    before = sources.use(Telemetry(rows, {}))
    try:
        client.post('/api/inventory/sync')
        sw = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'sw-a-01')
        detail = client.get(f"/api/inventory/{sw['id']}").get_json()
    finally:
        sources.use(before)
    assert detail['discovered']['poe'] == {'budget_w': 740.0, 'used_w': 37.0}


# ── routes (issue #919) ─────────────────────────────────────────────────────────────────────────

FW = 'device=fw-01,address=192.0.2.1,driver=snmp,kind=firewall'


def test_a_firewall_says_its_routes():
    st = State()
    ns = 1_700_000_000_000_000_000
    st.apply_text('\n'.join([
        f'fb_if,{FW},index=1,ifName=wan ifOperStatus=1i {ns}',
        f'fb_if,{FW},index=2,ifName=lan ifOperStatus=1i {ns}',
        f'fb_route,{FW},index=198.51.100.0.255.255.255.0.0.0.0.0.0 ipCidrRouteIfIndex=2i,'
        f'ipCidrRouteType=3i,ipCidrRouteProto=2i {ns}',
        f'fb_route,{FW},index=0.0.0.0.0.0.0.0.0.203.0.113.1 ipCidrRouteIfIndex=1i,'
        f'ipCidrRouteType=4i,ipCidrRouteProto=3i {ns}',
        f'fb_route,{FW},index=1.2.3 ipCidrRouteIfIndex=1i {ns}',                  # not a route index
    ]))
    assert st.devices['fw-01'].summary()['routes'] == [
        {'network': '0.0.0.0/0', 'next_hop': '203.0.113.1', 'proto': 'static', 'interface': 'wan'},
        {'network': '198.51.100.0/24', 'next_hop': '', 'proto': 'connected', 'interface': 'lan'}]


def test_telegraf_asks_only_firewalls_for_routes():
    t = {'name': 'fw-01', 'address': '192.0.2.1', 'platform': 'opnsense', 'drivers': ['snmp'], 'kind': 'firewall'}
    assert 'name = "fb_route"' in '\n'.join(telegraf.snmp(t))
    assert 'fb_route' not in '\n'.join(telegraf.snmp({**t, 'kind': 'router'}))


def test_discovery_keeps_a_firewalls_routes(client):
    add(client, name='fw-01', role='firewall')
    routes = [{'network': '0.0.0.0/0', 'next_hop': '203.0.113.1', 'interface': 'wan', 'proto': 'static'},
              {'network': 'nonsense', 'next_hop': ''}]
    before = sources.use(Telemetry([{'hostname': 'fw-01', 'status': 1, 'facts': {'routes': routes}}], {}))
    try:
        client.post('/api/inventory/sync')
        fw = next(d for d in client.get('/api/inventory').get_json()['devices'] if d['name'] == 'fw-01')
        detail = client.get(f"/api/inventory/{fw['id']}").get_json()
    finally:
        sources.use(before)
    assert detail['discovered']['routes'] == routes[:1]


# ── actions per kind of device, each on its own clock (issue #919) ─────────────────────────────

def test_each_action_has_its_own_schedule_and_admins_change_it(client, app_module):
    from tests.test_rbac import sign_in_as
    actions = {a['id']: a for a in client.get('/api/inventory/discovery').get_json()['actions']}
    assert list(actions) == ['identity', 'interfaces', 'networks', 'optics', 'poe', 'routes']
    assert [actions[a]['minutes'] for a in ('identity', 'interfaces', 'optics')] == [60, 15, 60]
    assert actions['routes']['roles'] == ['firewall'] and actions['poe']['roles'] == ['switch']
    r = client.put('/api/inventory/discovery/actions/poe', json={'minutes': 5})
    assert r.status_code == 200 and next(a for a in r.get_json()['actions'] if a['id'] == 'poe')['minutes'] == 5
    assert client.put('/api/inventory/discovery/actions/routes', json={'minutes': 0}).status_code == 200
    for bad in (2, -1, 'often', True, 99999):
        assert client.put('/api/inventory/discovery/actions/poe', json={'minutes': bad}).status_code == 400
    assert client.put('/api/inventory/discovery/actions/nope', json={'minutes': 5}).status_code == 404
    actions = {a['id']: a for a in client.get('/api/inventory/discovery').get_json()['actions']}
    assert (actions['poe']['minutes'], actions['routes']['minutes'], actions['routes']['custom']) == (5, 0, True)
    client.put('/api/inventory/discovery/actions/poe', json={'minutes': None})
    assert client.get('/api/inventory/discovery').get_json()['actions'][4]['minutes'] == 15
    # A tech sees the schedule but doesn't change it; a lead runs discovery but doesn't schedule it.
    tech = sign_in_as(app_module, 'te8', 'tech')
    assert tech.get('/api/inventory/discovery').status_code == 200
    assert tech.post('/api/inventory/discovery/run', json={}).status_code == 403
    lead = sign_in_as(app_module, 'le8', 'lead')
    assert lead.put('/api/inventory/discovery/actions/poe', json={'minutes': 30}).status_code == 403


def test_the_schedule_runs_only_the_actions_that_are_due(client, monkeypatch):
    from floorbit.store import load_data, save_data
    tick = inventory_discovery.tick
    # Every app made in this session left an inventory-sync loop that calls tick() each minute
    # (#1222): keep them out, wait for one that is running, and start from an empty schedule.
    monkeypatch.setattr(inventory_discovery, 'tick', lambda now=None: None)
    with inventory_discovery.running:
        data = load_data()
        data.pop(inventory_discovery.RUNS, None)
        save_data(data)
    before = sources.use(Telemetry([], {}))
    try:
        first = tick()
        assert set(first['actions']) == set(inventory_discovery.ACTION_IDS)
        later = tick(now=time.time() + 15 * 60 + 5)        # the hourly ones aren't due
        assert set(later['actions']) == {'interfaces', 'networks', 'poe', 'routes'}
        assert set(load_data()['inventory_discovery_runs']) == set(inventory_discovery.ACTION_IDS)
    finally:
        sources.use(before)


def test_run_now_for_one_action_on_one_device(client):
    sw = add(client, name='sw-a-01')
    fw = add(client, name='fw-01', role='firewall')
    rows = [{'hostname': 'sw-a-01', 'status': 1, 'facts': {'model': 'WS-C2960X-48FPD-L', 'poe': {'budget_w': 740}}},
            {'hostname': 'fw-01', 'status': 1,
             'facts': {'model': 'A1', 'routes': [{'network': '0.0.0.0/0', 'next_hop': '203.0.113.1'}]}}]
    before = sources.use(Telemetry(rows, {}))
    try:
        r = client.post('/api/inventory/discovery/run', json={'actions': ['poe'], 'device': sw['id']})
        assert r.status_code == 200
        report = r.get_json()['report']
        assert report['actions'] == {'poe': {'devices': 1, 'changed': 1}} and report['devices'] == [sw['id']]
        detail = client.get(f"/api/inventory/{sw['id']}").get_json()
        assert detail['discovered']['poe'] == {'budget_w': 740.0, 'used_w': 0.0}
        assert detail['model'] == ''                                     # identity didn't run
        assert client.get(f"/api/inventory/{fw['id']}").get_json()['discovered']['routes'] == []
        # A run for one device doesn't move the schedule.
        assert all(a['last'] is None for a in r.get_json()['actions'])
        # Routes are only a firewall's: on a switch the action does nothing.
        r = client.post('/api/inventory/discovery/run', json={'actions': ['routes', 'identity']})
        assert r.get_json()['report']['actions']['routes']['devices'] == 1
        assert client.get(f"/api/inventory/{fw['id']}").get_json()['discovered']['routes'][0]['network'] == '0.0.0.0/0'
        assert client.get(f"/api/inventory/{sw['id']}").get_json()['discovered']['poe']['budget_w'] == 740.0
        assert client.post('/api/inventory/discovery/run', json={'actions': ['nope']}).status_code == 400
        assert client.post('/api/inventory/discovery/run', json={'device': 'nope'}).status_code == 404
    finally:
        sources.use(before)
