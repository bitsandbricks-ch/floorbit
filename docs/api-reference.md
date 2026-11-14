# API reference

<!-- Written by scripts/api_reference.py from the app's routes. Don't edit by hand: run the script. -->

Every `/api/` endpoint, the permission it needs and the feature it belongs to. How to sign in with a
token, the version promise and webhooks are in [api.md](api.md). What an endpoint takes and answers is
at the top of the module that serves it. A request a role can't make answers 403; an endpoint whose
feature is turned off answers 404 ([features.md](features.md)).

## auth

Sign-in for the floor plan.

Source: [`auth/__init__.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/auth/__init__.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/auth/me` | anyone |  |

## auth.admin

Account management: the /settings/users page, roles and teams, and their API.

Source: [`auth/admin.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/auth/admin.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/roles` | `accounts.manage` |  |
| DELETE | `/api/roles/<role_id>` | `accounts.manage` |  |
| PUT | `/api/roles/<role_id>` | `accounts.manage` |  |
| GET | `/api/settings/oidc` | `settings.manage` |  |
| DELETE | `/api/settings/oidc/<provider_id>` | `settings.manage` |  |
| PUT | `/api/settings/oidc/<provider_id>` | `settings.manage` |  |
| POST | `/api/settings/oidc/<provider_id>/test` | `settings.manage` |  |
| GET | `/api/teams` | `accounts.manage` |  |
| POST | `/api/teams` | `accounts.manage` |  |
| DELETE | `/api/teams/<team_id>` | `accounts.manage` |  |
| PATCH | `/api/teams/<team_id>` | `accounts.manage` |  |
| DELETE | `/api/teams/<team_id>/members/<username>` | `accounts.manage` |  |
| PUT | `/api/teams/<team_id>/members/<username>` | `accounts.manage` |  |
| GET | `/api/users` | `accounts.manage` |  |
| POST | `/api/users` | `accounts.manage` |  |
| DELETE | `/api/users/<username>` | `accounts.manage` |  |
| PATCH | `/api/users/<username>` | `accounts.manage` |  |

## floorbit.blueprints.api_tokens

API tokens and the API's version (issue #40). Rules in auth/tokens.py, docs in docs/api.md.

Source: [`floorbit/blueprints/api_tokens.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/api_tokens.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/settings/api-tokens` | `settings.manage` |  |
| POST | `/api/settings/api-tokens` | `settings.manage` |  |
| DELETE | `/api/settings/api-tokens/<token_id>` | `settings.manage` |  |
| GET | `/api/version` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.attendee

The public attendee view (issue #19). See docs/kiosk.md.

Source: [`floorbit/blueprints/attendee.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/attendee.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/public/seats` | anyone | `public_hall` |

## floorbit.blueprints.audit

Settings > Audit log: the page, its JSON and a CSV download (admins only, under /settings).

Source: [`floorbit/blueprints/audit.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/audit.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/settings/audit` | `audit.read` |  |
| GET | `/api/settings/audit.csv` | `settings.manage` |  |

## floorbit.blueprints.backup

Backup and restore of the floor plan and settings (Settings > Backup).

Source: [`floorbit/blueprints/backup.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/backup.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/settings/backup` | `settings.manage` |  |
| POST | `/api/settings/backup` | `settings.manage` |  |

## floorbit.blueprints.brackets

Tournament brackets (issue #107). The rules live in floorbit/brackets.py; see docs/tournament.md.

Source: [`floorbit/blueprints/brackets.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/brackets.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/tournament/brackets` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `tournament` |
| POST | `/api/tournament/brackets` | `floorplan.edit` | `tournament` |
| DELETE | `/api/tournament/brackets/<bracket_id>` | `floorplan.edit` | `tournament` |
| PATCH | `/api/tournament/brackets/<bracket_id>` | `floorplan.edit` | `tournament` |
| PATCH | `/api/tournament/brackets/<bracket_id>/matches/<match_id>` | `floorplan.edit` | `tournament` |
| POST | `/api/tournament/brackets/import` | `floorplan.edit` | `tournament` |

## floorbit.blueprints.cables

Cables and patching (issue #97). The rules live in floorbit/cables.py.

Source: [`floorbit/blueprints/cables.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/cables.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/cables` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `cables` |
| POST | `/api/cables` | `floorplan.edit` | `cables` |
| GET | `/api/cables.csv` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `cables` |
| DELETE | `/api/cables/<cable_id>` | `floorplan.edit` | `cables` |
| PATCH | `/api/cables/<cable_id>` | `floorplan.edit` | `cables` |
| POST | `/api/cables/import` | `floorplan.edit` | `cables` |
| GET | `/api/cables/labels.pdf` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `cables` |

## floorbit.blueprints.cache

Inspect and clear the Redis cache of LibreNMS answers.

Source: [`floorbit/blueprints/cache.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/cache.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| POST | `/api/cache/invalid` | `floorplan.edit` |  |
| GET | `/api/cache/stats` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.commands

Switch commands (issue #94). The rules live in floorbit/commands.py.

Source: [`floorbit/blueprints/commands.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/commands.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/commands` | `ports.act` | `commands` |
| POST | `/api/commands/run` | `ports.act` | `commands` |
| DELETE | `/api/commands/templates/<tid>` | `settings.manage` | `commands` |
| PUT | `/api/commands/templates/<tid>` | `settings.manage` | `commands` |

## floorbit.blueprints.config

What the browser needs to know about the server: which integrations are on, display defaults.

Source: [`floorbit/blueprints/config.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/config.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/config` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.crew

Buttons in the crew's Discord channel (issue #32). The bridge itself is integrations/crew.py.

Source: [`floorbit/blueprints/crew.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/crew.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| POST | `/api/discord/interactions` | anyone |  |

## floorbit.blueprints.demo

Demo mode: the built-in ``demo`` plugin's made-up data, laid out on an empty floor plan.

Source: [`floorbit/blueprints/demo.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/demo.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| POST | `/api/demo/layout` | `settings.manage` |  |

## floorbit.blueprints.dispatch

Tech dispatch (issue #30). Rules live in floorbit/dispatch.py; see docs/dispatch.md.

Source: [`floorbit/blueprints/dispatch.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/dispatch.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/dispatch/crew` | `incidents.assign` | `dispatch` |
| POST | `/api/incidents/<incident_id>/dispatch` | `floorplan.view` | `incidents` |
| GET | `/api/jobs` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `dispatch` |
| POST | `/api/jobs/<incident_id>/done` | `floorplan.view` | `dispatch` |
| POST | `/api/jobs/<incident_id>/give-back` | `floorplan.view` | `dispatch` |
| POST | `/api/jobs/<incident_id>/take` | `floorplan.view` | `dispatch` |
| PUT | `/api/jobs/me` | `floorplan.view` | `dispatch` |

## floorbit.blueprints.dns

DNS analytics (issue #87): what the hall looks up. Counting lives in floorbit/dns.py.

Source: [`floorbit/blueprints/dns.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/dns.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/dns` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `dns` |

## floorbit.blueprints.features

Feature switches (issue #114). Rules in floorbit/features.py.

Source: [`floorbit/blueprints/features.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/features.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/features` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/settings/features` | `settings.manage` |  |
| PUT | `/api/settings/features` | `settings.manage` |  |

## floorbit.blueprints.flows

Traffic insights from NetFlow and IPFIX (issue #25). See docs/flows.md.

Source: [`floorbit/blueprints/flows.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/flows.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/flows` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `traffic` |

## floorbit.blueprints.games

Game and launcher insights (issue #88). The numbers come from floorbit/games.py.

Source: [`floorbit/blueprints/games.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/games.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/games` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `games` |

## floorbit.blueprints.gear

Gear loans (issue #36). Rules in floorbit/gear.py.

Source: [`floorbit/blueprints/gear.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/gear.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/gear` | `incidents.work` | `gear` |
| POST | `/api/gear/<device_id>/in` | `incidents.work` | `gear` |
| POST | `/api/gear/<device_id>/out` | `incidents.work` | `gear` |
| GET | `/api/gear/labels.pdf` | `incidents.work` | `gear` |

## floorbit.blueprints.halls

Halls (or floors), each with its own floor plan (issue #20). Rules live in floorbit/halls.py.

Source: [`floorbit/blueprints/halls.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/halls.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/halls` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/halls` | `floorplan.edit` |  |
| DELETE | `/api/halls/<hall_id>` | `floorplan.edit` |  |
| PUT | `/api/halls/<hall_id>` | `floorplan.edit` |  |
| DELETE | `/api/halls/<hall_id>/background` | `floorplan.edit` |  |
| GET | `/api/halls/<hall_id>/background` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| PUT | `/api/halls/<hall_id>/background` | `floorplan.edit` |  |
| POST | `/api/halls/<hall_id>/seat-blocks.csv` | `floorplan.edit` |  |

## floorbit.blueprints.handover

Shift handover (issue #33). Rules in floorbit/handover.py.

Source: [`floorbit/blueprints/handover.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/handover.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/handover` | `incidents.work` | `handover` |
| POST | `/api/handover` | `incidents.work` | `handover` |

## floorbit.blueprints.health

The service health wall (issue #28). The checks come from health plugins (floorbit/health.py).

Source: [`floorbit/blueprints/health.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/health.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/health` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `health` |
| POST | `/api/health/check` | `plugins.run` | `health` |

## floorbit.blueprints.incidents

Incident board and the seat QR helpdesk (issue #27). Rules live in floorbit/incidents.py.

Source: [`floorbit/blueprints/incidents.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/incidents.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/helpdesk/qr` | `incidents.assign` | `helpdesk` |
| GET | `/api/incidents` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `incidents` |
| POST | `/api/incidents` | `floorplan.view` | `incidents` |
| PATCH | `/api/incidents/<incident_id>` | `floorplan.view` | `incidents` |
| GET | `/api/incidents/markers` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `incidents` |
| GET | `/api/incidents/people` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `incidents` |

## floorbit.blueprints.inventory

The inventory API and page (floorbit/inventory.py has the rules).

Source: [`floorbit/blueprints/inventory.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/inventory.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/inventory` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/inventory` | `floorplan.edit` |  |
| DELETE | `/api/inventory/<device_id>` | `floorplan.edit` |  |
| PATCH | `/api/inventory/<device_id>` | `floorplan.edit` |  |
| GET | `/api/inventory/log` | `floorplan.edit` |  |
| POST | `/api/inventory/sync` | `floorplan.edit` |  |

## floorbit.blueprints.layout_templates

The floor plan template library (issue #48). Rules live in floorbit/layout_templates.py.

Source: [`floorbit/blueprints/layout_templates.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/layout_templates.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/templates` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/templates` | `floorplan.edit` |  |
| DELETE | `/api/templates/<template_id>` | `floorplan.edit` |  |
| PATCH | `/api/templates/<template_id>` | `floorplan.edit` |  |
| POST | `/api/templates/<template_id>/apply` | `floorplan.edit` |  |
| POST | `/api/templates/<template_id>/duplicate` | `floorplan.edit` |  |
| GET | `/api/templates/<template_id>/export` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/templates/<template_id>/versions` | `floorplan.edit` |  |
| POST | `/api/templates/import` | `floorplan.edit` |  |

## floorbit.blueprints.logs

Logs (issue #91): what switches, firewalls and DHCP servers sent by syslog. Receiving and keeping lives in floorbit/syslog.py.

Source: [`floorbit/blueprints/logs.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/logs.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/logs` | `seats.view` | `syslog` |
| GET | `/api/logs/alerts` | `seats.view` | `syslog` |
| GET | `/api/logs/markers` | `seats.view` | `syslog` |

## floorbit.blueprints.network

Live network data: switch status, IP to switch port, the seat mapping and the seat heatmap.

Source: [`floorbit/blueprints/network.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/network.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/monitoring/health` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/resolve/<ip_address>` | `seats.view` |  |
| GET | `/api/seats/find` | `seats.view` |  |
| GET | `/api/seats/heatmap` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/seats/info` | `seats.view` |  |
| GET | `/api/seats/occupancy` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/seats/resolve` | `seats.view` |  |
| GET | `/api/switches/<switch_id>/status` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.past_events

Past events and comparing them (issue #38). Rules in floorbit/event_archive.py.

Source: [`floorbit/blueprints/past_events.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/past_events.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/past-events` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `past_events` |
| DELETE | `/api/past-events/<event_id>` | `settings.manage` | `past_events` |
| PATCH | `/api/past-events/<event_id>` | `settings.manage` | `past_events` |
| GET | `/api/past-events/<event_id>/report.pdf` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `past_events` |
| GET | `/api/past-events/backup/<event_id>.json` | `settings.manage` | `past_events` |
| POST | `/api/past-events/close` | `settings.manage` | `past_events` |

## floorbit.blueprints.planner

Build planner (issue #34). Rules in floorbit/planner.py.

Source: [`floorbit/blueprints/planner.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/planner.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/planner` | `floorplan.edit` | `planner` |
| POST | `/api/planner/apply` | `floorplan.edit` | `planner` |
| GET | `/api/planner/config/<name>` | `floorplan.edit` | `planner` |
| GET | `/api/planner/configs.zip` | `floorplan.edit` | `planner` |
| GET | `/api/planner/labels.pdf` | `floorplan.edit` | `planner` |
| GET | `/api/planner/plan.csv` | `floorplan.edit` | `planner` |
| PUT | `/api/planner/settings` | `floorplan.edit` | `planner` |
| DELETE | `/api/planner/templates/<template_id>` | `floorplan.edit` | `planner` |
| GET | `/api/planner/templates/<template_id>` | `floorplan.edit` | `planner` |
| PUT | `/api/planner/templates/<template_id>` | `floorplan.edit` | `planner` |

## floorbit.blueprints.plugins

Plugins: Settings > Plugins for admins, the dashboard, and the API plugins add.

Source: [`floorbit/blueprints/plugins.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/plugins.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/dashboard` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `dashboard` |
| GET | `/api/dashboard/layouts` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `dashboard` |
| DELETE | `/api/dashboard/layouts/<layout_id>` | `floorplan.edit` | `dashboard` |
| PUT | `/api/dashboard/layouts/<layout_id>` | `floorplan.edit` | `dashboard` |
| POST | `/api/plugins/<plugin_id>/actions/<action_id>` | `floorplan.view` |  |
| GET | `/api/plugins/<plugin_id>/endpoints/<endpoint_id>` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/plugins/<plugin_id>/widgets/<widget_id>` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/plugins/menu` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/settings/plugins` | `settings.manage` |  |
| PUT | `/api/settings/plugins/<plugin_id>` | `settings.manage` |  |
| GET | `/api/settings/plugins/<plugin_id>/log` | `settings.manage` |  |
| POST | `/api/settings/plugins/<plugin_id>/test` | `settings.manage` |  |

## floorbit.blueprints.ports

Port actions (issue #16). The rules live in floorbit/ports.py.

Source: [`floorbit/blueprints/ports.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/ports.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/ports` | `ports.act` | `ports` |
| POST | `/api/ports/<action>` | `ports.act` | `ports` |
| GET | `/api/ports/shut` | `ports.act` | `ports` |

## floorbit.blueprints.power

Electrics (issue #45): boards, circuits and their load. Rules live in floorbit/power.py.

Source: [`floorbit/blueprints/power.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/power.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/power` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `power` |
| POST | `/api/power/boards` | `floorplan.view` | `power` |
| DELETE | `/api/power/boards/<board_id>` | `floorplan.view` | `power` |
| PATCH | `/api/power/boards/<board_id>` | `floorplan.view` | `power` |
| POST | `/api/power/check` | `plugins.run` | `power` |
| POST | `/api/power/circuits` | `floorplan.view` | `power` |
| DELETE | `/api/power/circuits/<circuit_id>` | `floorplan.view` | `power` |
| PATCH | `/api/power/circuits/<circuit_id>` | `floorplan.view` | `power` |
| POST | `/api/power/circuits/<circuit_id>/reading` | `floorplan.view` | `power` |
| POST | `/api/power/circuits/<circuit_id>/trip` | `floorplan.view` | `power` |
| GET | `/api/power/markers` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `power` |

## floorbit.blueprints.preflight

Pre-flight check board (issue #35). Rules in floorbit/preflight.py.

Source: [`floorbit/blueprints/preflight.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/preflight.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/preflight` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `preflight` |
| GET | `/api/preflight.pdf` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `preflight` |
| POST | `/api/preflight/run` | `incidents.work` | `preflight` |

## floorbit.blueprints.problems

The Problems page and alert mutes (issue #10). See docs/alerts.md.

Source: [`floorbit/blueprints/problems.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/problems.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| POST | `/api/alerts/mutes` | `incidents.work` |  |
| DELETE | `/api/alerts/mutes/<switch_id>` | `incidents.work` |  |
| GET | `/api/problems` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.replay

Event timeline replay (issue #21): the event on the floor plan, with a time slider. See docs/replay.md.

Source: [`floorbit/blueprints/replay.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/replay.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/replay` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `replay` |
| GET | `/api/replay/event` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `replay` |
| GET | `/api/replay/event.json` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `replay` |

## floorbit.blueprints.report

Post-event report (issue #22). See docs/report.md.

Source: [`floorbit/blueprints/report.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/report.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/report` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `report` |
| GET | `/api/report.pdf` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `report` |
| POST | `/api/report/new-event` | `settings.manage` | `report` |

## floorbit.blueprints.runbooks

Runbooks (issue #102). The rules live in floorbit/runbooks.py.

Source: [`floorbit/blueprints/runbooks.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/runbooks.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/runbooks` | `incidents.work` | `runbooks` |
| POST | `/api/runbooks` | `incidents.assign` | `runbooks` |
| DELETE | `/api/runbooks/<book_id>` | `incidents.assign` | `runbooks` |
| PATCH | `/api/runbooks/<book_id>` | `incidents.assign` | `runbooks` |
| POST | `/api/runbooks/<book_id>/move` | `incidents.assign` | `runbooks` |

## floorbit.blueprints.schedule

Event schedule and countdown (issue #106). The rules live in floorbit/schedule.py; see docs/schedule.md.

Source: [`floorbit/blueprints/schedule.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/schedule.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/schedule` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `schedule` |
| PUT | `/api/schedule/event` | `floorplan.edit` | `schedule` |
| POST | `/api/schedule/import` | `floorplan.edit` | `schedule` |
| POST | `/api/schedule/items` | `floorplan.edit` | `schedule` |
| DELETE | `/api/schedule/items/<item_id>` | `floorplan.edit` | `schedule` |
| PATCH | `/api/schedule/items/<item_id>` | `floorplan.edit` | `schedule` |

## floorbit.blueprints.seat_blocks

Seat blocks (rows of seats) on the floor plan. Each is in one hall (``hall_id``, floorbit/halls.py).

Source: [`floorbit/blueprints/seat_blocks.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/seat_blocks.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/seat-blocks` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/seat-blocks` | `floorplan.edit` |  |
| DELETE | `/api/seat-blocks/<block_id>` | `floorplan.edit` |  |
| PUT | `/api/seat-blocks/<block_id>` | `floorplan.edit` |  |
| GET | `/api/seats` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.seat_map

The seat mapping page and API (floorbit/seatmap.py has the rules).

Source: [`floorbit/blueprints/seat_map.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/seat_map.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/seat-map` | `seats.view` |  |
| GET | `/api/seat-map.csv` | `seats.view` |  |
| DELETE | `/api/seat-map/<seat>` | `seats.edit` |  |
| PUT | `/api/seat-map/<seat>` | `seats.edit` |  |
| POST | `/api/seat-map/import` | `seats.edit` |  |

## floorbit.blueprints.security

Security findings (issue #29). The checks come from security plugins (floorbit/security.py).

Source: [`floorbit/blueprints/security.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/security.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/security` | `seats.view` | `security` |
| POST | `/api/security/<path:finding_id>/ack` | `seats.view` | `security` |
| POST | `/api/security/check` | `plugins.run` | `security` |
| GET | `/api/security/markers` | `seats.view` | `security` |

## floorbit.blueprints.setup

First-run setup (issue #13, floorbit/setup.py).

Source: [`floorbit/blueprints/setup.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/setup.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/setup` | anyone |  |
| POST | `/api/setup/account` | anyone |  |
| POST | `/api/setup/finish` | `settings.manage` |  |
| POST | `/api/setup/steps/<step>` | `settings.manage` |  |

## floorbit.blueprints.speedtest

Speedtest at the seat (issue #99). The rules live in floorbit/speedtest.py.

Source: [`floorbit/blueprints/speedtest.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/speedtest.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/speedtests` | `incidents.work` | `helpdesk` |

## floorbit.blueprints.stats

The stats dashboard (issue #24). See docs/stats.md.

Source: [`floorbit/blueprints/stats.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/stats.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/forecast` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `forecast` |
| GET | `/api/stats` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/stats/compare` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/stats/peak/reset` | `settings.manage` |  |
| GET | `/api/stats/seats` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |

## floorbit.blueprints.status_page

Public network status page (issue #101). The rules live in floorbit/status_page.py.

Source: [`floorbit/blueprints/status_page.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/status_page.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/status-page` | `incidents.work` | `status_page` |
| PUT | `/api/status-page/override` | `incidents.assign` | `status_page` |
| POST | `/api/status-page/updates` | `incidents.assign` | `status_page` |
| DELETE | `/api/status-page/updates/<update_id>` | `incidents.assign` | `status_page` |

## floorbit.blueprints.switches

Switches on the floor plan: the placed devices of the inventory (floorbit/inventory.py).

Source: [`floorbit/blueprints/switches.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/switches.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/switches` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| POST | `/api/switches` | `floorplan.edit` |  |
| DELETE | `/api/switches/<switch_id>` | `floorplan.edit` |  |
| PUT | `/api/switches/<switch_id>` | `floorplan.edit` |  |
| POST | `/api/switches/sync` | `floorplan.edit` |  |

## floorbit.blueprints.teardown

Teardown checklist (issue #37). Rules in floorbit/teardown.py.

Source: [`floorbit/blueprints/teardown.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/teardown.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/teardown` | `floorplan.edit` | `teardown` |
| GET | `/api/teardown/export.zip` | `settings.manage` | `teardown` |
| POST | `/api/teardown/items` | `floorplan.edit` | `teardown` |
| DELETE | `/api/teardown/items/<item_id>` | `floorplan.edit` | `teardown` |
| PATCH | `/api/teardown/items/<item_id>` | `floorplan.edit` | `teardown` |
| PUT | `/api/teardown/switches/<device_id>` | `floorplan.edit` | `teardown` |

## floorbit.blueprints.terminal

The browser terminal for one switch (issue #95). The rules live in floorbit/terminal.py.

Source: [`floorbit/blueprints/terminal.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/terminal.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/terminal` | `terminal.open` | `terminal` |
| POST | `/api/terminal` | `terminal.open` | `terminal` |
| DELETE | `/api/terminal/<sid>` | `terminal.open` | `terminal` |
| POST | `/api/terminal/<sid>/input` | `terminal.open` | `terminal` |
| GET | `/api/terminal/<sid>/output` | `terminal.open` | `terminal` |
| POST | `/api/terminal/<sid>/resize` | `terminal.open` | `terminal` |

## floorbit.blueprints.timeline

Event changelog (issue #100). The rules live in floorbit/timeline.py.

Source: [`floorbit/blueprints/timeline.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/timeline.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/timeline` | `audit.read` | `timeline` |
| GET | `/api/timeline.csv` | `audit.read` | `timeline` |

## floorbit.blueprints.tournament

Tournament awareness (issue #31): match zones and QoS hints. Rules in floorbit/tournament.py.

Source: [`floorbit/blueprints/tournament.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/tournament.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/tournament` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `tournament` |
| GET | `/api/tournament/qos` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `tournament` |
| GET | `/api/tournament/seats` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `tournament` |
| POST | `/api/tournament/zones` | `floorplan.edit` | `tournament` |
| DELETE | `/api/tournament/zones/<zone_id>` | `floorplan.edit` | `tournament` |
| PATCH | `/api/tournament/zones/<zone_id>` | `floorplan.edit` | `tournament` |

## floorbit.blueprints.webhooks

Outgoing webhooks (issue #40). Rules in floorbit/webhooks.py, docs in docs/api.md#webhooks.

Source: [`floorbit/blueprints/webhooks.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/webhooks.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/settings/webhooks` | `settings.manage` |  |
| POST | `/api/settings/webhooks` | `settings.manage` |  |
| DELETE | `/api/settings/webhooks/<hook_id>` | `settings.manage` |  |
| PATCH | `/api/settings/webhooks/<hook_id>` | `settings.manage` |  |
| POST | `/api/settings/webhooks/<hook_id>/secret` | `settings.manage` |  |
| POST | `/api/settings/webhooks/<hook_id>/test` | `settings.manage` |  |

## floorbit.blueprints.wifi

Wi-Fi view (issue #98). The rules live in floorbit/wifi.py.

Source: [`floorbit/blueprints/wifi.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/blueprints/wifi.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/wifi` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) | `wifi` |

## floorbit.settings

Persisted application settings.

Source: [`floorbit/settings.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/floorbit/settings.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| GET | `/api/settings` | `settings.manage` |  |
| PATCH | `/api/settings` | `settings.manage` |  |
| PUT | `/api/settings` | `settings.manage` |  |
| POST | `/api/settings/test/<service>` | `settings.manage` |  |

## integrations

Optional integrations for the floor plan app.

Source: [`integrations/__init__.py`](https://github.com/bitsandbricks-ch/floorbit/blob/master/integrations/__init__.py)

| Method | Path | Needs | Feature |
| --- | --- | --- | --- |
| POST | `/api/checkin` | anyone |  |
| GET | `/api/checkin/me` | anyone |  |
| GET | `/api/checkins` | `seats.view` |  |
| DELETE | `/api/checkins/<seat>` | `seats.edit` |  |
| GET | `/api/checkins/history` | `seats.view` |  |
| GET | `/api/checkins/history.csv` | `seats.view` |  |
| POST | `/api/checkins/refresh` | `seats.edit` |  |
| GET | `/api/events` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
| GET | `/api/integrations` | `settings.manage` |  |
| POST | `/api/integrations/discord/test` | `settings.manage` |  |
| POST | `/api/integrations/monitor/poll` | `settings.manage` |  |
| GET | `/api/seats/sources` | `seats.view` |  |
| GET | `/api/status/snapshot` | floorplan.view (open while `AUTH_PUBLIC_READ` is on) |  |
