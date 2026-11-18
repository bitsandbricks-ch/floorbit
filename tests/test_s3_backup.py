"""Backups to an S3 bucket (floorbit/s3_backup.py). A fake bucket stands in for S3: nothing leaves."""
import hashlib
import re
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from floorbit import s3_backup

ACCESS, SECRET = "AKIAEXAMPLE", "example-secret-key"


class FakeBucket:
    """Just enough of the S3 API: PUT, GET, DELETE and ListObjectsV2 with paging, path style.
    Checks every request's signature, so a signing mistake fails here and not at an event."""

    def __init__(self, page=1000):
        self.objects, self.calls, self.page, self.fail = {}, [], page, None

    def __call__(self, method, url, data=None, headers=None, **kwargs):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        signed = {k: v for k, v in headers.items() if k.startswith("x-amz-")}
        expected = s3_backup.sign(method, headers["Host"], parts.path, query, signed,
                                  headers["x-amz-content-sha256"], ACCESS, SECRET, "us-east-1", headers["x-amz-date"])
        assert headers["Authorization"] == expected
        assert headers["x-amz-content-sha256"] == hashlib.sha256(data or b"").hexdigest()
        self.calls.append((method, parts.path, query))
        if self.fail:
            return Answer(self.fail, b"<Error><Code>AccessDenied</Code></Error>")
        bucket, _, key = unquote(parts.path).lstrip("/").partition("/")
        assert bucket == "backups"
        if method == "PUT":
            self.objects[key] = bytes(data)
            return Answer(200)
        if method == "DELETE":
            self.objects.pop(key, None)
            return Answer(204)
        if key:
            if key not in self.objects:
                return Answer(404, b"<Error><Code>NoSuchKey</Code></Error>")
            return Answer(200, self.objects[key])
        names = sorted(k for k in self.objects if k.startswith(query.get("prefix", "")))
        start = int(query.get("continuation-token", "0"))
        chunk = names[start:start + self.page]
        more = start + self.page < len(names)
        body = '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">' + "".join(
            f"<Contents><Key>{k}</Key><Size>{len(self.objects[k])}</Size></Contents>" for k in chunk
        ) + f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>"
        if more:
            body += f"<NextContinuationToken>{start + self.page}</NextContinuationToken>"
        body += "</ListBucketResult>"
        return Answer(200, body.encode())


class Answer:
    def __init__(self, status, content=b""):
        self.status_code, self.content, self.reason = status, content, "fake"

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def close(self):
        pass


@pytest.fixture
def bucket(monkeypatch):
    fake = FakeBucket()
    monkeypatch.setattr(s3_backup.requests, "request", fake)
    for key, value in {"S3_BACKUP_ENDPOINT": "https://s3.example.com", "S3_BACKUP_BUCKET": "backups",
                       "S3_BACKUP_ACCESS_KEY": ACCESS, "S3_BACKUP_SECRET_KEY": SECRET,
                       "S3_BACKUP_PREFIX": "lan/"}.items():
        monkeypatch.setenv(key, value)
    return fake


def test_signature_matches_the_aws_example():
    # The GET Object example from the AWS Signature Version 4 documentation.
    empty = hashlib.sha256(b"").hexdigest()
    auth = s3_backup.sign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {},
                          {"range": "bytes=0-9", "x-amz-content-sha256": empty, "x-amz-date": "20130524T000000Z"},
                          empty, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
                          "20130524T000000Z")
    assert auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    listing = s3_backup.sign("GET", "examplebucket.s3.amazonaws.com", "/", {"max-keys": "2", "prefix": "J"},
                             {"x-amz-content-sha256": empty, "x-amz-date": "20130524T000000Z"},
                             empty, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
                             "20130524T000000Z")
    assert listing.endswith("Signature=34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7")


def test_where_aws_and_other_stores(monkeypatch):
    s = {"endpoint": "", "region": "eu-central-1", "bucket": "backups"}
    assert s3_backup._where(s, "a/b.json.gz") == (
        "https://backups.s3.eu-central-1.amazonaws.com", "backups.s3.eu-central-1.amazonaws.com", "/a/b.json.gz")
    assert s3_backup._where({**s, "bucket": "my.backups"}, "x")[2] == "/my.backups/x"
    assert s3_backup._where({**s, "endpoint": "http://minio.example.com:9000"}, "x") == (
        "http://minio.example.com:9000", "minio.example.com:9000", "/backups/x")


