"""How far a local agent's clock is off from ours, so the times it sends can be put right.

An agent in the hall may run on a box without a battery clock or without NTP, so its clock can be
minutes or days off. Syslog lines keep the time the agent heard them: with the agent's clock
behind, every line looked "late" (kept while the uplink was down), so no log alert fired, and a
clock a day behind dropped every line as past retention. Two agents with different clocks also gave
the same line two times, so the copy wasn't recognised. Each agent request says the agent's time in
``Floorbit-Agent-Clock``; the difference to ours is what its times need."""
import math
import time

HEADER = 'Floorbit-Agent-Clock'
SLACK = 5            # seconds: less than this is the request's own travel time, not a wrong clock
WARN_FROM = 60       # seconds: from here the crew hears about it once per agent

_warned = set()


def offset(agent=None, now=None, log=print):
    """Seconds to add to the calling agent's times; 0 when it didn't say (an older agent) or is close."""
    from flask import has_request_context, request
    raw = request.headers.get(HEADER) if has_request_context() else None
    if not raw:
        return 0.0
    try:
        theirs = float(raw)
    except ValueError:
        return 0.0
    if not math.isfinite(theirs):
        return 0.0
    now = time.time() if now is None else now
    off = now - theirs
    if abs(off) < SLACK:
        return 0.0
    name = (agent or {}).get('name') or '?'
    if abs(off) >= WARN_FROM and name not in _warned:
        _warned.add(name)
        log(f'[agent] {name}: its clock is {_human(off)} {"behind" if off > 0 else "ahead"}; '
            'times it sends are put right. Turn on NTP on that machine.')
    return off


def _human(seconds):
    seconds = abs(seconds)
    if seconds < 120:
        return f'{seconds:.0f} s'
    if seconds < 7200:
        return f'{seconds / 60:.0f} min'
    if seconds < 172800:
        return f'{seconds / 3600:.1f} h'
    return f'{seconds / 86400:.0f} days'
