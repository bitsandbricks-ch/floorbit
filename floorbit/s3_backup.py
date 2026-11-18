"""Backups to an S3 bucket: AWS S3 or anything that speaks its API (MinIO, Garage, Backblaze B2, Wasabi,
Ceph). See docs/backup.md.

The file is the same backup as Settings > Backup and restore (blueprints/backup.py): the floor plan,
cabling, power and the settings, never secrets or accounts. It is gzipped and, with a passphrase set
(``S3_BACKUP_PASSPHRASE``), encrypted here before it leaves (AES-256-GCM, key from scrypt), so the
bucket's owner can't read it. Every ``S3_BACKUP_INTERVAL_HOURS`` the cluster's leader uploads one;
after each upload only the newest ``S3_BACKUP_KEEP`` stay. Admins also back up now, and restore or
download any listed one, on the Settings page.

Requests are signed with AWS Signature Version 4 by hand: boto3 would add 80 MB to the image for four
calls. They go through ``requests``, so the outbound checks (floorbit/outbound.py) apply as for any
URL an admin sets.
"""
import gzip
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import quote, urlsplit

import requests

from integrations import config

from . import store

NAME_RE = re.compile(r'^floorbit-backup-(\d{8})-(\d{6})Z\.json\.gz(\.enc)?\Z')
PREFIX_RE = re.compile(r'^[A-Za-z0-9._/-]{0,200}\Z')
BUCKET_RE = re.compile(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]\Z')
REGION_RE = re.compile(r'^[a-z0-9-]{1,40}\Z')
MAGIC = b'FLOORBIT-ENC1\n'          # an encrypted file starts with this, then salt and nonce
SCRYPT = {'n': 2 ** 15, 'r': 8, 'p': 1, 'maxmem': 64 * 1024 * 1024, 'dklen': 32}
TIMEOUT = 60
RETRY_AFTER = 15 * 60               # a failed scheduled upload is tried again after this long
_lock = threading.Lock()


class S3Error(RuntimeError):
    pass


# ── Settings ──────────────────────────────────────────────────────────────────
def settings():
    """The bucket settings, or S3Error naming what is missing or wrong."""
    s = {
        'endpoint': (config.get('S3_BACKUP_ENDPOINT') or '').strip().rstrip('/'),
        'region': (config.get('S3_BACKUP_REGION') or 'us-east-1').strip(),
        'bucket': (config.get('S3_BACKUP_BUCKET') or '').strip(),
        'prefix': (config.get('S3_BACKUP_PREFIX') or '').strip().lstrip('/'),
        'access_key': (config.get('S3_BACKUP_ACCESS_KEY') or '').strip(),
        'secret_key': (config.get('S3_BACKUP_SECRET_KEY') or '').strip(),
        'passphrase': config.get('S3_BACKUP_PASSPHRASE') or '',
    }
    if not (s['bucket'] and s['access_key'] and s['secret_key']):
        raise S3Error('Set the bucket, access key and secret key for S3 backups first.')
    if not BUCKET_RE.match(s['bucket']):
        raise S3Error('The bucket name is 3 to 63 lower-case letters, digits, . and -.')
    if not REGION_RE.match(s['region']):
        raise S3Error('The region is lower-case letters, digits and -, like eu-central-1.')
    if not PREFIX_RE.match(s['prefix']) or '..' in s['prefix']:
        raise S3Error('The folder in the bucket may only hold letters, digits, ., _, - and /.')
    if s['prefix'] and not s['prefix'].endswith('/'):
        s['prefix'] += '/'
    # Tenants on one platform may share a bucket (the same S3_BACKUP_* settings): each keeps its
    # backups in its own folder, so none lists, prunes or restores another's. The default tenant
    # keeps the folder as set, where its backups always were; the listing never reaches into
    # tenants/ below it (backup names hold no /).
    from . import store
    if store.tenant_dir():
        s['prefix'] += store.tenant_dir().rstrip('/') + '/'
    if s['endpoint']:
        parts = urlsplit(s['endpoint'])
        if parts.scheme not in ('http', 'https') or not parts.netloc or parts.query or parts.fragment:
            raise S3Error('The S3 endpoint is a URL like https://s3.example.com.')
    return s


