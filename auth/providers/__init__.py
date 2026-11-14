"""Registry of login methods. See base.py for how to add one."""
from .base import AuthError, AuthProvider, Identity, PasswordProvider, RedirectProvider
from .discord import DiscordProvider
from .local import LocalProvider

__all__ = [
    'AuthError', 'AuthProvider', 'DiscordProvider', 'Identity', 'LocalProvider', 'PasswordProvider',
    'RedirectProvider', 'Registry',
]


class Registry:
    def __init__(self):
        self._providers = {}

    def register(self, provider):
        if not provider.id or provider.kind not in ('password', 'redirect'):
            raise ValueError('A provider needs an id and a kind of "password" or "redirect".')
        self._providers[provider.id] = provider
        return provider

    def get(self, provider_id):
        provider = self._providers.get(provider_id)
        return provider if provider and provider.enabled() else None

    def enabled(self, kind=None):
        return [p for p in self._providers.values() if p.enabled() and (kind is None or p.kind == kind)]