def test_pack_and_unpack_with_and_without_a_passphrase():
    backup = {"format": "floorbit-backup", "layout": {"note": "ü" * 1000}}
    plain = s3_backup.pack(backup)
    assert s3_backup.unpack(plain) == backup
    sealed = s3_backup.pack(backup, "correct horse")
    assert sealed.startswith(s3_backup.MAGIC) and b"floorbit-backup" not in sealed
    assert s3_backup.unpack(sealed, "correct horse") == backup
    with pytest.raises(s3_backup.S3Error, match="does not open"):
        s3_backup.unpack(sealed, "wrong")
    with pytest.raises(s3_backup.S3Error, match="encrypted"):
        s3_backup.unpack(sealed)
    with pytest.raises(s3_backup.S3Error, match="not a Floorbit backup"):
        s3_backup.unpack(b"hello")


def test_not_configured_says_so(client, monkeypatch):
    monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
    info = client.get("/api/settings/backup/s3").get_json()
    assert info["configured"] is False and info["backups"] == []
    resp = client.post("/api/settings/backup/s3")
    assert resp.status_code == 400 and "bucket" in resp.get_json()["error"]


def test_back_up_now_lists_and_restores(client, bucket):
    sw = client.post("/api/switches", json={"name": "sw-demo-01", "x": 10, "y": 20}).get_json()
    done = client.post("/api/settings/backup/s3")
    assert done.status_code == 200, done.get_json()
    name = done.get_json()["name"]
    assert re.match(r"^floorbit-backup-\d{8}-\d{6}Z\.json\.gz$", name)
    assert list(bucket.objects) == ["lan/" + name]

    bucket.objects["lan/notes.txt"] = b"someone else's file"
    info = client.get("/api/settings/backup/s3").get_json()
    assert [b["name"] for b in info["backups"]] == [name]
    assert info["last"]["ok"] is True and info["encrypted"] is False

    client.delete(f"/api/switches/{sw['id']}")
    resp = client.post("/api/settings/backup/s3/restore", json={"key": "lan/" + name})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["restored"]["inventory"] == 1

    got = client.get("/api/settings/backup/s3/download", query_string={"key": "lan/" + name})
    assert got.status_code == 200 and got.get_json()["format"] == "floorbit-backup"
    assert 'filename="floorbit-backup-' in got.headers["Content-Disposition"]


def test_only_listed_backups_can_be_fetched(client, bucket):
    bucket.objects["lan/notes.txt"] = b"x"
    for key in ("lan/notes.txt", "other/floorbit-backup-20261118-070000Z.json.gz", "../x", None):
        resp = client.post("/api/settings/backup/s3/restore", json={"key": key})
        assert resp.status_code == 400
    assert not any(m == "GET" and "notes" in p for m, p, _ in bucket.calls)


def test_encrypted_with_passphrase(client, bucket, monkeypatch):
    monkeypatch.setenv("S3_BACKUP_PASSPHRASE", "correct horse")
    name = client.post("/api/settings/backup/s3").get_json()["name"]
    assert name.endswith(".json.gz.enc")
    assert bucket.objects["lan/" + name].startswith(s3_backup.MAGIC)
    assert client.post("/api/settings/backup/s3/restore", json={"key": "lan/" + name}).status_code == 200
    monkeypatch.setenv("S3_BACKUP_PASSPHRASE", "something else")
    resp = client.post("/api/settings/backup/s3/restore", json={"key": "lan/" + name})
    assert resp.status_code == 400 and "passphrase" in resp.get_json()["error"]


def test_retention_keeps_the_newest_and_pages_through_the_list(app_module, bucket, monkeypatch):
    bucket.page = 2
    monkeypatch.setenv("S3_BACKUP_KEEP", "3")
    with app_module.app.app_context():
        for hour in range(5):
            s3_backup.run("tester", now=1_800_000_000 + hour * 3600)
    first = s3_backup.name_for(1_800_000_000 + 2 * 3600, False)
    assert sorted(bucket.objects)[0] == "lan/" + first and len(bucket.objects) == 3
    bucket.objects["lan/keep-me.txt"] = b"x"
    with app_module.app.app_context():
        s3_backup.run("tester", now=1_800_000_000 + 9 * 3600)
    assert "lan/keep-me.txt" in bucket.objects and len(bucket.objects) == 4


