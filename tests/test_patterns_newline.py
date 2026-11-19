"""A name or host with a newline at the end is refused everywhere (#769): ``$`` matched before a
final newline, so every check pattern ends in ``\\Z`` now."""
import importlib
import re

import pytest

CHECKS = [
    ('floorbit.telemetry.targets', 'AGENT_RE', 'rack-a'), ('floorbit.services', 'HOST_RE', 'example.com'),
    ('floorbit.game_servers', 'HOST_RE', 'example.com'), ('floorbit.tenancy', 'ID_RE', 'summer-lan'),
    ('floorbit.ports', 'PORT_RE', 'Gi1/0/1'), ('floorbit.ports', 'USER_RE', 'netops'),
    ('floorbit.links', 'PORT_RE', 'Gi1/0/1'), ('floorbit.seatmap', 'SEAT_RE', 'A-1'),
    ('floorbit.seatmap', 'MAC_RE', '020000000001'), ('floorbit.inventory_types', 'ID_RE', 'switch'),
    ('floorbit.inventory_interfaces', 'NAME_RE', 'Gi1/0/1'), ('floorbit.dashboards', 'ID_RE', 'hall-b'),
    ('floorbit.nav_sections', 'ID_RE', 'network'), ('floorbit.commands', 'ID_RE', 'show-vlan'),
    ('floorbit.power', 'METER_RE', 'DB-1'), ('floorbit.seat_walk', 'TOKEN_RE', 'a' * 20),
    ('floorbit.icon_library', 'ID_RE', 'custom-0123456789ab'), ('floorbit.store', '_TENANT_RE', 'club-b'),
    ('floorbit.agent_link', 'NAME_RE', 'hall agent'), ('floorbit.cables', 'LABEL_RE', 'A-01'),
    ('floorbit.webhooks', 'NAME_RE', 'discord'), ('floorbit.s3_backup', 'BUCKET_RE', 'floorbit-backups'),
]


@pytest.mark.parametrize('module,name,good', CHECKS)
def test_a_trailing_newline_is_refused(module, name, good):
    pattern = getattr(importlib.import_module(module), name)
    assert isinstance(pattern, re.Pattern)
    assert pattern.match(good)
    assert not pattern.match(good + '\n')
