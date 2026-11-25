"""gunicorn.conf.py holds the image's defaults, so GUNICORN_CMD_ARGS can change them."""
import os
import re
import runpy
import subprocess
import sys
import types

import pytest


def _conf():
    return runpy.run_path("gunicorn.conf.py")


def test_the_defaults_are_one_worker_with_64_threads():
    conf = _conf()
    assert (conf["workers"], conf["worker_class"], conf["threads"], conf["bind"]) == (1, "gthread", 64, "0.0.0.0:5000")


def test_the_environment_overrides_them(monkeypatch):
    # What the image runs: plain ``gunicorn app:app`` in the folder that holds gunicorn.conf.py.
    env = {**os.environ, "GUNICORN_CMD_ARGS": "--threads 200 --workers 2"}
    out = subprocess.run([sys.executable, "-m", "gunicorn", "--print-config", "app:app"], env=env,
                         capture_output=True, text=True, timeout=60).stdout
    settings = dict(re.findall(r"^(\w+)\s+= (.*)$", out, re.M))
    assert (settings["threads"], settings["workers"], settings["worker_class"]) == ("200", "2", "gthread")


@pytest.mark.parametrize("cluster,warned", [("", True), ("valkey", False)])
def test_several_workers_without_the_cluster_are_warned_about(monkeypatch, capsys, cluster, warned):
    monkeypatch.setenv("FLOORBIT_CLUSTER", cluster)
    _conf()["when_ready"](types.SimpleNamespace(cfg=types.SimpleNamespace(workers=4)))
    assert ("without FLOORBIT_CLUSTER" in capsys.readouterr().out) is warned


def test_one_worker_needs_no_cluster(monkeypatch, capsys):
    monkeypatch.delenv("FLOORBIT_CLUSTER", raising=False)
    _conf()["when_ready"](types.SimpleNamespace(cfg=types.SimpleNamespace(workers=1)))
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("workers,asked", [(1, False), (3, True)])
def test_with_several_workers_each_starts_its_loops_at_once(workers, asked):
    # Only the leader polls (issue #1417); its loops must not wait for a request to reach it.
    got = []

    class App:
        def test_client(self):
            return types.SimpleNamespace(get=got.append)
    _conf()["post_worker_init"](types.SimpleNamespace(cfg=types.SimpleNamespace(workers=workers), wsgi=App()))
    assert got == (["/healthz"] if asked else [])
