"""A traffic summary from an agent of another version, or a broken one, never breaks the Traffic,
Games or wall pages for everyone (floorbit/blueprints/agent.py, take_flow_summary)."""
import json
import random

from test_agent import enrol

from floorbit.flows.demo import DemoFlows

ODD = [None, 5, "x", [], {}, [1], {"a": 1}, True, -1, 10 ** 20, "9" * 50]


def _mutate(value, rnd):
    if isinstance(value, dict) and value:
        value = dict(value)
        k = rnd.choice(list(value))
        value[k] = _mutate(value[k], rnd) if rnd.random() < .5 else rnd.choice(ODD)
        return value
    if isinstance(value, list) and value:
        value = list(value)
        i = rnd.randrange(len(value))
        value[i] = _mutate(value[i], rnd) if rnd.random() < .5 else rnd.choice(ODD)
        return value
    return rnd.choice(ODD)


def test_odd_summaries_never_break_the_pages(client, app_module):
    key = enrol(client)["key"]
    agent = app_module.app.test_client()
    demo = DemoFlows()
    demo.backfill(minutes=5)
    good = json.loads(json.dumps(demo.snapshot()))
    rnd = random.Random(5)
    for _ in range(300):
        snap = _mutate(good, rnd)
        snap = {**snap, "updated": 1} if isinstance(snap, dict) else {"updated": 1}
        assert agent.post("/api/agent/v1/flows", json={"snapshot": snap},
                          headers={"Floorbit-Agent-Key": key}).status_code == 200
        for path in ("/api/flows", "/api/games", "/wall.json"):
            assert client.get(path, headers={"Accept-Language": "de"}).status_code < 500, (path, snap)
    # A good summary still comes through whole.
    agent.post("/api/agent/v1/flows", json={"snapshot": good}, headers={"Floorbit-Agent-Key": key})
    shown = client.get("/api/flows").get_json()
    assert shown["services"] == good["services"][:25] and shown["anomalies"][0]["seat"] == good["anomalies"][0]["seat"]
