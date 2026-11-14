"""Runbooks (issue #102): step-by-step fix guides for kinds of incident. See docs/runbooks.md.

A runbook is Markdown with the kinds of incident it is for. The incident board links an incident to
the first runbook for its kind, and the tech's job page shows the steps right on the job.

Kept in data.json under ``runbooks``. Until the crew saves one, Floorbit offers ``STARTERS``: general
first steps, meant to be rewritten with the event's own (where the spare switches are, who to call).

The kind of an incident is the problem the attendee picked on the help page, or else what it is
tied to: a power circuit is ``power``, a switch without a seat is ``switch-down``.
"""
import threading
import time
import uuid

from .store import load_data, save_data

KEY = 'runbooks'
KINDS = ('no-internet', 'slow', 'power', 'switch-down', 'other')
MAX_RUNBOOKS = 100
MAX_TITLE = 80
MAX_BODY = 20000
_lock = threading.Lock()

STARTERS = (
    ('No internet at the seat', ('no-internet',), """\
1. Look at the incident: the port's link and whether the switch sees the seat's MAC.
2. **Link down:** check the cable at the seat and at the switch. Try another cable.
3. **Link up, no MAC:** check the network card is on and set to get an address automatically (DHCP).
4. **MAC seen, still no internet:** ask the player to renew the address, then try a website and a DNS name.
5. Still broken: patch the seat to another port and note which one on the incident.
"""),
    ('Slow connection', ('slow',), """\
1. Look at the speed test on the incident, if the player ran one.
2. Check the port for errors and the speed it linked at. 100 Mbit/s often means a bad cable.
3. Swap the cable, then ask the player to run the speed test again from the help page.
4. If the whole row is slow, look at the switch's uplink on the stats page.
"""),
    ('No power at the seat', ('power',), """\
1. Check the power strip's switch and that it is plugged in.
2. Check the circuit on the Electrics page: is it near its limit or tripped?
3. Do not reset a breaker yourself: call the Electrics team.
"""),
    ('Switch down', ('switch-down',), """\
1. Check the switch has power and its lights are on.
2. Check its uplink cable at both ends.
3. Post an update on the network status page so the players know.
4. Swap in a spare switch if it doesn't come back, and note its name on the incident.
"""),
)


class RunbookError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _starters():
    return [{'id': f'starter-{n}', 'title': title, 'kinds': list(kinds), 'body': body, 'starter': True,
             'updated_at': None, 'by': None} for n, (title, kinds, body) in enumerate(STARTERS, 1)]


def all_runbooks(data=None):
    data = load_data() if data is None else data
    stored = data.get(KEY)
    return list(stored) if isinstance(stored, list) else _starters()


def kind_of(incident):
    problem = incident.get('problem')
    if problem in KINDS:
        return problem
    if incident.get('circuit_id'):
        return 'power'
    if incident.get('switch_id') and not incident.get('seat'):
        return 'switch-down'
    return 'other'


def for_incident(incident, books):
    kind = kind_of(incident)
    return next((b for b in books if kind in b.get('kinds', ())), None)


def _clean(body):
    title = ' '.join(str(body.get('title') or '').split())[:MAX_TITLE]
    if not title:
        raise RunbookError('Give the runbook a title.')
    text = str(body.get('body') or '').replace('\r\n', '\n').strip()
    if not text:
        raise RunbookError('Write the steps.')
    if len(text) > MAX_BODY:
        raise RunbookError(f'A runbook is at most {MAX_BODY} characters.')
    kinds = body.get('kinds') or []
    if not isinstance(kinds, list) or any(k not in KINDS for k in kinds):
        raise RunbookError(f"The kinds are: {', '.join(KINDS)}.")
    return {'title': title, 'body': text, 'kinds': [k for k in KINDS if k in kinds]}


def _change(fn):
    with _lock:
        data = load_data()
        books = all_runbooks(data)
        result = fn(books)
        data[KEY] = books
        save_data(data)
    return result


def add(body, by):
    clean = _clean(body)

    def run(books):
        if len(books) >= MAX_RUNBOOKS:
            raise RunbookError(f'Floorbit keeps at most {MAX_RUNBOOKS} runbooks.')
        book = {'id': uuid.uuid4().hex[:10], **clean, 'starter': False, 'updated_at': time.time(), 'by': by}
        books.append(book)
        return book
    return _change(run)


def update(book_id, body, by):
    def run(books):
        book = next((b for b in books if b['id'] == book_id), None)
        if not book:
            raise RunbookError('No such runbook.', 404)
        book.update(_clean({**book, **body}), starter=False, updated_at=time.time(), by=by)
        return book
    return _change(run)


def delete(book_id):
    def run(books):
        kept = [b for b in books if b['id'] != book_id]
        if len(kept) == len(books):
            raise RunbookError('No such runbook.', 404)
        books[:] = kept
    _change(run)


def move(book_id, step):
    """Up (-1) or down (+1): the first runbook for a kind is the one an incident links to."""
    def run(books):
        i = next((n for n, b in enumerate(books) if b['id'] == book_id), None)
        if i is None:
            raise RunbookError('No such runbook.', 404)
        j = max(0, min(len(books) - 1, i + (1 if step > 0 else -1)))
        books[i], books[j] = books[j], books[i]
    _change(run)
