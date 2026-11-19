"""A plugin's own JSON documents (``uses: [documents]``) and the store its ``migrate`` gets.

Each collection is one store document, ``plugin-data/<plugin id>/<collection>.json`` under the
tenant, so it lives wherever Floorbit keeps its data (files, SQLite, Postgres) and every tenant has
its own. Limits (docs/plugin-spec.md#storage): 256 KB per document, 5 MB and 50 collections per
plugin. A plugin never names a path: collection names and document ids are checked here.
"""
from __future__ import annotations

import json
import re
import threading

from .base import STATE_MAX_BYTES, PluginError

DOC_MAX_BYTES = 256 * 1024
PLUGIN_MAX_BYTES = 5 * 1024 * 1024
MAX_COLLECTIONS = 50
COLLECTION_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}\Z')
DOC_ID_MAX = 128

_locks = {}
_locks_guard = threading.Lock()


def _lock(plugin_id):
    with _locks_guard:
        return _locks.setdefault(plugin_id, threading.Lock())


def folder(plugin_id):
    from .. import store
    return store.tenant_path('plugin-data', plugin_id)


def _path(plugin_id, collection):
    from .. import store
    return store.tenant_path('plugin-data', plugin_id, f'{collection}.json')


def _size(value):
    return len(json.dumps(value, separators=(',', ':'), default=str).encode())


def _check_id(doc_id):
    if not isinstance(doc_id, str) or not 1 <= len(doc_id) <= DOC_ID_MAX or not doc_id.isprintable():
        raise PluginError(f'A document id is 1 to {DOC_ID_MAX} printable characters')
    return doc_id


def _read(plugin_id, collection):
    from .. import store
    data = store.read_json(_path(plugin_id, collection), {})
    return data if isinstance(data, dict) else {}


def collections(plugin_id):
    from .. import store
    return [n[:-5] for n in store.list_json(folder(plugin_id)) if COLLECTION_RE.match(n[:-5])]


class Collection:
    """One collection: ``get``, ``put``, ``delete``, ``ids``, ``all``. Writes read the collection
    fresh under the plugin's lock, so two hooks writing at once don't undo each other; between pods,
    the store's merge keeps a document another pod wrote meanwhile (each document is a top-level key)."""

    def __init__(self, plugin_id, name):
        if not isinstance(name, str) or not COLLECTION_RE.match(name):
            raise PluginError('A collection name is 1 to 40 lowercase letters, digits and _, starting with a letter')
        self.plugin_id, self.name = plugin_id, name

    def get(self, doc_id, default=None):
        doc = _read(self.plugin_id, self.name).get(_check_id(doc_id))
        return default if doc is None else json.loads(json.dumps(doc))   # a copy: never the cached one

    def ids(self):
        return sorted(_read(self.plugin_id, self.name))

    def all(self):
        return json.loads(json.dumps(_read(self.plugin_id, self.name)))

    def put(self, doc_id, doc):
        from .. import store
        _check_id(doc_id)
        try:
            doc = json.loads(json.dumps(doc, allow_nan=False))
        except (TypeError, ValueError):
            raise PluginError('A document must be plain JSON (dicts, lists, text, numbers, true/false, null)') from None
        size = _size(doc)
        if size > DOC_MAX_BYTES:
            raise PluginError(f'A document is limited to {DOC_MAX_BYTES // 1024} KB ({size // 1024} KB given)')
        with _lock(self.plugin_id):
            have = collections(self.plugin_id)
            if self.name not in have and len(have) >= MAX_COLLECTIONS:
                raise PluginError(f'A plugin keeps at most {MAX_COLLECTIONS} collections')
            data = _read(self.plugin_id, self.name)
            others = sum(_size(_read(self.plugin_id, c)) for c in have if c != self.name)
            data[doc_id] = doc      # in place: the store keeps what another pod wrote meanwhile
            if others + _size(data) > PLUGIN_MAX_BYTES:
                raise PluginError(f'A plugin\'s documents are limited to {PLUGIN_MAX_BYTES // (1024 * 1024)} MB')
            store.write_json(_path(self.plugin_id, self.name), data)

    def delete(self, doc_id):
        """True when there was such a document."""
        from .. import store
        _check_id(doc_id)
        with _lock(self.plugin_id):
            data = _read(self.plugin_id, self.name)
            if doc_id not in data:
                return False
            del data[doc_id]        # in place, as in put()
            store.write_json(_path(self.plugin_id, self.name), data)
            # Gone only when nothing is left after the merge: another pod may have added one.
            if not _read(self.plugin_id, self.name):
                store.delete_json(_path(self.plugin_id, self.name))
            return True

    def clear(self):
        from .. import store
        with _lock(self.plugin_id):
            store.delete_json(_path(self.plugin_id, self.name))


class Store:
    """What ``migrate(from_schema, store)`` works on: the plugin's collections and its small state."""

    def __init__(self, spec, registry):
        self._spec, self._registry = spec, registry

    def collection(self, name):
        self._registry.require(self._spec, 'documents')
        return Collection(self._spec.id, name)

    def collections(self):
        self._registry.require(self._spec, 'documents')
        return collections(self._spec.id)

    @property
    def state(self):
        return dict(self._registry.state_of(self._spec.id))

    def set_state(self, key, value):
        self._registry.require(self._spec, 'storage')
        self._registry.set_state_key(self._spec.id, key, value, STATE_MAX_BYTES)
