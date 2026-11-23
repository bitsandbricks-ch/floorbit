#!/bin/sh
# Once per clone: the merge driver that merges translation files by key (scripts/git-merge-json.py).
set -e
cd "$(dirname "$0")/.."
git config merge.json-texts.name "translation files, merged by key"
git config merge.json-texts.driver "python3 scripts/git-merge-json.py %O %A %B"
echo "Merge driver json-texts is set up."
