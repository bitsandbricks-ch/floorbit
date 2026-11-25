"""Stats counts ports in use of all ports, and as down only the ports that were up during the event
and went down: most down ports are just unused, which read like an outage (issue #1421)."""
from test_stats import busy, hall, poll, read, seat_port  # noqa: F401  (hall is a fixture)


def test_an_unused_port_is_not_counted_as_gone_down(client, hall):  # noqa: F811
    busy(hall["mon"])                                     # A-3 was never up
    poll(hall, 1000)
    now = read(client)["now"]
    assert (now["ports_up"], now["ports_total"], now["ports_lost"]) == (3, 4, 0)
    assert now["ports_down"] == 1                         # still there for the dashboards


def test_a_port_that_was_up_and_went_down_counts(client, hall):  # noqa: F811
    busy(hall["mon"])
    poll(hall, 1000)
    hall["mon"].set("sw-a-01", seat_port("Gi1/0/1", "A-1", 0, state="down"))   # the other ports stay as they were
    poll(hall, 1060)
    now = read(client)["now"]
    assert (now["ports_up"], now["ports_lost"], now["ports_down"], now["ports_total"]) == (2, 1, 2, 4)


def test_a_new_event_forgets_which_ports_were_up(client, hall):  # noqa: F811
    busy(hall["mon"])
    poll(hall, 1000)
    hall["app"].extensions["floorbit_stats"].new_event(now=1030)
    hall["mon"].set("sw-a-01", seat_port("Gi1/0/1", "A-1", 0, state="down"))
    poll(hall, 1060)
    assert read(client)["now"]["ports_lost"] == 0
