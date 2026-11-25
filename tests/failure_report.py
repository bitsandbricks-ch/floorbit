"""Name a failing test before pytest builds its report (issue #1464).

Twice in CI, ``pytest (sqlite)`` failed a test near 90 % and then stalled while formatting it:
the first traceback of a run makes ``inspect.getmodule`` resolve the real path of every module
loaded so far, one ``realpath`` each, while dozens of the app's background threads compete for
the GIL. The job hit its time limit and the log never said which test had failed.

So: the failing test's name goes to the terminal first, and after each test the module-path cache
is brought up to date, so a report only resolves the few modules that test imported.
"""
import inspect

import pytest


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    if call.excinfo is not None and not call.excinfo.errisinstance(pytest.skip.Exception):
        capture = item.config.pluginmanager.getplugin("capturemanager")
        reporter = item.config.pluginmanager.getplugin("terminalreporter")
        if capture is not None and reporter is not None:
            with capture.global_and_fixture_disabled():
                reporter.write_line(f"\n[failure] {item.nodeid} ({call.when}): "
                                    f"{call.excinfo.typename}, building the report")
    yield


def pytest_runtest_logfinish(nodeid, location):
    # A file name no module has makes getmodule() map every module it hasn't seen yet.
    inspect.getmodule(None, "/nonexistent/floorbit-failure-report.py")
