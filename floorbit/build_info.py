"""Which Floorbit runs here: the release, the commit and when the image was built (the page footer).

The Docker image bakes them in at build time (``FLOORBIT_COMMIT``, ``FLOORBIT_BUILT``,
``FLOORBIT_RELEASE``, ``FLOORBIT_SOURCE``: build args in the Dockerfile, set by image.yml). A checkout
without them asks git once, so a dev server still shows its commit; without git it says nothing.
"""
import os
import re
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = 'https://github.com/bitsandbricks-ch/floorbit'
COMMIT_RE = re.compile(r'^[0-9a-f]{7,40}\Z')
RELEASE_RE = re.compile(r'^v?[0-9][0-9A-Za-z.+-]{0,39}\Z')
SOURCE_RE = re.compile(r'^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._-]+){1,3}\Z')


def _git(*args):
    try:
        out = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.stdout.strip()


def _when(value):
    """Seconds since the epoch from ``2026-11-19T07:30:00Z`` or a plain number; None for anything else."""
    value = (value or '').strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return int((d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp())


@lru_cache(maxsize=1)
def info():
    """``{"version", "release", "commit", "built", "source", "dev"}``; computed once per process,
    since none of it changes while the server runs."""
    version_file = ROOT / 'VERSION'
    version = version_file.read_text().strip() if version_file.is_file() else '0'
    commit = os.environ.get('FLOORBIT_COMMIT', '').strip().lower()
    built = _when(os.environ.get('FLOORBIT_BUILT'))
    dev = not commit
    if dev:
        # A checkout, not an image: the commit it sits on, and its time as the best "built" we have.
        commit = _git('rev-parse', 'HEAD').lower()
        built = built or _when(_git('show', '-s', '--format=%ct', 'HEAD'))
    release = os.environ.get('FLOORBIT_RELEASE', '').strip()
    source = os.environ.get('FLOORBIT_SOURCE', '').strip().rstrip('/') or DEFAULT_SOURCE
    return {
        'version': version,
        # Only a tagged image is a release; a master image says which commit it is instead.
        'release': release.removeprefix('v') if RELEASE_RE.match(release) else None,
        'commit': commit if COMMIT_RE.match(commit) else None,
        'built': built,
        'source': source if SOURCE_RE.match(source) else DEFAULT_SOURCE,
        'dev': dev,
    }
