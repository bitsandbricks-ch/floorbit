### Added

- Plugins and a dashboard. A plugin is a folder with `plugin.yaml` and `plugin.py`. It can add
  settings, actions (audited, with a role), dashboard tiles, read-only endpoints and hooks on
  changes, and only the areas it lists under `uses:`. Settings > Plugins turns them on (all start
  off). Floorbit ships an HTTP check that shows whether your web services answer. Plugin state is
  kept in `plugins.json` next to `data.json` (`PLUGINS_FILE`; Compose puts it in the state volume).
