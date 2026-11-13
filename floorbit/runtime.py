"""The settings the app runs with right now.

Values saved on /settings live in data.json and win over env vars, which remain the defaults
(see floorbit/settings.py). ``apply()`` copies them onto ``rt``, which the rest of the app
reads, so a save on the settings page takes effect without a restart.
"""
from types import SimpleNamespace

rt = SimpleNamespace(
    netbox_url='', netbox_token='', netbox_roles=[], netbox_verify_ssl=True,
    librenms_url='', librenms_token='', librenms_verify_ssl=True, librenms_fdb_exclude=[],
    cache_ttl_arp=300, cache_ttl_mac=300, cache_ttl_resolve=30,
    netbox_enabled=False, librenms_enabled=False, display_defaults={},
)


def apply(store):
    """Copy the settings store's current values onto ``rt``."""
    s = store
    rt.netbox_url           = s.get('netbox.url')
    rt.netbox_token         = s.get('netbox.token')
    rt.netbox_roles         = s.get('netbox.device_roles')
    rt.netbox_verify_ssl    = s.get('netbox.verify_ssl')
    rt.librenms_url         = s.get('librenms.url')
    rt.librenms_token       = s.get('librenms.token')
    rt.librenms_verify_ssl  = s.get('librenms.verify_ssl')
    rt.librenms_fdb_exclude = [p.lower() for p in s.get('librenms.fdb_exclude')]
    rt.cache_ttl_arp        = s.get('cache.ttl_arp')
    rt.cache_ttl_mac        = s.get('cache.ttl_mac')
    rt.cache_ttl_resolve    = s.get('cache.ttl_resolve')
    rt.netbox_enabled       = bool(rt.netbox_url and rt.netbox_token)
    rt.librenms_enabled     = bool(rt.librenms_url and rt.librenms_token)
    rt.display_defaults     = {
        'hide_labels':     s.get('display.hide_labels'),
        'exclude_heatmap': s.get('display.exclude_heatmap'),
    }
