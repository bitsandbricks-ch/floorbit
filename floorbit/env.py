"""Numbers from environment variables, read without stopping the app on a typo."""
import math
import os


def number(name, default, kind=int, minimum=None):
    """``name`` as ``kind``; ``default`` when it is unset, empty or not a number.

    A bad value used to stop Floorbit at start with a bare traceback (a crash loop under
    Kubernetes); now the log names the variable and the default it uses instead.
    """
    raw = (os.environ.get(name) or '').strip()
    value = default
    if raw:
        try:
            parsed = kind(raw)
            if not math.isfinite(parsed):
                raise ValueError(raw)
            value = parsed
        except ValueError:
            print(f'[config] {name}={raw!r} is not a number; using {default}')
    if minimum is not None and value < minimum:
        print(f'[config] {name}={raw!r} is below {minimum}; using {minimum}')
        value = minimum
    return value
