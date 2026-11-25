"""An incident made from a problem hears when that problem ends (issue #882).

A problem is what Floorbit sees and ends by itself; an incident is the work someone does about it
(docs/alerts.md). Once a minute the cluster's leader looks at the open incidents made from a problem
(``from_problem``): when the problem is no longer on the list, the incident gets ``problem_over_at``
and the board hears about it, so whoever has it knows the trouble may be gone. If the same problem
comes back, the mark goes again. The incident itself stays open: closing it is the crew's call.
"""
import threading
import time

from integrations import events

from . import incidents
from .store import load_data

EVERY = 60


def tick(now=None):
    """One look. Returns the ids of the incidents whose mark changed."""
    from . import problems
    now = time.time() if now is None else now
    watched = [i for i in incidents._all(load_data()) if i.get('from_problem') and i['status'] != 'fixed']
    if not watched:
        return []
    body = problems.current(True)
    live = {p['id'] for p in body['problems'] + body['attention']}
    changes = {}
    for i in watched:
        over = i['from_problem'] not in live
        if over and not i.get('problem_over_at'):
            changes[i['id']] = now
        elif not over and i.get('problem_over_at'):
            changes[i['id']] = None
    if changes:
        incidents.mark_problem_over(changes)
        for i in watched:
            if i['id'] in changes:
                action = 'problem_over' if changes[i['id']] else 'problem_back'
                events.publish('incident.changed', {'id': i['id'], 'status': i['status'], 'action': action})
    return sorted(changes)


def _loop(app, stop):
    from . import cluster
    while not stop.wait(EVERY):
        try:
            if cluster.leading():
                with app.app_context():
                    tick()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad look
            print(f'[incidents] problem watch failed: {exc}')


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='problem-watch', daemon=True).start()
    return stop
