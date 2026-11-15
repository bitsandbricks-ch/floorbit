# Feature switches

Issue #114. Not every event uses everything. An admin turns whole features off under
**Settings > Features** (`/settings/features`).

## What "off" means

- **Menus:** the feature's links leave the floor plan's toolbar, the Settings page and the buttons on
  other pages.
- **Pages and API:** they answer 404 (`{"error": "This feature is turned off."}` for the API), for
  everybody. That includes public pages like the seat helpdesk.
- **Background work stops:**
  - the electrics, security and service health watches stop polling;
  - the NetFlow collector still reads packets, but drops them. It checks the switch every 30 seconds.
- **Nothing is deleted.** Turn the feature back on and its data is still there.

Some features build on others. When **Incidents** is off, so are the helpdesk, tech dispatch and the
shift handover. **Past events** needs the **event report**. The page says why such a feature is off.

| Feature | Owns |
| --- | --- |
| `incidents` | `/incidents`, `/api/incidents` |
| `helpdesk` | `/help`, `/api/helpdesk`, `/incidents/qr` |
| `dispatch` | `/jobs`, `/api/jobs`, `/api/dispatch` |
| `handover` | `/handover`, `/api/handover` |
| `gear` | `/gear`, `/api/gear` |
| `health` | `/health`, `/api/health` (not `/healthz`) |
| `dashboard` | `/dashboard`, `/api/dashboard` |
| `traffic` | `/traffic`, `/api/flows`, the NetFlow collector |
| `security` | `/security`, `/api/security` |
| `ports` | `/api/ports` (port actions on the floor plan) |
| `power` | `/power`, `/api/power` |
| `tournament` | `/tournament`, `/api/tournament` |
| `replay` | `/replay`, `/api/replay` |
| `report` | `/report`, `/api/report` |
| `past_events` | `/events`, `/api/past-events` |
| `planner` | `/planner`, `/api/planner` |
| `preflight` | `/preflight`, `/api/preflight` |
| `teardown` | `/teardown`, `/api/teardown` |
| `public_hall` | `/hall`, `/api/public` |

The floor plan, inventory, seats, stats, problems, settings and sign-in are the core and are always on.

## Forcing a feature off on the server

```sh
FLOORBIT_FEATURES_OFF=traffic,ports
```

Features listed there are off whatever the settings page says, and the page can't turn them on. Use
it for setups that should never offer a feature.

## Who and where

- Changing the switches needs **Change settings** (admins). Every change goes to the audit log as
  "Turned features on or off", naming what changed.
- `GET /api/features` returns `{"off": [...]}` to anyone who sees the floor plan; the menus use it.
- The switches are kept in data.json under `features`. Only what was turned off is stored, so a
  feature added in an update starts on.

## Adding a feature

Add it to `FEATURES` in `floorbit/features.py`: an id, the paths it owns, and the features it needs.
Then:

- give it a name and a description in `frontend/src/i18n/*/features.json`;
- wrap its links in `useFeature('<id>')` (React) or `feature_on('<id>')` (Jinja);
- have its background loop ask `features.on('<id>')` before polling.
