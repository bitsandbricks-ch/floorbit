"""Tournament brackets (issue #107): single elimination, for the crew and a public big-screen view.

A bracket is rounds of matches. Leads make one from a list of teams (byes fill it up to a power of
two) and enter scores and winners; a winner moves on to the next round by itself. A plugin that
uses ``brackets`` (a tournament tool such as Toornament or start.gg) can send brackets instead:
those are read-only here and replaced on every import, like imported cables.

Each bracket can belong to a match zone (floorbit/tournament.py), and each match can name its seats
("A-1..A-5, B-1..B-5"); the crew view links them to the floor plan and names the match zone they
are in. The public view (``/bracket``) shows team names, scores and the zone's name, never seats.

Kept in data.json under ``brackets``: a list of
``{"id", "name", "zone_id", "source", "plugin", "rounds": [[match, ...], ...], "updated_at", "by"}``,
a match being ``{"id", "a": {"name", "score"}, "b": {...}, "status", "winner", "seats", "station"}``.
"""
import threading
import time
import uuid

from . import tournament
from .store import load_data, save_data

KEY = 'brackets'
MAX_BRACKETS = 20
MAX_TEAMS = 128
MAX_NAME = 60
STATUSES = ('waiting', 'live', 'done')
_lock = threading.Lock()


class BracketError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def all_brackets(data=None):
    data = load_data() if data is None else data
    return [b for b in data.get(KEY) or [] if isinstance(b, dict) and b.get('id')]


def _name(value):
    return ' '.join(str(value or '').split())[:MAX_NAME] or None


def _side(name=None, score=None):
    return {'name': _name(name), 'score': score}


def _match(r, i, a=None, b=None):
    return {'id': f'r{r + 1}m{i + 1}', 'a': _side(a), 'b': _side(b), 'status': 'waiting', 'winner': None,
            'seats': [], 'station': ''}


