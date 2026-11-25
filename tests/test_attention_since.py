"""An item keeps when it started across a restart, instead of every row saying "now" (issue #1415)."""
from test_attention import hall, poll, port  # noqa: F401  (hall is a fixture)


def test_a_restart_keeps_when_each_item_started(hall):  # noqa: F811
    hall["mon"].set("sw-a-01", port("Gi1/0/1", duplex="half"))
    assert [e["kind"] for e in poll(hall, 1000)] == ["duplex"]
    hall["watch"].reset()   # what a restart leaves: nothing in memory
    assert poll(hall, 5000) == []   # not new again: it was there before
    [item] = hall["watch"].snapshot()["items"]
    assert item["since"] == 1000


def test_an_item_that_went_away_starts_afresh(hall):  # noqa: F811
    hall["mon"].set("sw-a-01", port("Gi1/0/1", duplex="half"))
    poll(hall, 1000)
    hall["mon"].set("sw-a-01", port("Gi1/0/1"))
    poll(hall, 2000)
    hall["mon"].set("sw-a-01", port("Gi1/0/1", duplex="half"))
    hall["watch"].reset()
    assert [e["kind"] for e in poll(hall, 3000)] == ["duplex"]
    assert hall["watch"].snapshot()["items"][0]["since"] == 3000
