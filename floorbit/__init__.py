"""Floorbit: the event's network on a floor plan.

``create_app()`` builds the Flask app from these parts:

* ``auth/``                 sign-in, roles and accounts (registered first, so its guard runs first)
* ``floorbit/settings.py``  the settings page and its store; ``runtime.py`` holds the live values
* ``floorbit/cache.py``     Redis
* ``floorbit/theme.py``     themes: the preset and colours each page renders with
* ``floorbit/sources/``     NetBox and LibreNMS, behind ``inventory()`` and ``monitoring()``
* ``floorbit/blueprints/``  one blueprint per area of the JSON API and the pages
* ``integrations/``         live updates, status monitor, Discord, seat sources, check-in

See docs/architecture.md.
"""
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from . import cache, runtime, store
from .blueprints import ALL as BLUEPRINTS
from .settings import SettingsStore, create_settings_blueprint
from .theme import init_theme

ROOT = Path(__file__).resolve().parent.parent


def create_app(start_background=True):
    load_dotenv()
    app = Flask(__name__, root_path=str(ROOT))
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

    # Sign-in first, so its check runs before the other before_request hooks and a
    # refused request never touches Redis.
    from auth import init_auth
    init_auth(app, store.DATA_FILE)

    settings_store = SettingsStore(store.DATA_FILE)
    runtime.apply(settings_store)
    app.extensions['floorbit_settings'] = settings_store

    @app.before_request
    def refresh_runtime_settings():
        """Pick up settings saved by another process/worker (cheap mtime check)."""
        if settings_store.reload_if_changed():
            runtime.apply(settings_store)

    app.before_request(cache.connect)

    # Every page's preset and colours, ?theme= per screen, and the uploaded event logo.
    init_theme(app, settings_store)

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)

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
    return app