def test_bucket_errors_are_reported_and_noted(client, bucket):
    bucket.fail = 403
    resp = client.post("/api/settings/backup/s3")
    assert resp.status_code == 502 and "403: AccessDenied" in resp.get_json()["error"]
    info = client.get("/api/settings/backup/s3").get_json()
    assert info["last"]["ok"] is False and "AccessDenied" in info["error"]


def test_schedule():
    hour = 3600
    assert s3_backup.due(10 * hour, None, 24)
    assert not s3_backup.due(10 * hour, {"at": 0, "ok": True}, 0)
    assert not s3_backup.due(10 * hour, {"at": 0, "ok": True}, 24)
    assert s3_backup.due(24 * hour, {"at": 0, "ok": True}, 24)
    assert s3_backup.due(hour, {"at": 0, "ok": False}, 24)          # a failure is retried sooner
    assert not s3_backup.due(600, {"at": 0, "ok": False}, 24)
    assert s3_backup.due(0, {"at": 10 * hour, "ok": True}, 24)      # the clock went back


def test_tick_uploads_when_due(app_module, bucket):
    with app_module.app.app_context():
        assert s3_backup.tick(now=1_800_000_000)["name"]
        assert s3_backup.tick(now=1_800_000_000 + 60) is None
        assert s3_backup.tick(now=1_800_000_000 + 25 * 3600)["name"]
    assert len(bucket.objects) == 2


def test_settings_check_the_names(monkeypatch, bucket):
    monkeypatch.setenv("S3_BACKUP_BUCKET", "Not_A_Bucket")
    with pytest.raises(s3_backup.S3Error, match="bucket name"):
        s3_backup.settings()
    monkeypatch.setenv("S3_BACKUP_BUCKET", "backups")
    monkeypatch.setenv("S3_BACKUP_PREFIX", "a/../b")
    with pytest.raises(s3_backup.S3Error, match="folder"):
        s3_backup.settings()
    monkeypatch.setenv("S3_BACKUP_PREFIX", "plain")
    assert s3_backup.settings()["prefix"] == "plain/"


def test_secrets_are_write_only_and_not_in_a_backup(client, bucket):
    saved = client.put("/api/settings", json={"integrations.s3_backup_secret_key": "very-secret-value"})
    assert saved.status_code == 200
    page = client.get("/api/settings").get_data(as_text=True)
    assert "very-secret-value" not in page
    assert "very-secret-value" not in client.get("/api/settings/backup").get_data(as_text=True)


def test_decrypt_command(tmp_path, monkeypatch):
    path = tmp_path / "floorbit-backup-20261118-070000Z.json.gz.enc"
    path.write_bytes(s3_backup.pack({"format": "floorbit-backup"}, "pw"))
    monkeypatch.setenv("S3_BACKUP_PASSPHRASE", "pw")
    assert s3_backup.main(["decrypt", str(path)]) == 0
    assert (tmp_path / "floorbit-backup-20261118-070000Z.json").read_text().startswith("{")


def test_answers_with_entities_are_refused(bucket, monkeypatch):
    bomb = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
            b'<ListBucketResult><Contents><Key>&a;</Key></Contents></ListBucketResult>')
    bucket_call = bucket.__call__

    def answer(method, url, **kwargs):
        bucket_call(method, url, **kwargs)
        return Answer(200, bomb)
    monkeypatch.setattr(s3_backup.requests, "request", answer)
    with pytest.raises(s3_backup.S3Error, match="does not read"):
        s3_backup.listing()


def test_error_code_only_passes_plain_codes():
    assert s3_backup._error_code(Answer(403, b"<Error><Code>AccessDenied</Code></Error>")) == "AccessDenied"
    assert s3_backup._error_code(Answer(403, b"<Error><Code>Go to evil.example now!</Code></Error>")) == "fake"
