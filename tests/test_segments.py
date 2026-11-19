"""Network segments (issue #946, floorbit/segments.py) and the agent's one-off SNMP GETs
(floorbit/telemetry/snmpget.py)."""
import socket
import threading

import pytest

from floorbit import segments
from floorbit.telemetry import snmpget


def test_segments_start_with_lookups_off_and_are_checked(client):
    r = client.post('/api/settings/segments', json={'vlan': 110, 'network': '10.10.1.7/22', 'name': ' Seats  A '})
    assert r.status_code == 201
    seg = r.get_json()['segment']
    assert seg['network'] == '10.10.0.0/22' and seg['name'] == 'Seats A' and seg['lookups'] is False
    assert client.post('/api/settings/segments', json={'vlan': 111, 'network': '10.10.0.0/22'}).status_code == 400
    assert client.post('/api/settings/segments', json={'vlan': 5000, 'network': '10.20.0.0/24'}).status_code == 400
    assert client.post('/api/settings/segments', json={'vlan': 5, 'network': 'example'}).status_code == 400
    changed = client.patch(f'/api/settings/segments/{seg["id"]}', json={'lookups': True}).get_json()['segment']
    assert changed['lookups'] is True
    assert segments.for_ip('10.10.2.40')['vlan'] == 110 and segments.for_ip('10.11.0.1') is None
    assert client.delete(f'/api/settings/segments/{seg["id"]}').status_code == 200
    assert client.get('/api/settings/segments').get_json()['segments'] == []


def test_the_narrowest_range_wins():
    found = [{'network': '10.0.0.0/8', 'vlan': 1}, {'network': '10.10.0.0/22', 'vlan': 110}]
    assert segments.for_ip('10.10.1.1', found)['vlan'] == 110
    assert segments.for_ip('10.99.1.1', found)['vlan'] == 1


def test_crew_cannot_change_segments(kiosk_client):
    assert kiosk_client.get('/api/settings/segments').status_code == 403
    assert kiosk_client.post('/api/settings/segments', json={'vlan': 1, 'network': '10.0.0.0/24'}).status_code == 403


@pytest.mark.parametrize('name,vlan', [('Vlan110', 110), ('Vl20', 20), ('vlanif 30', 30), ('irb.40', 40),
                                       ('GigabitEthernet1/0/1', None), ('Vlan5000', None)])
def test_vlan_interfaces_by_name(name, vlan):
    assert segments.vlan_of_interface(name) == vlan


def test_discovery_proposes_segments_and_never_overwrites_a_hand_edit(client, monkeypatch):
    from floorbit.store import load_data, save_data
    data = load_data()
    data['inventory_discovered'] = {'dev-1': {'vlans': [{'id': 110, 'name': 'SEATS-A'}],
                                              'svis': [{'vlan': 110, 'network': '10.10.0.0/22', 'if_index': 110},
                                                       {'vlan': 120, 'network': '10.12.0.0/24', 'if_index': 120}]}}
    save_data(data)
    assert client.post('/api/settings/segments/discover').get_json() == {'added': 2, 'updated': 0, 'found': 2}
    found = {s['vlan']: s for s in client.get('/api/settings/segments').get_json()['segments']}
    assert found[110]['name'] == 'SEATS-A' and found[110]['if_index'] == 110 and found[110]['source'] == 'discovery'
    assert not any(s['lookups'] for s in found.values())            # off until someone turns them on
    client.patch(f'/api/settings/segments/{found[120]["id"]}', json={'name': 'Crew', 'lookups': True})
    client.patch(f'/api/settings/segments/{found[110]["id"]}', json={'lookups': True})
    data = load_data()
    data['inventory_discovered']['dev-1']['vlans'] = [{'id': 110, 'name': 'SEATS-A-NEW'}, {'id': 120, 'name': 'X'}]
    save_data(data)
    client.post('/api/settings/segments/discover')
    found = {s['vlan']: s for s in client.get('/api/settings/segments').get_json()['segments']}
    assert found[110]['name'] == 'SEATS-A-NEW' and found[110]['lookups'] is True     # discovery's own: corrected
    assert found[120]['name'] == 'Crew'                                              # changed by hand: kept


