### Added

- Themes. Floorbit has a new look and logo, sibling to Seatbit: dark hall neutrals, Bit Green for
  actions, Trace Cyan for what you have selected, and the Geist fonts shipped with the app. Pick a
  preset under Settings > Appearance: Floorbit, Ops desk, Kiosk, Classic (the old orange look) or
  Custom with your event's accent, background, name and logo. Status colours never change with the
  theme.
- `?theme=<preset>` on any page sets the theme for that screen only and the browser remembers it,
  so the hall projector and the orga desk can each run their own. `/kiosk` uses the Kiosk preset by
  default.
- `FLOORBIT_THEME` and `FLOORBIT_EVENT_NAME` set the theme and event name from the environment.

### Changed

- Every page, including sign-in and check-in, now follows the theme and the light/dark switch.
