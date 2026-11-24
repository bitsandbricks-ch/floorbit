"""The DNS page pages its lists itself (issue #1343): the answer holds more than one page of sites
and says how many are named in all."""
import pytest

from floorbit import dns

pytestmark = pytest.mark.usefixtures("lan_here")

HOUR = 1_794_650_400


def lookups(domain, clients, at=HOUR + 60):
    return [{"ts": at + i, "domain": domain, "client": f"198.51.100.{i + 1}", "blocked": False}
            for i in range(clients)]


def test_more_than_a_page_of_sites_and_the_count_of_all(tmp_path, monkeypatch):
    monkeypatch.setattr(dns, "SITES_MAX", 70)
    stats = dns.DnsStats(path=str(tmp_path / "dns.json"))
    rows = []
    for i in range(80):
        rows += lookups(f"www.site{i}.example", 5)
    stats.add(rows, now=HOUR + 600)
    snap = stats.snapshot(hours=1, now=HOUR + 600)
    assert len(snap["sites"]) == 70      # more than the page's 50, capped
    assert snap["named"] == 80
