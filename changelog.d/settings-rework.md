### Changed

- Settings is no longer one long scroll. A list of sections on the side (Event and look, Sources,
  Monitoring, Alerts and Discord, Sign-in and switches) opens one section at a time at its own
  address, such as `/settings/netbox`, and a search box finds any setting by its name, help text or
  environment variable. Unsaved changes stay while you move between sections.
- Plugin settings moved from the Settings page to the plugins: Settings > Plugins lists every
  plugin with its version and an on/off switch, with search and an On/Off filter once the list is
  long, and each plugin has its own page (`/settings/plugins/<id>`) with its test, actions, log and
  settings.
