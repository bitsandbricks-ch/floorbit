"""Signed plugin bundles for the agents (floorbit/plugins/bundles.py, scripts/agent_bundles.py):
signing and checking, safe unpacking, the hosted side handing them on, and rollouts in the audit log."""
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest
from test_agent import clean_tunnel, enrol, head  # noqa: F401  # clean_tunnel is autouse there

from floorbit.plugins import bundles

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def keypair(tmp_path):
    pem, pub = bundles.keygen()
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "release.pub").write_text(pub)
    return pem, bundles.pinned_keys(keys), keys


def plugin_folder(tmp_path, pid="hallthing"):
    folder = tmp_path / "src" / pid
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(f"id: {pid}\nname: Hall thing\nversion: '1.0'\n")
    (folder / "agent.py").write_text("x = 1\n")
    return folder


def test_sign_verify_and_tamper(tmp_path, keypair):
    pem, keys, _ = keypair
    folder = plugin_folder(tmp_path)
    doc = bundles.sign(folder, pem, "0.5.0", 1)
    assert doc["id"] == "hallthing" and set(doc["files"]) == {"plugin.yaml", "agent.py"}
    assert bundles.verify(folder, keys, "hallthing", "0.5.0")["version"] == "0.5.0"
    with pytest.raises(bundles.BundleError, match=r"not 0\.6\.0"):
        bundles.verify(folder, keys, "hallthing", "0.6.0")
    with pytest.raises(bundles.BundleError, match="not other"):
        bundles.verify(folder, keys, "other")
    with pytest.raises(bundles.BundleError, match="does not trust"):
        bundles.verify(folder, bundles.pinned_keys(tmp_path / "nowhere"))
    (folder / "agent.py").write_text("import os; os.system('id')\n")
    with pytest.raises(bundles.BundleError, match="differ"):
        bundles.verify(folder, keys)
    (folder / "agent.py").write_text("x = 1\n")
    (folder / "extra.py").write_text("y = 2\n")
    with pytest.raises(bundles.BundleError, match="differ"):
        bundles.verify(folder, keys)


def test_a_changed_signature_document_fails(tmp_path, keypair):
    pem, keys, _ = keypair
    folder = plugin_folder(tmp_path)
    bundles.sign(folder, pem, "0.5.0", 1)
    sig = json.loads((folder / bundles.SIGFILE).read_text())
    sig["version"] = "9.9.9"       # an old bundle passed off as a newer one
    (folder / bundles.SIGFILE).write_text(json.dumps(sig))
    with pytest.raises(bundles.BundleError, match="bad signature"):
        bundles.verify(folder, keys)


def test_pack_unpack_round_trip(tmp_path, keypair):
    pem, keys, _ = keypair
    folder = plugin_folder(tmp_path)
    bundles.sign(folder, pem, "0.5.0", 1)
    data = bundles.pack(folder)
    assert data == bundles.pack(folder)          # the same folder packs the same
    bundles.unpack(data, tmp_path / "out")
    assert bundles.verify(tmp_path / "out", keys, "hallthing", "0.5.0")


@pytest.mark.parametrize("name, kind", [("../evil.py", tarfile.REGTYPE), ("/etc/x", tarfile.REGTYPE),
                                        ("link", tarfile.SYMTYPE), ("dev", tarfile.CHRTYPE)])
def test_unpack_refuses_what_could_escape(tmp_path, name, kind):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
        tar.addfile(info, io.BytesIO(b"") if kind == tarfile.REGTYPE else None)
    with pytest.raises(bundles.BundleError, match="refused"):
        bundles.unpack(buf.getvalue(), tmp_path / "out")
    assert not (tmp_path / "evil.py").exists()


def test_unpack_refuses_junk(tmp_path):
    with pytest.raises(bundles.BundleError, match="unreadable"):
        bundles.unpack(b"not a tarball", tmp_path / "out")


def test_versions():
    assert bundles.newer("0.10.0", "0.9.9") and bundles.newer("1.0", "0.9")
    assert not bundles.newer("0.5.0", "0.5") and not bundles.newer("0.4.9", "0.5.0")