def seeded(teams):
    """Round one with the teams in seed order (1 v n, 2 v n-1 ...), byes for the top seeds."""
    size = 2
    while size < len(teams):
        size *= 2
    padded = list(teams) + [None] * (size - len(teams))
    # The classic order puts seed 1 and seed 2 in different halves.
    order = [1]
    while len(order) < size:
        n = len(order) * 2 + 1
        order = [x for s in order for x in (s, n - s)]
    pairs = [(padded[order[i] - 1], padded[order[i + 1] - 1]) for i in range(0, size, 2)]
    rounds = [[_match(0, i, a, b) for i, (a, b) in enumerate(pairs)]]
    while len(rounds[-1]) > 1:
        r = len(rounds)
        rounds.append([_match(r, i) for i in range(len(rounds[-1]) // 2)])
    return rounds


def advance(rounds):
    """Byes in round one win by themselves; every winner's name moves to the next round."""
    for m in rounds[0]:
        a, b = m['a']['name'], m['b']['name']
        if (a is None) != (b is None):
            m.update(winner='a' if a else 'b', status='done')
    for r in range(len(rounds) - 1):
        for i, m in enumerate(rounds[r]):
            nxt = rounds[r + 1][i // 2]
            side = 'a' if i % 2 == 0 else 'b'
            won = m['winner'] and m[m['winner']]['name']
            if nxt[side]['name'] != won:
                nxt[side] = _side(won)
                # Someone else moved up: the next match's result no longer stands.
                if nxt['winner'] == side or nxt['status'] == 'done':
                    nxt.update(winner=None, status='waiting')
    return rounds


def _teams(raw):
    teams = raw if isinstance(raw, list) else str(raw or '').splitlines()
    teams = [_name(t) for t in teams]
    teams = [t for t in teams if t]
    if len(teams) < 2:
        raise BracketError('A bracket needs at least two teams, one per line.')
    if len(teams) > MAX_TEAMS:
        raise BracketError(f'A bracket has at most {MAX_TEAMS} teams.')
    if len({t.lower() for t in teams}) != len(teams):
        raise BracketError('Two teams have the same name.')
    return teams


def _zone(zone_id, data):
    if not zone_id:
        return None
    if not any(z['id'] == zone_id for z in tournament.zones(data)):
        raise BracketError('No such match zone.')
    return zone_id


def _change(fn):
    with _lock:
        data = load_data()
        items = all_brackets(data)
        result = fn(items, data)
        data[KEY] = items
        save_data(data)
    return result


def _find(items, bracket_id, editable=True):
    b = next((x for x in items if x['id'] == bracket_id), None)
    if b is None:
        raise BracketError('No such bracket.', 404)
    if editable and b.get('source') == 'import':
        raise BracketError(f"This bracket comes from {b.get('plugin') or 'a plugin'}: change it there.", 409)
    return b


def create(body, by):
    name = _name(body.get('name'))
    if not name:
        raise BracketError('Give the bracket a name.')
    teams = _teams(body.get('teams'))

    def run(items, data):
        if len(items) >= MAX_BRACKETS:
            raise BracketError(f'At most {MAX_BRACKETS} brackets.')
        b = {'id': uuid.uuid4().hex[:10], 'name': name, 'zone_id': _zone(body.get('zone_id'), data),
             'source': 'floorbit', 'plugin': None, 'rounds': advance(seeded(teams)),
             'updated_at': time.time(), 'by': by}
        items.append(b)
        return b
    return _change(run)


def update(bracket_id, body, by):
    def run(items, data):
        b = _find(items, bracket_id, editable='zone_id' not in body or 'name' in body)
        if 'name' in body:
            b['name'] = _name(body['name']) or b['name']
        if 'zone_id' in body:
            b['zone_id'] = _zone(body.get('zone_id'), data)
        b.update(updated_at=time.time(), by=by)
        return b
    return _change(run)


def delete(bracket_id):
    def run(items, data):
        b = _find(items, bracket_id, editable=False)
        items.remove(b)
    return _change(run)


def _score(value):
    if value in (None, ''):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise BracketError('A score is a whole number.') from None
    if not 0 <= n <= 9999:
        raise BracketError('A score is 0 to 9999.')
    return n


def set_match(bracket_id, match_id, body, by):
    """Scores, status, winner, seats and station of one match. A winner makes it done."""
    def run(items, data):
        b = _find(items, bracket_id)
        m = next((x for rnd in b['rounds'] for x in rnd if x['id'] == match_id), None)
        if m is None:
            raise BracketError('No such match.', 404)
        if 'a_score' in body:
            m['a']['score'] = _score(body['a_score'])
        if 'b_score' in body:
            m['b']['score'] = _score(body['b_score'])
        if 'status' in body:
            if body['status'] not in STATUSES:
                raise BracketError(f"The status is one of: {', '.join(STATUSES)}.")
            m['status'] = body['status']
        if 'winner' in body:
            winner = body['winner'] or None
            if winner not in (None, 'a', 'b'):
                raise BracketError('The winner is a or b.')
            if winner and not m[winner]['name']:
                raise BracketError('That side has no team yet.')
            m['winner'] = winner
            if winner:
                m['status'] = 'done'
            elif m['status'] == 'done':
                m['status'] = 'waiting'
        if 'seats' in body:
            if str(body['seats'] or '').strip():
                try:
                    blocks, seats = tournament.parse_seats(body['seats'], data)
                except tournament.TournamentError as exc:
                    raise BracketError(str(exc)) from None
                m['seats'] = blocks + seats
            else:
                m['seats'] = []
        if 'station' in body:
            m['station'] = ' '.join(str(body['station'] or '').split())[:MAX_NAME]
        advance(b['rounds'])
        b.update(updated_at=time.time(), by=by)
        return b
    return _change(run)


# ── Plugins ──────────────────────────────────────────────────────────────────────────────────

def sources(registry):
    return registry.feeders('brackets')


def _from_plugin(raw):
    """A plugin's bracket in Floorbit's shape. Rounds of matches with names, scores, status, winner."""
    name = _name(raw.get('name'))
    rounds = raw.get('rounds')
    if not name or not isinstance(rounds, list) or not rounds or not all(isinstance(r, list) and r for r in rounds):
        raise BracketError('A bracket needs a name and rounds of matches.')
    out = []
    for r, rnd in enumerate(rounds[:10]):
        row = []
        for i, m in enumerate(rnd[:256]):
            m = m if isinstance(m, dict) else {}
            match = _match(r, i, (m.get('a') or {}).get('name'), (m.get('b') or {}).get('name'))
            for side in ('a', 'b'):
                try:
                    match[side]['score'] = _score((m.get(side) or {}).get('score'))
                except BracketError:
                    match[side]['score'] = None
            match['status'] = m.get('status') if m.get('status') in STATUSES else 'waiting'
            match['winner'] = m.get('winner') if m.get('winner') in ('a', 'b') else None
            match['station'] = _name(m.get('station')) or ''
            row.append(match)
        out.append(row)
    return {'name': name, 'ext_id': str(raw.get('id') or name)[:100], 'rounds': out}


def import_from(registry, by):
    """Replace each answering plugin's brackets with what it has now. Returns (count, errors)."""
    from .plugins import PluginError
    found, errors, answered = [], [], set()
    for spec in sources(registry):
        try:
            for raw in registry.call(spec, 'brackets') or []:
                try:
                    found.append((spec, _from_plugin(raw if isinstance(raw, dict) else {})))
                except BracketError as exc:
                    errors.append(f'{spec.name}: {exc}')
            answered.add(spec.name)
        except PluginError as exc:
            errors.append(f'{spec.name}: {exc}')
    if errors and not answered:
        raise BracketError('; '.join(errors), 502)

    def run(items, data):
        old = {(b.get('plugin'), b.get('ext_id')): b for b in items if b.get('source') == 'import'}
        kept = [b for b in items if b.get('source') != 'import' or b.get('plugin') not in answered]
        new = []
        for spec, b in found:
            prev = old.get((spec.name, b['ext_id']))
            new.append({'id': prev['id'] if prev else uuid.uuid4().hex[:10], **b,
                        'zone_id': prev.get('zone_id') if prev else None, 'source': 'import', 'plugin': spec.name,
                        'updated_at': time.time(), 'by': by})
        items[:] = (kept + new)[:MAX_BRACKETS]
        return len(new)
    return _change(run), errors


# ── Views ────────────────────────────────────────────────────────────────────────────────────

ROUND_NAMES = {1: 'final', 2: 'semi', 3: 'quarter'}


def round_label(index, count):
    """'final', 'semi', 'quarter' or None (then the page says "Round n")."""
    return ROUND_NAMES.get(count - index)


def public_view(b, zones_by_id):
    """What /bracket shows: no seats, no who-changed-what."""
    zone = zones_by_id.get(b.get('zone_id'))
    count = len(b['rounds'])
    return {
        'id': b['id'], 'name': b['name'], 'zone': zone['name'] if zone else None,
        'rounds': [{'n': r + 1, 'label': round_label(r, count),
                    'matches': [{'id': m['id'], 'a': m['a'], 'b': m['b'], 'status': m['status'], 'winner': m['winner'],
                                 'station': m.get('station') or ''} for m in rnd]}
                   for r, rnd in enumerate(b['rounds'])],
        'champion': (lambda f: f[f['winner']]['name'] if f['winner'] else None)(b['rounds'][-1][0]),
        'live': sum(1 for rnd in b['rounds'] for m in rnd if m['status'] == 'live'),
    }