def test_the_facts_name_vlan_interfaces():
    from floorbit.telemetry.state import State
    st = State()
    tags = 'device=core-01,address=192.0.2.1,driver=snmp'
    st.apply_text(f'fb_ifmac,{tags},index=110 ifName="Vlan110"\n'
                  f'fb_ip,{tags},index=10.10.0.1 ipAdEntIfIndex=110i,ipAdEntNetMask="255.255.252.0"\n'
                  f'fb_ip,{tags},index=192.0.2.1 ipAdEntIfIndex=1i,ipAdEntNetMask="255.255.255.0"\n')
    # Only the VLAN interface is a segment; the management address on another interface isn't.
    assert st.find('core-01').summary()['svis'] == [{'vlan': 110, 'network': '10.10.0.0/22', 'if_index': 110}]


# ── the SNMP GETs, against a tiny SNMPv2c responder on localhost ──────────────────────────────

class Responder:
    """Answers SNMPv2c GETs from ``table`` ({(community, oid): value}); anything else: noSuchInstance."""

    def __init__(self, table):
        from pysnmp.proto import api
        self.table, self.api = table, api
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.asked = []
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        from pyasn1.codec.ber import decoder, encoder
        p = self.api.PROTOCOL_MODULES[self.api.SNMP_VERSION_2C]
        while True:
            try:
                data, peer = self.sock.recvfrom(65535)
            except OSError:
                return
            msg, _rest = decoder.decode(data, asn1Spec=p.Message())
            community = str(p.apiMessage.get_community(msg))
            req = p.apiMessage.get_pdu(msg)
            resp = p.apiPDU.get_response(req)
            binds = []
            for oid, _val in p.apiPDU.get_varbinds(req):
                self.asked.append((community, str(oid)))
                value = self.table.get((community, str(oid)))
                if value is None:
                    binds.append((oid, p.NoSuchInstance('')))
                elif isinstance(value, bytes):
                    binds.append((oid, p.OctetString(value)))
                else:
                    binds.append((oid, p.Integer(value)))
            p.apiPDU.set_varbinds(resp, binds)
            p.apiMessage.set_pdu(msg, resp)
            self.sock.sendto(encoder.encode(msg), peer)

    def close(self):
        self.sock.close()


@pytest.fixture
def responder():
    made = []

    def make(table):
        made.append(Responder(table))
        return made[-1]
    yield make
    for r in made:
        r.close()


def test_a_pc_is_found_with_three_gets(responder):
    mac_oid = '2.0.0.0.0.49'                        # 02:00:00:00:00:31
    core = responder({('example-community', '1.3.6.1.2.1.4.22.1.2.110.10.10.1.23'): bytes.fromhex('020000000031')})
    access = responder({('example-community@110', f'1.3.6.1.2.1.17.4.3.1.2.{mac_oid}'): 7,
                        ('example-community@110', '1.3.6.1.2.1.17.1.4.1.2.7'): 10107})
    login = {'community': 'example-community', 'snmp_version': '2c'}
    mac = snmpget.mac_of_ip({**login, 'address': '127.0.0.1', 'snmp_port': core.port}, 110, '10.10.1.23')
    assert mac == '02:00:00:00:00:31'
    switch = {**login, 'name': 'access-01', 'address': '127.0.0.1', 'snmp_port': access.port}
    assert snmpget.port_of_mac(switch, mac, 110) == 10107
    assert len(access.asked) == 2 and len(core.asked) == 1                         # GETs, never a walk
    assert snmpget.port_of_mac(switch, '02:00:00:00:00:99', 110) is None           # not on this switch


def test_a_switch_that_does_not_answer_times_out_quickly():
    silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    silent.bind(('127.0.0.1', 0))
    try:
        with pytest.raises(snmpget.SnmpError):
            snmpget.get({'address': '127.0.0.1', 'snmp_port': silent.getsockname()[1], 'community': 'x'},
                        ['1.3.6.1.2.1.1.5.0'], timeout=0.3)
    finally:
        silent.close()
