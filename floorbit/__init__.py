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
from .blueprints import ALL as BLUEPRINTS
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
    app = Flask(__name__, root_path=str(ROOT))
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

    stuck = store.unwritable()
    if stuck:
        print(f"[store] Can't write {', '.join(stuck)}: saving will fail. In Docker, run "
              "`docker compose exec -u root floorbit chown -R floorbit: /app/state` (docs/install.md).")

    # Sign-in first, so its check runs before the other before_request hooks and a
    # refused request never touches Redis.
    from auth import init_auth
    init_auth(app, store.DATA_FILE)

    settings_store = SettingsStore(store.DATA_FILE)
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

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

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

    # The service health wall: health plugins polled in the background (docs/health.md).
    from .health import init_health
    init_health(app, registry, start_background=start_background)

    # Security findings from security plugins, polled in the background (docs/security.md).
    from .security import init_security
    init_security(app, registry, start_background=start_background)

    # Electrics: boards, circuits and their load, with readings from power plugins (docs/power.md).
    from .power import init_power
    init_power(app, registry, start_background=start_background)

    # DNS analytics: what the hall looks up, hall-wide only (docs/dns.md).
    from .dns import init_dns
    init_dns(app, registry, start_background=start_background)

    # Ports that need a look: flapping, errors rising, half duplex, no check-in (docs/alerts.md).
    from .attention import init_attention
    from .stats import init_stats
    init_stats(app)   # fed by the attention watch's port reads (docs/stats.md)
    init_attention(app, start_background=start_background)

    # Outgoing webhooks: chosen events POSTed to other tools, signed (docs/api.md#webhooks).
    from .webhooks import init_webhooks
    init_webhooks(app, start_background=start_background)

    # FLOORBIT_DEMO=1: lay the demo hall out on an empty floor plan (docs/demo.md).
    from .blueprints.demo import seed_on_start
    seed_on_start(app)

    # First-run setup for a new install, after the demo so a demo hall counts as set up (docs/install.md).
    from .blueprints.setup import init_setup
    init_setup(app)
    return app