def test_the_release_script_signs_every_builtin_plugin(tmp_path, keypair):
    _, _, keys = keypair
    script = ROOT / "scripts" / "agent_bundles.py"
    key = tmp_path / "key.pem"
    key.write_bytes(keypair[0])
    out = tmp_path / "out"
    built = subprocess.run([sys.executable, str(script), "build", "--key", str(key), "--keys", str(keys),
                            "--out", str(out), "--version", "0.5.0"], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    index = json.loads((out / "index.json").read_text())
    assert {"netflow-relay", "librenms", "syslog-relay"} <= set(index["plugins"]) and "demo" not in index["plugins"]
    assert index["plugins"]["netflow-relay"]["file"] == "netflow-relay-0.5.0.tar.gz"
    ok = subprocess.run([sys.executable, str(script), "verify", str(out), "--keys", str(keys)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout


def test_the_release_script_refuses_a_key_agents_dont_pin(tmp_path, keypair):
    other, _ = bundles.keygen()
    key = tmp_path / "other.pem"
    key.write_bytes(other)
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "agent_bundles.py"), "build", "--key", str(key),
                          "--keys", str(keypair[2]), "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert res.returncode != 0 and "not one the agents pin" in res.stderr


@pytest.fixture
def offered(tmp_path, keypair, monkeypatch):
    pem, _, _ = keypair
    out = tmp_path / "bundles"
    out.mkdir()
    folder = plugin_folder(tmp_path, "netflow-relay")
    bundles.sign(folder, pem, "0.5.0", 1)
    data = bundles.pack(folder)
    (out / "netflow-relay-0.5.0.tar.gz").write_bytes(data)
    (out / "secret.txt").write_text("not a bundle")
    (out / "index.json").write_text(json.dumps({"plugins": {
        "netflow-relay": {"version": "0.5.0", "file": "netflow-relay-0.5.0.tar.gz", "sha256": bundles.sha256(data),
                     "agent_api": 1},
        "evil": {"version": "1", "file": "../../etc/passwd"}}}))
    monkeypatch.setenv("FLOORBIT_AGENT_BUNDLES", str(out))
    return data


def test_the_hosted_side_offers_and_hands_on_bundles(client, anon_client, offered, app_module):
    from floorbit import agent_plugins
    registry = app_module.app.extensions["floorbit_plugins"]
    registry.set_enabled("netflow-relay", True)
    try:
        key = enrol(client)["key"]
        cfg = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()
        assert cfg["bundles"]["netflow-relay"]["file"] == "netflow-relay-0.5.0.tar.gz"
        assert "evil" not in agent_plugins.bundles_index()
        got = anon_client.get("/api/agent/v1/bundles/netflow-relay-0.5.0.tar.gz", headers=head(key))
        assert got.status_code == 200 and got.data == offered
        assert anon_client.get("/api/agent/v1/bundles/netflow-relay-0.5.0.tar.gz").status_code in (401, 403)
        for name in ("secret.txt", "index.json", "..%2Findex.json", "other-0.5.0.tar.gz"):
            assert anon_client.get(f"/api/agent/v1/bundles/{name}", headers=head(key)).status_code == 404
    finally:
        registry.set_enabled("netflow-relay", False)


def test_no_bundles_without_an_index(client, anon_client, tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_AGENT_BUNDLES", str(tmp_path / "none"))
    key = enrol(client)["key"]
    assert anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()["bundles"] == {}


def test_rollouts_reach_the_report_and_the_audit_log(client, anon_client):
    made = enrol(client, "Hall agent")
    now = time.time()
    report = {"updates": {
        "policy": "approve", "image": "0.4.0", "keys": ["abc"],
        "plugins": {"lancache": {"version": "0.5.0", "source": "bundle", "probation": True, "rolled_back": ["0.4.5"],
                                 "pending": None},
                    "librenms": {"version": "0.4.0", "source": "image",
                                 "pending": {"version": "0.5.0", "why": "waits for approval on the agent"}},
                    "BAD": {}},
        "events": [{"at": now, "plugin": "lancache", "event": "installed", "version": "0.5.0", "detail": "was 0.4.0"},
                   {"at": now, "plugin": "lancache", "event": "rolled back", "version": "0.4.5", "detail": "boom"},
                   {"at": now, "plugin": "lancache", "event": "hacked", "version": "1"}]},
        "vrrp": {"primary": True, "holds": ["192.0.2.10/24"]}}
    for _ in range(2):      # the same rollout reported twice is audited once
        anon_client.post("/api/agent/v1/report", json={"report": report}, headers=head(made["key"]))
    got = client.get("/api/agents").get_json()["agents"][0]["report"]
    assert got["updates"]["policy"] == "approve" and got["updates"]["signed"] is True
    assert set(got["updates"]["plugins"]) == {"lancache", "librenms"}
    assert got["updates"]["plugins"]["librenms"]["pending"]["version"] == "0.5.0"
    assert [e["event"] for e in got["updates"]["events"]] == ["installed", "rolled back"]
    assert got["vrrp"] == {"primary": True, "holds": ["192.0.2.10/24"]}
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert actions.count("Hall agent: updated plugin lancache to 0.5.0") == 1
    assert actions.count("Hall agent: rolled back plugin lancache 0.4.5 (boom)") == 1