def configured():
    try:
        settings()
    except S3Error:
        return False
    return True


def interval_hours():
    return min(config.get_int('S3_BACKUP_INTERVAL_HOURS', 24, minimum=0), 24 * 31)


def keep():
    return config.get_int('S3_BACKUP_KEEP', 30, minimum=1)


# ── Signing (AWS Signature Version 4) ─────────────────────────────────────────
def _hmac(key, text):
    return hmac.new(key, text.encode('utf-8'), hashlib.sha256).digest()


def _q(text):
    return quote(text, safe='-_.~')


def sign(method, host, path, query, headers, payload_hash, access_key, secret_key, region, amz_date):
    """The Authorization header for one request. ``path`` is already URI-encoded; ``headers`` holds
    every header that is signed (host, x-amz-date, x-amz-content-sha256 and any other)."""
    lower = {k.lower(): ' '.join(str(v).strip().split()) for k, v in {**headers, 'host': host}.items()}
    names = sorted(lower)
    canonical = '\n'.join([
        method, path,
        '&'.join(f'{_q(k)}={_q(v)}' for k, v in sorted(query.items())),
        ''.join(f'{n}:{lower[n]}\n' for n in names),
        ';'.join(names), payload_hash,
    ])
    day = amz_date[:8]
    scope = f'{day}/{region}/s3/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(('AWS4' + secret_key).encode('utf-8'), day), region), 's3'), 'aws4_request')
    signature = hmac.new(key, to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={";".join(names)}, Signature={signature}'


def _where(s, key=''):
    """(base URL, host, URI-encoded path) for an object (or the bucket with key '')."""
    if s['endpoint']:
        # MinIO, Garage and most others answer bucket names in the path.
        parts = urlsplit(s['endpoint'])
        base_path = parts.path.rstrip('/')
        path = f'{base_path}/{s["bucket"]}/' + quote(key, safe='/-_.~')
        return f'{parts.scheme}://{parts.netloc}', parts.netloc, path
    if '.' in s['bucket']:
        # A dotted name doesn't match the wildcard certificate as a host name.
        host = f's3.{s["region"]}.amazonaws.com'
        return f'https://{host}', host, f'/{s["bucket"]}/' + quote(key, safe='/-_.~')
    host = f'{s["bucket"]}.s3.{s["region"]}.amazonaws.com'
    return f'https://{host}', host, '/' + quote(key, safe='/-_.~')


def _request(s, method, key='', query=None, body=b'', stream=False):
    query = query or {}
    base, host, path = _where(s, key)
    payload_hash = hashlib.sha256(body).hexdigest()
    amz_date = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    headers = {'x-amz-date': amz_date, 'x-amz-content-sha256': payload_hash}
    headers['Authorization'] = sign(method, host, path, query, headers, payload_hash,
                                    s['access_key'], s['secret_key'], s['region'], amz_date)
    url = base + path + ('?' + '&'.join(f'{_q(k)}={_q(v)}' for k, v in sorted(query.items())) if query else '')
    try:
        resp = requests.request(method, url, data=body or None, headers={**headers, 'Host': host},
                                timeout=TIMEOUT, stream=stream, allow_redirects=False)
    except requests.RequestException as exc:
        raise S3Error(f'The S3 endpoint does not answer: {type(exc).__name__}') from None
    if resp.status_code >= 300:
        raise S3Error(f'The bucket answered {resp.status_code}: {_error_code(resp)}')
    return resp


def _error_code(resp):
    code = _tag(resp.content[:16384].decode('utf-8', 'replace'), 'Code')
    return code if code and re.fullmatch(r'[A-Za-z0-9.]{1,80}', code) else (resp.reason or 'error')[:80]


# S3's answers are small and flat. They are read with a few patterns instead of an XML parser, so a
# hostile endpoint has no entities to expand: a document that declares any is refused outright.
def _tags(text, name):
    return [html.unescape(v) for v in re.findall(rf'<{name}>([^<]*)</{name}>', text)]


def _tag(text, name):
    found = _tags(text, name)
    return found[0] if found else None


def _answer(content):
    text = content.decode('utf-8', 'replace')
    if '<!' in text:
        raise S3Error('The S3 endpoint sent an answer Floorbit does not read.')
    return text


# ── Files ─────────────────────────────────────────────────────────────────────
def _key(passphrase, salt):
    return hashlib.scrypt(passphrase.encode('utf-8'), salt=salt, **SCRYPT)


def pack(backup, passphrase=''):
    """The backup as gzipped JSON, encrypted when there is a passphrase."""
    raw = gzip.compress(json.dumps(backup, separators=(',', ':')).encode('utf-8'), compresslevel=6, mtime=0)
    if not passphrase:
        return raw
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    return MAGIC + salt + nonce + AESGCM(_key(passphrase, salt)).encrypt(nonce, raw, MAGIC)


def unpack(blob, passphrase=''):
    """The backup from a file ``pack`` made."""
    from .blueprints.backup import MAX_BYTES
    if blob.startswith(MAGIC):
        if not passphrase:
            raise S3Error('This backup is encrypted: set the passphrase it was made with.')
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        head = len(MAGIC)
        salt, nonce, sealed = blob[head:head + 16], blob[head + 16:head + 28], blob[head + 28:]
        try:
            blob = AESGCM(_key(passphrase, salt)).decrypt(nonce, sealed, MAGIC)
        except InvalidTag:
            raise S3Error('This backup does not open with the passphrase set now.') from None
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as f:
            raw = f.read(MAX_BYTES + 1)
    except (OSError, EOFError):
        raise S3Error('This file in the bucket is not a Floorbit backup.') from None
    if len(raw) > MAX_BYTES:
        raise S3Error('This backup is larger than a backup can be.')
    try:
        return json.loads(raw)
    except ValueError:
        raise S3Error('This file in the bucket is not a Floorbit backup.') from None


def name_for(now, encrypted):
    return time.strftime('floorbit-backup-%Y%m%d-%H%M%SZ.json.gz', time.gmtime(now)) + ('.enc' if encrypted else '')


# ── Bucket ────────────────────────────────────────────────────────────────────
def listing(s=None):
    """Floorbit's backups in the bucket folder, newest first. Other files there are left out."""
    s = s or settings()
    out, token = [], None
    for _ in range(100):   # 100,000 objects: far past any retention
        query = {'list-type': '2', 'prefix': s['prefix']}
        if token:
            query['continuation-token'] = token
        text = _answer(_request(s, 'GET', query=query).content)
        for item in re.findall(r'<Contents>(.*?)</Contents>', text, re.S):
            key = _tag(item, 'Key') or ''
            name = key[len(s['prefix']):]
            m = NAME_RE.match(name) if key.startswith(s['prefix']) else None
            if not m:
                continue
            size = _tag(item, 'Size') or '0'
            out.append({'key': key, 'name': name, 'size': int(size) if size.isdigit() else 0,
                        'made': _made(m), 'encrypted': bool(m.group(3))})
        token = _tag(text, 'NextContinuationToken')
        if (_tag(text, 'IsTruncated') or '').lower() != 'true' or not token:
            break
    return sorted(out, key=lambda b: b['name'], reverse=True)


def _made(m):
    d, t = m.group(1), m.group(2)
    return f'{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}Z'


def _checked_key(s, key):
    key = str(key or '')
    if not key.startswith(s['prefix']) or not NAME_RE.match(key[len(s['prefix']):]):
        raise S3Error('That is not one of the backups in the bucket.')
    return key


def fetch(key, s=None):
    from .blueprints.backup import MAX_BYTES
    s = s or settings()
    key = _checked_key(s, key)
    resp = _request(s, 'GET', key, stream=True)
    blob = bytearray()
    for chunk in resp.iter_content(1024 * 1024):
        blob += chunk
        if len(blob) > MAX_BYTES:
            resp.close()
            raise S3Error('This backup is larger than a backup can be.')
    return unpack(bytes(blob), s['passphrase'])


def _state_path():
    return store.event_path('s3-backup.json')


def state():
    found = store.read_json(_state_path())
    return found if isinstance(found, dict) else {}


def run(by, now=None):
    """Upload a backup of the current event now, then drop the oldest beyond ``keep()``."""
    from .blueprints.backup import make_backup
    now = time.time() if now is None else now
    s = settings()
    if not _lock.acquire(timeout=TIMEOUT * 2):
        raise S3Error('Another backup is being uploaded; try again shortly.')
    try:
        body = pack(make_backup(store.load_data()), s['passphrase'])
        name = name_for(now, bool(s['passphrase']))
        try:
            _request(s, 'PUT', s['prefix'] + name, body=body)
        except S3Error as exc:
            _note(now, by, ok=False, error=str(exc))
            raise
        removed = prune(s)
        _note(now, by, ok=True, name=name, size=len(body), removed=len(removed))
        return {'name': name, 'size': len(body), 'encrypted': bool(s['passphrase']), 'removed': removed}
    finally:
        _lock.release()


def prune(s):
    """Delete Floorbit's backups beyond the newest ``keep()``. Returns the names deleted."""
    gone = []
    for old in listing(s)[keep():]:
        try:
            _request(s, 'DELETE', old['key'])
            gone.append(old['name'])
        except S3Error as exc:   # the next run tries again
            print(f'[s3-backup] could not delete {old["name"]}: {exc}')
    return gone


def _note(now, by, **result):
    entry = {'at': now, 'by': by, **result}
    found = state()
    found['last'] = entry
    if result.get('ok'):
        found['last_ok'] = entry
    try:
        store.write_json(_state_path(), found)
    except Exception as exc:  # noqa: BLE001  # the upload itself worked
        print(f'[s3-backup] could not note the run: {exc}')


# ── Schedule ──────────────────────────────────────────────────────────────────
SCHEDULED_USER = 'scheduled backup'


def due(now, last, hours):
    """Is a scheduled upload due? ``last`` is the state's last run (ok or not)."""
    if hours <= 0:
        return False
    if not last or not isinstance(last.get('at'), (int, float)):
        return True
    since = now - last['at']
    if since < 0:              # the clock went back: start counting again
        return True
    return since >= (hours * 3600 if last.get('ok') else min(hours * 3600, RETRY_AFTER))


def tick(now=None):
    """One look at the schedule. Returns the run's result, or None when nothing was due."""
    from . import audit
    now = time.time() if now is None else now
    if not configured() or not due(now, state().get('last'), interval_hours()):
        return None
    try:
        result = run(SCHEDULED_USER, now)
    except S3Error as exc:
        audit.record('settings', 'Uploaded a backup to S3', user=SCHEDULED_USER, ok=False)
        print(f'[s3-backup] scheduled upload failed: {exc}')
        return None
    audit.record('settings', 'Uploaded a backup to S3', user=SCHEDULED_USER, target=result['name'])
    return result


def _loop(app, stop):
    from . import cluster
    while not stop.wait(60):
        try:
            if cluster.leading():   # several pods upload once
                with app.app_context():
                    tick()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad upload
            print(f'[s3-backup] scheduled upload failed: {exc}')


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='s3-backup', daemon=True).start()
    return stop


def main(argv):
    """``python -m floorbit.s3_backup decrypt <file> [<out>]``: open a downloaded backup without a
    running Floorbit. The passphrase comes from S3_BACKUP_PASSPHRASE or is asked for."""
    if len(argv) < 2 or argv[0] != 'decrypt':
        print('usage: python -m floorbit.s3_backup decrypt <file> [<out.json>]')
        return 2
    with open(argv[1], 'rb') as f:
        blob = f.read()
    passphrase = os.environ.get('S3_BACKUP_PASSPHRASE') or ''
    if blob.startswith(MAGIC) and not passphrase:
        import getpass
        passphrase = getpass.getpass('Passphrase: ')
    backup = unpack(blob, passphrase)
    out = argv[2] if len(argv) > 2 else argv[1].removesuffix('.enc').removesuffix('.gz')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(backup, f, indent=2)
    print(f'Wrote {out}. Restore it on Settings > Backup and restore.')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
