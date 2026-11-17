"""Device inventory: servers and VMs with specs, interfaces (by hand and fed), groups and tags that
nest, credentials that inherit, feature switches per device, and login blocks for agents."""
import json

import pytest
from conftest import stored
from test_credentials import key_file

from floorbit import inventory, inventory_interfaces, inventory_scope, store


@pytest.fixture(autouse=True)
def secret_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "key"))
    inventory_scope._handed.clear()


def add(client, **body):
    r = client.post("/api/inventory", json={"role": "switch", **body})
    assert r.status_code == 201, r.data
    return r.get_json()


def group(client, **body):
    r = client.post("/api/inventory/groups", json=body)
    assert r.status_code == 201, r.data
    return r.get_json()


def tag(client, **body):
    r = client.post("/api/inventory/tags", json=body)
    assert r.status_code == 201, r.data
    return r.get_json()


def detail(client, dev):
    return client.get(f"/api/inventory/{dev['id']}").get_json()


# ── Devices of every kind ──────────────────────────────────────────────────────────────────

def test_servers_and_vms_have_specs_icons_and_colours(client):
    host = add(client, name="hv-01", role="server", cpu="EPYC 7313", cores="32", memory_mb="262144", os="Proxmox VE")
    vm = add(client, name="dns-01", role="vm", host="hv-01", cores="4", memory_mb="8192", disk_gb="64",
             platform="debian", icon="cloud", color="#1E88E5")
    assert host["cores"] == "32" and vm["host"] == "hv-01" and vm["icon"] == "cloud" and vm["color"] == "#1e88e5"
    assert client.post("/api/inventory", json={"name": "x", "role": "vm", "cores": "four"}).status_code == 400
    assert client.post("/api/inventory", json={"name": "x", "icon": "dragon"}).status_code == 400
    assert client.post("/api/inventory", json={"name": "x", "color": "red"}).status_code == 400
    assert client.patch(f"/api/inventory/{vm['id']}", json={"color": ""}).get_json()["color"] == ""


def test_a_fed_spec_changed_by_hand_is_locked(app_module):
    data = {"inventory": []}
    inventory.sync(data, "netbox", [{"ref": "vm-1", "name": "dns-01", "role": "vm", "cores": "2"}])
    dev = data["inventory"][0]
    inventory.update(data, dev["id"], {"cores": "4"})
    inventory.sync(data, "netbox", [{"ref": "vm-1", "name": "dns-01", "role": "vm", "cores": "2"}])
    assert dev["cores"] == "4" and "cores" in dev["locked"]


# ── Interfaces ─────────────────────────────────────────────────────────────────────────────

