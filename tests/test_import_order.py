"""Each package imports on its own, whatever is imported first.

`auth` imports `floorbit.env`, which used to pull in every blueprint, which imports `auth` again:
`tests/test_nav.py` run alone failed with a half-initialised `auth`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize('first', ['auth', 'floorbit', 'integrations', 'floorbit.blueprints', 'auth.admin'])
def test_imports_on_its_own(first):
    done = subprocess.run([sys.executable, '-c', f'import {first}; import floorbit; floorbit.create_app'],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
