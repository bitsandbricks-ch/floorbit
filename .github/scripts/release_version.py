#!/usr/bin/env python3
"""Check that a release tag matches the repo's version file; print version=<v> for $GITHUB_OUTPUT.

Reads [release] from .mason.toml (version file and tag pattern, the same keys mason bump and
mason release use) and finds the version in it: VERSION, pyproject.toml, package.json,
plugin.yaml, Cargo.toml or a Python file with __version__.
"""
import json
import re
import sys
import tomllib
from pathlib import Path

tag = sys.argv[1]
release = {}
if Path(".mason.toml").exists():
    release = tomllib.loads(Path(".mason.toml").read_text()).get("release", {})
path = Path(release.get("version", "VERSION"))
pattern = release.get("tag", "v{version}")
text = path.read_text()

if path.name == "package.json":
    version = json.loads(text)["version"]
elif path.suffix == ".toml":
    data = tomllib.loads(text)
    version = (data.get("project") or data.get("package") or data.get("tool", {}).get("poetry") or {})["version"]
else:
    m = re.search(r"""(?m)^(?:__version__\s*=\s*|version\s*[:=]\s*)?["']?(\d+\.\d+\.\d+[^"'\s]*)""", text)
    if not m:
        sys.exit(f"no version found in {path}")
    version = m.group(1)

want = pattern.format(version=version)
if tag != want:
    sys.exit(f"tag {tag} doesn't match {path} ({version}): expected {want}. Bump first (mason bump).")
print(f"version={version}")
