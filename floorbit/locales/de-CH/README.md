# Server German, one file per area

The German for the server's messages lives here, one file per area of the code, named after the
module that sends the message (`floorbit/blueprints/cables.py` → `cables.json`,
`floorbit/telemetry/…` → `telemetry.json`, `auth/…` → `auth.json`). Texts used by several areas,
or by none the split could find, are in `shared.json`.

Format: `{"English text as in the code": "Swiss German text"}`, `{}` where a value goes; the German
may reorder values with `{1}`, `{2}`. No "ß".

Why: when every pull request added its lines to one big `de-CH.json`, two pull requests that ran at
the same time almost always conflicted there (issue #1230). Files per area rarely meet.

`floorbit/i18n.py` loads every `*.json` here. A text may be in one file only, and the old single file
may not come back (`tests/test_i18n_server.py` checks). A branch that still added to `de-CH.json`:
merge `master`, keep its `de-CH.json` and run `python scripts/split_locales.py`, which moves those
texts here. The audit log's German works the same way in `../log.de-CH/`.
