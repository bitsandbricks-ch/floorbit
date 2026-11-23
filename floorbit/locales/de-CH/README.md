# Server German, one file per area

New German for the server's messages goes here, not into `../de-CH.json`: one file per area of the
code, named after the module that sends the message (`floorbit/blueprints/cables.py` →
`cables.json`, `floorbit/telemetry/…` → `telemetry.json`). The format is the same:
`{"English text as in the code": "Swiss German text"}`, `{}` where a value goes.

Why: when every pull request adds its lines to the one big `de-CH.json`, two pull requests
that run at the same time almost always conflict there. Files per area rarely meet.

`floorbit/i18n.py` loads `../de-CH.json` and then every `*.json` here. A text may be in one file
only (`tests/test_i18n_server.py` checks). `log.de-CH.json` and `discord.de-CH.json` work the same
way, with a `log.de-CH/` and a `discord.de-CH/` folder.

`../de-CH.json` keeps its texts until the pull requests that still add to it are merged; then they
move here too (issue #1230).
