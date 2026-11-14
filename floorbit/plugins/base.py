"""What a plugin's Python code gets to work with.

A plugin is a folder with ``plugin.yaml`` and, optionally, ``plugin.py`` defining
``class Plugin(floorbit.plugins.base.Plugin)``. Methods are found by name and must match the
manifest (the loader refuses a ``run_x`` without an action ``x``):

    run_<action>(params)   -> dict (``message`` is shown)     actions:
    widget_<id>()          -> widget dict (see widgets.py)    widgets:
    endpoint_<id>(args)    -> JSON-able                       endpoints:
    on_<event>(event)      -> None                            hooks:
    test()                 -> str                             "Test" button, optional

Adapted from labdex (labdex/plugins/base.py, AGPL-3.0, by the same author). See docs/plugins.md.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque


class PluginError(Exception):
    """Raise this for an expected failure; the message is shown to the user."""


class HttpClient:
    """requests.Session with a base URL, TLS settings and timeouts that are always set."""

    def __init__(self, base_url='', verify=True, timeout=10, auth=None, headers=None, log=None):
        import requests
        self.base = (base_url or '').rstrip('/')
        self.s = requests.Session()
        self.s.verify = verify
        self.s.auth = auth
        self.s.headers.update(headers or {})
        self.timeout = timeout
        self._log = log

    def request(self, method, path, **kw):
        import requests
        url = path if path.startswith(('http://', 'https://')) else f"{self.base}/{path.lstrip('/')}"
        kw.setdefault('timeout', self.timeout)
        kw.setdefault('allow_redirects', False)   # a redirect to another host is never followed silently
        try:
            r = self.s.request(method, url, **kw)
        except requests.exceptions.SSLError as exc:
            self._note(f'{method} {url} -> TLS verification failed')
            raise PluginError(f'TLS verification failed for {url}') from exc
        except requests.exceptions.RequestException as exc:
            self._note(f'{method} {url} -> {type(exc).__name__}')
            raise PluginError(f'{method} {url} failed: {type(exc).__name__}') from exc
        self._note(f'{method} {url} -> {r.status_code}')
        return r

    def _note(self, line):
        if self._log:
            self._log(line)

    def get(self, path, **kw):
        return self.request('GET', path, **kw)

    def post(self, path, **kw):
        return self.request('POST', path, **kw)


STATE_MAX_BYTES = 64 * 1024
LOG_LINES = 200


class Context:
    """The plugin's view of Floorbit. Everything goes through here, and only for the areas the
    manifest lists under ``uses:``."""

    def __init__(self, spec, registry):
        self.spec = spec
        self._registry = registry

    @property
    def id(self):
        return self.spec.id

    @property
    def settings(self):
        return self._registry.settings_of(self.spec)

    def log(self, message):
        self._registry.log(self.spec.id, str(message))

    def http(self, base_url='', *, verify=None, timeout=10, auth=None, headers=None):
        self._registry.require(self.spec, 'http')
        if verify is None:
            verify = self.settings.get('verify_ssl', True)
        return HttpClient(base_url, verify=verify, timeout=min(float(timeout), 60), auth=auth,
                          headers=headers, log=self.log)

    # small private state, kept in plugins.json next to data.json -------------------
    @property
    def state(self):
        return dict(self._registry.state_of(self.spec.id))

    def set_state(self, key, value):
        self._registry.require(self.spec, 'storage')
        state = dict(self._registry.state_of(self.spec.id))
        state[str(key)] = value
        if len(json.dumps(state, default=str)) > STATE_MAX_BYTES:
            raise PluginError(f'Plugin state is limited to {STATE_MAX_BYTES // 1024} KB')
        self._registry.save_state(self.spec.id, state)


class Plugin:
    """Base class for ``plugin.py``. ``self.ctx`` is the plugin's Context."""

    def __init__(self, ctx):
        self.ctx = ctx

    @property
    def settings(self):
        return self.ctx.settings

    def log(self, msg):
        self.ctx.log(msg)

    def test(self):
        """Override to check the settings work (the Test button); return a short message."""
        raise PluginError('This plugin has no test.')


class LogBuffer:
    """The last lines each plugin logged, for the Plugins page (memory only)."""

    def __init__(self):
        self._lines = {}
        self._lock = threading.Lock()

    def add(self, plugin_id, line):
        with self._lock:
            self._lines.setdefault(plugin_id, deque(maxlen=LOG_LINES)).append(
                {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'line': line[:500]})

    def get(self, plugin_id):
        with self._lock:
            return list(self._lines.get(plugin_id, []))
