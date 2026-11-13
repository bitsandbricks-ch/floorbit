#!/bin/sh
# Check that a release tag matches VERSION and write that version's CHANGELOG.md section to
# the file given (for the release job in .github/workflows/ci.yml).
#   sh scripts/release-notes.sh v1.2.0 notes.md
set -eu
tag=${1:?tag}
out=${2:?output file}
version=$(tr -d ' \n' < VERSION)
if [ "$tag" != "v$version" ]; then
  echo "tag $tag doesn't match VERSION ($version): expected v$version. Bump first (mason bump)." >&2
  exit 1
fi
awk -v v="$version" '
  /^## / { if (found) exit; if (index($0, "[" v "]") || $2 == v) { found = 1; next } }
  found { print }' CHANGELOG.md > "$out"
if ! grep -q '[^[:space:]]' "$out"; then
  echo "Release $tag." > "$out"
fi