def test_interfaces_by_hand_with_ranges(client):
    sw = add(client, name="sw-a-01")
    r = client.post(f"/api/inventory/{sw['id']}/interfaces", json={"names": "Gi1/0/1-48, Te1/1/1-2", "type": "copper",
                                                                  "speed_mbps": 1000})
    assert r.status_code == 201 and len(r.get_json()["added"]) == 50
    ifaces = detail(client, sw)["interfaces"]
    assert [i["name"] for i in ifaces[:3]] == ["Gi1/0/1", "Gi1/0/2", "Gi1/0/3"]    # natural order
    te = next(i for i in ifaces if i["name"] == "Te1/1/1")
    r = client.patch(f"/api/inventory/{sw['id']}/interfaces/{te['id']}",
                     json={"type": "fiber", "speed_mbps": 10000, "mode": "trunk", "ips": "192.0.2.1/31",
                           "mac": "00-11-22-33-44-55"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ips"] == ["192.0.2.1/31"] and body["mac"] == "00:11:22:33:44:55" and body["mode"] == "trunk"
    bad = client.patch(f"/api/inventory/{sw['id']}/interfaces/{te['id']}", json={"vlan": 5000})
    assert bad.status_code == 400
    again = client.post(f"/api/inventory/{sw['id']}/interfaces", json={"names": "Gi1/0/1"})
    assert again.get_json()["added"] == []            # already there
    assert client.delete(f"/api/inventory/{sw['id']}/interfaces/{te['id']}").get_json() == {"result": "deleted"}
    assert client.get("/api/inventory").get_json()["devices"][0]["interface_count"] == 49


def test_fed_interfaces_keep_hand_changes_and_are_never_deleted():
    dev = {"name": "sw", "interfaces": []}
    feed = inventory_interfaces.clean_feed([{"name": "Gi1/0/1", "speed_mbps": 1000, "description": "seat"},
                                            {"name": "Gi1/0/2", "speed_mbps": 1000}, {"name": "bad name!"}])
    assert [i["name"] for i in feed] == ["Gi1/0/1", "Gi1/0/2"]
    assert inventory_interfaces.merge_feed(dev, "librenms", feed)["added"] == 2
    one = inventory_interfaces.by_name(dev, "gi1/0/1")
    inventory_interfaces.update(dev, one["id"], {"description": "uplink"})
    assert one["locked"] == ["description"]
    counts = inventory_interfaces.merge_feed(dev, "librenms", feed[:1])
    assert one["description"] == "uplink" and counts["gone"] == 1
    assert inventory_interfaces.by_name(dev, "Gi1/0/2")["gone"] == ["librenms"]
    assert inventory_interfaces.remove(dev, one["id"]) == "hidden"
    inventory_interfaces.update(dev, one["id"], {"unlock": ["description"]})
    assert one["description"] == "seat"
    with pytest.raises(inventory_interfaces.InterfaceError):
        inventory_interfaces.update(dev, one["id"], {"name": "Gi9"})   # fed: renamed at the source


def test_inventory_feeds_carry_interfaces(app_module):
    data = {"inventory": []}
    items, _ = inventory.clean_feed([{"id": "1", "name": "fw-01", "role": "firewall",
                                      "interfaces": [{"name": "igb0", "ips": ["192.0.2.1/24"]}]}])
    report = inventory.sync(data, "netbox", items)
    assert report["interfaces"] == 1
    assert data["inventory"][0]["interfaces"][0]["ips"] == ["192.0.2.1/24"]
    # A feed without the key leaves hand-made interfaces alone.
    inventory_interfaces.add(data["inventory"][0], {"names": "mgmt0"})
    items, _ = inventory.clean_feed([{"id": "1", "name": "fw-01", "role": "firewall"}])
    inventory.sync(data, "netbox", items)
    assert len(data["inventory"][0]["interfaces"]) == 2


def test_interfaces_come_from_the_monitoring_source(client):
    add(client, name="sw-a-01")
    r = client.post("/api/inventory/interfaces/sync", json={})
    # The test LibreNMS is set up with ports for its switches; with none known, nothing happens.
    assert r.status_code in (200, 409)
    if r.status_code == 200:
        assert r.get_json()["plugin"]


def test_netbox_interfaces_and_vms():
    from floorbit.builtin_plugins.netbox.plugin import interface, vm
    raw = {"name": "Te1/1/1", "type": {"value": "10gbase-x-sfpp"}, "speed": 10_000_000, "enabled": True,
           "mode": {"value": "tagged"}, "untagged_vlan": {"vid": 10}, "mac_address": "00:11:22:33:44:55"}
    out = interface(raw, ["192.0.2.1/31"])
    assert out["type"] == "fiber" and out["speed_mbps"] == 10000 and out["mode"] == "trunk" and out["vlan"] == 10
    assert interface({"name": "eth0"})["type"] == "virtual"
    machine = vm({"id": 5, "name": "dns-01", "vcpus": 2.0, "memory": 4096, "disk": 32000,
                  "device": {"name": "hv-01"}, "platform": {"name": "Debian 12"}}, disk_in_mb=True)
    assert machine == {"id": "vm-5", "name": "dns-01", "role": "vm", "mgmt_ip": "", "hall": "", "status": "",
                       "platform": "Debian 12", "cores": "2", "memory_mb": "4096", "disk_gb": "32", "host": "hv-01"}


# ── Groups, tags and inheritance ───────────────────────────────────────────────────────────

def test_groups_nest_and_devices_inherit(client):
    core = tag(client, name="core", color="#E53935", properties={"snmp.port": "161"})
    hall = group(client, name="Hall A", icon="switch", properties={"site": "hall-a", "rack": "r1"},
                 features={"ports": False})
    row = group(client, name="Row 1", parent_id=hall["id"], tags=[core["id"]], properties={"rack": "r7"})
    sw = add(client, name="sw-a-01", group_id=row["id"], properties={"rack": "r9"})
    res = detail(client, sw)["resolved"]
    assert {k: v["value"] for k, v in res["properties"].items()} == {"site": "hall-a", "rack": "r9", "snmp.port": "161"}
    assert res["properties"]["site"]["from"]["name"] == "Hall A"
    assert res["features"]["ports"] == {"on": False, "from": {"type": "group", "id": hall["id"], "name": "Hall A"}}
    assert res["features"]["terminal"]["on"] is True
    assert [t["name"] for t in res["tags"]] == ["core"] and res["tags"][0]["own"] is False
    assert res["look"]["icon"]["value"] == "switch" and res["group_path"][0]["name"] == "Hall A"
    # The device says otherwise: it wins.
    client.patch(f"/api/inventory/{sw['id']}", json={"features": {"ports": True}})
    assert detail(client, sw)["resolved"]["features"]["ports"]["on"] is True


def test_group_rules(client):
    a = group(client, name="A")
    b = group(client, name="B", parent_id=a["id"])
    assert client.patch(f"/api/inventory/groups/{a['id']}", json={"parent_id": b["id"]}).status_code == 400
    assert client.post("/api/inventory/groups", json={"name": "B", "parent_id": a["id"]}).status_code == 400
    assert client.post("/api/inventory/groups", json={"name": "x", "features": {"nope": True}}).status_code == 400
    sw = add(client, name="sw-1", group_id=b["id"])
    assert client.delete(f"/api/inventory/groups/{b['id']}").get_json() == {"ok": True, "moved": 1}
    assert detail(client, sw)["group_id"] == a["id"]            # moved up, not lost
    assert client.post("/api/inventory", json={"name": "x", "group_id": "nope"}).status_code == 400


def test_removing_a_tag_takes_it_off_everything(client):
    t = tag(client, name="lab")
    g = group(client, name="G", tags=[t["id"]])
    sw = add(client, name="sw-1", tags=[t["id"]])
    assert client.get("/api/inventory/groups").get_json()["tags"][0]["used"] == 2
    client.delete(f"/api/inventory/tags/{t['id']}")
    assert detail(client, sw)["tags"] == []
    assert client.get("/api/inventory/groups").get_json()["groups"][0]["tags"] == [] and g


def test_defaults_switch_a_plugin_on_everywhere(client):
    sw = add(client, name="sw-1")
    assert detail(client, sw)["resolved"]["features"]["netbox"]["on"] is False      # plugins: off by default
    client.patch("/api/inventory/defaults", json={"features": {"netbox": True}})
    assert detail(client, sw)["resolved"]["features"]["netbox"]["on"] is True


# ── Credentials ────────────────────────────────────────────────────────────────────────────

def put_cred(client, **body):
    r = client.put("/api/inventory/credentials", json=body)
    assert r.status_code == 200, r.data
    return r.get_json()


def test_credentials_are_write_only_and_inherit(client):
    hall = group(client, name="Hall A")
    sw = add(client, name="sw-a-01", group_id=hall["id"], mgmt_ip="198.51.100.4")
    put_cred(client, owner_type="group", owner_id=hall["id"], kind="ssh", username="ops", secret="hall-secret")
    put_cred(client, owner_type="defaults", kind="snmp_v3", username="mon", secret="auth-pass-1",
             priv_secret="priv-pass-1", auth_protocol="SHA256")
    listed = client.get("/api/inventory/credentials").get_json()["credentials"]
    assert {c["owner_name"] for c in listed} == {"Hall A", "All devices"}
    text = json.dumps(listed) + json.dumps(detail(client, sw)) + stored(store.DATA_FILE)
    assert "hall-secret" not in text and "priv-pass-1" not in text
    creds = detail(client, sw)["resolved"]["credentials"]
    assert creds["ssh"]["from"]["name"] == "Hall A" and creds["snmp_v3"]["secrets"] == ["priv_secret", "secret"]
    # The device's own one wins; editing keeps the secret when none is typed.
    own = put_cred(client, owner_type="device", owner_id=sw["id"], kind="ssh", username="local", secret="dev-secret")
    again = put_cred(client, owner_type="device", owner_id=sw["id"], kind="ssh", username="local2")
    assert again["id"] == own["id"] and again["rev"] != own["rev"]
    data = store.read_json(store.DATA_FILE)
    opened = inventory_scope.login_for(data, inventory.find(data, sw["id"]), "ssh")
    assert opened["username"] == "local2" and opened["secret"] == "dev-secret"
    assert client.put("/api/inventory/credentials", json={"owner_type": "device", "owner_id": sw["id"],
                                                          "kind": "ssh", "username": "u"}).status_code == 200
    assert client.put("/api/inventory/credentials", json={"owner_type": "tag", "owner_id": "x", "kind": "ssh",
                                                          "username": "u", "secret": "s"}).status_code == 400
    assert client.put("/api/inventory/credentials", json={"owner_type": "defaults", "kind": "telnet",
                                                          "secret": "s"}).status_code == 400
    assert client.delete(f"/api/inventory/credentials/{own['id']}").get_json() == {"ok": True}


def test_only_admins_set_credentials_and_techs_clear_blocks(app_module, client):
    from tests.test_rbac import sign_in_as
    sw = add(client, name="sw-1")
    tech = sign_in_as(app_module, "te7", "tech")
    lead = sign_in_as(app_module, "le7", "lead")
    body = {"owner_type": "device", "owner_id": sw["id"], "kind": "ssh", "username": "u", "secret": "s"}
    assert tech.put("/api/inventory/credentials", json=body).status_code == 403
    assert lead.put("/api/inventory/credentials", json=body).status_code == 403
    assert lead.get("/api/inventory/credentials").status_code == 200
    assert tech.post("/api/inventory/blocks/clear", json={"device_id": sw["id"]}).get_json() == {"cleared": 0}
    viewer = sign_in_as(app_module, "vi7", "viewer")
    assert viewer.post("/api/inventory/blocks/clear", json={"device_id": sw["id"]}).status_code == 403
    assert viewer.get(f"/api/inventory/{sw['id']}").get_json()["resolved"]["credentials"] == {}


# ── For agent plugins ──────────────────────────────────────────────────────────────────────

def test_plugin_targets_need_the_plugin_on_and_a_credential(client):
    from tests.test_agent import enrol, head
    lab = tag(client, name="lab", features={"ssh-ports": True})
    sw1 = add(client, name="sw-1", mgmt_ip="198.51.100.1", tags=[lab["id"]], platform="ios")
    add(client, name="sw-2", mgmt_ip="198.51.100.2")                       # plugin not on
    sw3 = add(client, name="sw-3", tags=[lab["id"]])                       # no credential
    put_cred(client, owner_type="device", owner_id=sw1["id"], kind="ssh", username="ops", secret="pw-1")
    targets = inventory_scope.plugin_targets("ssh-ports", ["ssh"])
    assert [(t["name"], t["address"], t["platform"]) for t in targets] == [("sw-1", "198.51.100.1", "ios")]
    cred = targets[0]["credential"]
    assert cred["username"] == "ops" and cred["secret"] == "pw-1" and cred["kind"] == "ssh" and cred["rev"]
    assert inventory_scope.plugin_targets("ssh-ports", ["snmp_v2c"]) == []
    # The agent asks with its key; the list is cached by ETag.
    key = enrol(client)["key"]
    r = client.get("/api/agent/v1/inventory/ssh-ports?kinds=ssh", headers=head(key))
    assert r.status_code == 200 and r.get_json()["devices"][0]["credential"]["secret"] == "pw-1"
    assert r.headers["Cache-Control"] == "no-store"
    etag = r.headers["ETag"]
    assert client.get("/api/agent/v1/inventory/ssh-ports?kinds=ssh",
                      headers={**head(key), "If-None-Match": etag}).status_code == 304
    assert client.get("/api/agent/v1/inventory/ssh-ports", headers=head("wrong")).status_code == 401
    # A failed login blocks the device until a tech clears it; a new password clears it too.
    r = client.post("/api/agent/v1/inventory/auth-failed", headers=head(key),
                    json={"device_id": sw1["id"], "credential_id": cred["id"], "rev": cred["rev"],
                          "plugin": "ssh-ports", "message": "Authentication failed"})
    assert r.get_json() == {"blocked": True}
    assert inventory_scope.plugin_targets("ssh-ports", ["ssh"]) == []
    blocks = client.get("/api/inventory/blocks").get_json()["blocks"]
    assert [(b["device"], b["plugin"], b["agent"]) for b in blocks] == [("sw-1", "ssh-ports", "Demo LAN 2026")]
    assert detail(client, sw1)["resolved"]["credentials"]["ssh"]["blocked"] is True
    assert client.post("/api/inventory/blocks/clear", json={"device_id": sw1["id"]}).get_json() == {"cleared": 1}
    assert len(inventory_scope.plugin_targets("ssh-ports", ["ssh"])) == 1
    inventory_scope.auth_failed(sw1["id"], cred["id"], cred["rev"], "ssh-ports", "nope")
    put_cred(client, owner_type="device", owner_id=sw1["id"], kind="ssh", username="ops", secret="pw-2")
    assert inventory_scope.plugin_targets("ssh-ports", ["ssh"])[0]["credential"]["secret"] == "pw-2"
    # An old rev reported late doesn't block the new password.
    assert inventory_scope.auth_failed(sw1["id"], cred["id"], cred["rev"], "ssh-ports", "late") is None
    assert sw3


def test_handing_out_logins_is_audited_once(client):
    from tests.test_ports import audit_lines
    sw = add(client, name="sw-1", features={"ssh-ports": True})
    put_cred(client, owner_type="device", owner_id=sw["id"], kind="ssh", username="ops", secret="pw")
    for _ in range(3):
        inventory_scope.plugin_targets("ssh-ports")
    handed = [e for e in audit_lines() if e["action"].startswith("Handed stored logins")]
    assert len(handed) == 1


# ── Port actions here honour it too ────────────────────────────────────────────────────────

def test_feature_switched_off_stops_port_actions(client):
    from floorbit import ports
    sw = add(client, name="sw-1", mgmt_ip="198.51.100.9", features={"ports": False})
    data = store.read_json(store.DATA_FILE)
    with pytest.raises(ports.PortError, match="switched off"):
        ports._feature(inventory.find(data, sw["id"]), "ports")
    ports._feature(inventory.find(data, sw["id"]), "terminal")      # the others stay on


def test_game_servers_and_vms_say_which_host_they_run_on(client):
    host = add(client, name="hv-01", role="server")
    vm = add(client, name="vm-games", role="vm", host="hv-01")
    bad = {"name": "CS", "host": "192.0.2.50", "port": 27015, "query": "tcp", "runs_on": "nowhere"}
    assert client.post("/api/game-servers", json=bad).status_code == 400
    r = client.post("/api/game-servers", json=bad | {"runs_on": "VM-GAMES"})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["runs_on"] == "vm-games"
    runs = detail(client, host)["runs_here"]
    assert [(x["kind"], x["name"]) for x in runs] == [("device", "vm-games"), ("game-server", "CS")]
    assert [x["name"] for x in detail(client, vm)["runs_here"]] == ["CS"]


def test_device_options_list_each_name_once(client):
    add(client, name="fw-01", role="firewall")
    add(client, name="FW-01", role="firewall")
    names = [o["value"] for o in client.get("/api/options/devices").get_json()["options"]]
    assert [n.lower() for n in names].count("fw-01") == 1
