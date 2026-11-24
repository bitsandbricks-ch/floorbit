"""Busiest seats list seats only (issue #1409): a busy port without a seat is not a seat."""
from test_attention import port
from test_stats import M, busy, hall, poll, read  # noqa: F401  (hall is a fixture)


def test_a_busy_port_without_a_seat_counts_in_the_total_but_is_not_a_busiest_seat(client, hall):  # noqa: F811
    busy(hall["mon"])
    hall["mon"].set("sw-a-01", {**port("Gi1/0/15", description="lancache"), "download_bps": 900 * M,
                                "upload_bps": 100 * M})
    poll(hall, 1000)
    body = read(client)
    assert [t["seat"] for t in body["top"]] == ["A-1", "A-2"]
    assert body["now"]["down"] == 1250 * M   # still part of the hall's traffic
