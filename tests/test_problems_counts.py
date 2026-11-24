"""One problem count for every place that shows one (#884)."""
import pytest

pytestmark = pytest.mark.usefixtures("lan_here")


def test_look_and_total_add_up_from_the_lists(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    body = client.get("/api/problems").get_json()
    c = body["counts"]
    live = [p for p in body["problems"] if not p.get("muted")]
    assert c["down"] == sum(p["level"] == "down" for p in live)
    assert c["look"] == sum(p["level"] == "warn" for p in live) + len(body["attention"])
    assert c["total"] == c["down"] + c["look"]


def test_the_handover_counts_the_same_total(client):
    from floorbit import handover
    assert handover.summary([], {"down": 1, "warn": 2, "look": 5, "total": 6})["counts"]["problems"] == 6
