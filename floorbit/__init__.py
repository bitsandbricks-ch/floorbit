"""Floorbit: the event's network on a floor plan.

``create_app()`` builds the Flask app from these parts:

* ``auth/``                 sign-in, roles and accounts (registered first, so its guard runs first)
* ``floorbit/settings.py``  the settings page and its store; ``runtime.py`` holds the live values
* ``floorbit/cache.py``     Redis
* ``floorbit/audit.py``     the audit log of changes and sign-ins
* ``floorbit/theme.py``     themes: the preset and colours each page renders with
* ``floorbit/plugins/``     plugins: actions, widgets, endpoints and hooks outside the core
* ``floorbit/sources/``     NetBox and LibreNMS, behind ``inventory()`` and ``monitoring()``
* ``floorbit/blueprints/``  one blueprint per area of the JSON API and the pages
* ``integrations/``         live updates, status monitor, Discord, seat sources, check-in

See docs/architecture.md.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from . import cache, runtime, store
from .audit import init_audit
from .plugins import init_plugins
from .settings import SettingsStore, create_settings_blueprint
from .theme import init_theme

ROOT = Path(__file__).resolve().parent.parent


def _setting_or_empty(settings_store, key):
    try:
        return settings_store.get(key)
    except KeyError:   # integrations add this field at start-up
        return ''


def create_app(start_background=True):
    load_dotenv()
    if os.environ.get('FLOORBIT_DATA_FILE'):   # may come from .env, read just now
        store.DATA_FILE = os.environ['FLOORBIT_DATA_FILE']
    store.current_tenant()   # a wrong FLOORBIT_TENANT stops the start, before anything is read
    from . import outbound
    outbound.install()   # before anything can make a request (issue #505)
    app = Flask(__name__, root_path=str(ROOT))
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

    from . import database
    # Before waiting for it: SQLite in a folder this process can't write never comes up.
    stuck = store.unwritable() if database.backend().kind == 'sqlite' else []
    if stuck:
        print(f"[store] Can't write {', '.join(stuck)}: saving will fail. In Docker, run "
              "`docker compose exec -u root floorbit chown -R floorbit: /app/state` (docs/install.md).")
    where = database.wait_until_ready()
    print(f"[store] Keeping documents in {where['where']}")
    if not where['ok']:
        print("[store] Starting without it: pages show the last copies read (none yet), saving is "
              "off, and Floorbit keeps trying in the background (docs/database.md).", flush=True)
    if start_background:
        database.watch()

    # Stored data from an older Floorbit moves to the current shape, once (floorbit/upgrades.py).
    from . import upgrades
    try:
        upgrades.run_at_start()
    except Exception as exc:  # noqa: BLE001  # the database may be away: load_data moves it when read
        print(f"[upgrades] Could not move the stored data yet: {exc}", flush=True)

    # Self-hosted: the agent next to this server gets its key from a shared file (docs/install.md).
    from . import agent_link
    try:
        if agent_link.bootstrap_local():
            print(f"[agent] The local agent's key is in {agent_link._local_key_file()}", flush=True)
    except Exception as exc:  # noqa: BLE001  # the database may be away: the next start tries again
        print(f"[agent] Could not enrol the local agent: {exc}", flush=True)

    # Without the database: a clear 503 instead of a 500, in the reader's language (docs/database.md).
    from .blueprints.health import database_unavailable, disk_unwritable, too_large
    app.register_error_handler(database.DatabaseUnavailable, database_unavailable)
    # A full or read-only disk: a clear 507 instead of a 500 (docs/install.md).
    app.register_error_handler(OSError, disk_unwritable)
    app.register_error_handler(413, too_large)

    # Sign-in first, so its check runs before the other before_request hooks and a
    # refused request never touches Redis.
    from auth import init_auth
    init_auth(app, store.tenant_file)
    # Which event the request works on, before anything reads one (docs/tenancy.md).
    from .blueprints import tenant_events
    tenant_events.init_app(app)
    from .blueprints import platform
    platform.init_app(app)
    from . import hosting
    hosting.register_cli(app)
    from . import i18n
    i18n.init_app(app)

    settings_store = SettingsStore(store.tenant_file)
    runtime.apply(settings_store)
    app.extensions['floorbit_settings'] = settings_store

    # Discord sign-in reads its settings on every request, so a save applies at once.
    from auth.providers import DiscordProvider
    auth = app.extensions['auth']
    auth.providers.register(DiscordProvider(settings_store.get))
    auth.public_url = lambda: _setting_or_empty(settings_store, 'integrations.public_url')

    @app.before_request
    def refresh_runtime_settings():
        """Pick up settings saved by another process/worker (cheap mtime check)."""
        if settings_store.reload_if_changed():
            runtime.apply(settings_store)

    app.before_request(cache.connect)

    # Every page's preset and colours, ?theme= per screen, and the uploaded event logo.
    init_theme(app, settings_store)

    # Who changed what: every successful change and sign-in, see floorbit/audit.py.
    init_audit(app)

    # Floorbit's own log lines, for the Logs page next to the syslog (docs/syslog.md).
    from .app_log import init_app_log
    init_app_log(app, start_background=start_background)

    # Imported here, not at the top: blueprints import auth, and auth imports floorbit.env, so a
    # top-level import made `import auth` (or any test importing it first) fail half-initialised.
    from .blueprints import ALL as BLUEPRINTS
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

    # A stopping gunicorn worker ends the live-update streams first, so it exits at once.
    if start_background:
        from integrations import events
        events.close_streams_on_sigterm()

    # Features an admin turned off answer 404 and leave the navigation (docs/features.md).
    from .features import init_features
    init_features(app)

    # /settings page plus GET/PUT /api/settings and POST /api/settings/test/<service>
    app.register_blueprint(create_settings_blueprint(
        settings_store,
        on_change=lambda: runtime.apply(settings_store),
        get_redis=cache.get_redis_client,
        redis_info=cache.redis_info,
    ))

    # Live push (/api/events), switch status monitor, Discord alerts, seat sources and the
    # seat check-in page. See docs/integrations.md.
    from integrations import init_integrations
    init_integrations(app, load_data=store.load_data, settings_store=settings_store,
                      start_background=start_background)

    # Plugins: actions, widgets, endpoints and hooks from floorbit/builtin_plugins (see docs/plugins.md).
    version_file = ROOT / 'VERSION'
    app.config['FLOORBIT_VERSION'] = version_file.read_text().strip() if version_file.is_file() else '0'
    registry = init_plugins(app, settings_store, app.config['FLOORBIT_VERSION'])
    # Plugins installed from the Marketplace, signed (floorbit/marketplace.py, docs/marketplace.md).
    from .marketplace import init_marketplace
    init_marketplace(app, registry, start_background=start_background)

    # The service health wall: health plugins polled in the background (docs/health.md).
    from .health import init_health
    init_health(app, registry, start_background=start_background)

    # Discord posts what is about to start on the public programme (docs/schedule.md).
    from .schedule_announce import init_schedule_announce
    init_schedule_announce(app, start_background=start_background)

    # A bare "x" or 5 as a JSON body is refused before any handler reads it (floorbit/json_body.py).
    from .json_body import init_json_body
    init_json_body(app)

    # Clickjacking and MIME sniffing guards on every answer (floorbit/headers.py).
    from .headers import init_headers
    init_headers(app)

    # Unknown addresses: JSON for the API, the React app's 404 for pages (floorbit/not_found.py).
    from .not_found import init_not_found
    init_not_found(app)

    # Security findings from security plugins, polled in the background (docs/security.md).
    from .security import init_security
    init_security(app, registry, start_background=start_background)

    # Electrics: boards, circuits and their load, with readings from power plugins (docs/power.md).
    from .power import init_power
    init_power(app, registry, start_background=start_background)

    # DNS analytics: what the hall looks up, hall-wide only (docs/dns.md).
    from .dns import init_dns
    init_dns(app, registry, start_background=start_background)

    # What the LAN cache served, from its access log (docs/games.md).
    from .lancache import init_lancache
    init_lancache(app, start_background=start_background)

    # Device telemetry: Telegraf, gNMI, MDT and API pollers, without LibreNMS (docs/telemetry.md).
    from . import telemetry
    telemetry.init_app(app, start_background=start_background)

    # Game servers: up or down, players and map, an RCON console (docs/game-servers.md).
    from . import game_servers
    game_servers.init_app(app, start_background=start_background)
    from . import services
    services.init_app(app, start_background=start_background)
    from . import links
    links.init_app(app, start_background=start_background)
    # The crew's walk-through check-in: seat ports are cleared a day after the event (docs/seat-walk.md).
    from . import seat_walk
    seat_walk.init_app(app, start_background=start_background)

    # Ports that need a look: flapping, errors rising, half duplex, no check-in (docs/alerts.md).
    from .attention import init_attention
    from .stats import init_stats
    init_stats(app)   # fed by the attention watch's port reads (docs/stats.md)
    init_attention(app, start_background=start_background)
    from . import port_clients
    port_clients.init_app(app)   # reads only when the cables page asks (docs/cables.md)

    # Syslog from switches, firewalls and DHCP servers, off until SYSLOG_ENABLED (docs/syslog.md).
    from .syslog import init_syslog
    init_syslog(app, registry, start_background=start_background)

    # Bandwidth forecast from the stats' hours, with a warning before the line fills (docs/forecast.md).
    from .forecast import init_forecast
    init_forecast(app, start_background=start_background)

    # Outgoing webhooks: chosen events POSTed to other tools, signed (docs/api.md#webhooks).
    from .webhooks import init_webhooks
    init_webhooks(app, start_background=start_background)
    from .config_backup import init_nightly
    init_nightly(app, start_background=start_background)
    # Scheduled backups to an S3 bucket, off until one is set (docs/backup.md).
    from . import s3_backup
    s3_backup.init_app(app, start_background=start_background)

    # The event changelog: alerts from the event bus and each start go into its journal (docs/timeline.md).
    from .timeline import init_timeline
    init_timeline(app)

    # FLOORBIT_DEMO=1: lay the demo hall out on an empty floor plan (docs/demo.md).
    from .blueprints.demo import seed_on_start
    seed_on_start(app)

    # First-run setup for a new install, after the demo so a demo hall counts as set up (docs/install.md).
    from .blueprints.setup import init_setup
    init_setup(app)

    # Several pods: share live updates, agent calls and one leader through Redis (docs/kubernetes.md).
    if start_background:
        from . import cluster
        joined = cluster.init()
        if joined is not None and where['kind'] != 'postgres':
            print('[cluster] Several pods need one shared database: set FLOORBIT_DATABASE_URL to Postgres '
                  '(docs/database.md). Each pod keeps its own documents until then.')
    return app
