"""How a seat block names its seats (issue: Mike's hall plan, rows with letters).

Two ways, picked per block with ``naming``:

- ``block`` (the old way, and the default for blocks saved before): the block's name and a running
  number, ``A-1`` to ``A-16`` over all its rows.
- ``rows``: every row of the block is a row of the hall with its own letter, counted on from
  ``row_start`` (``A``, ``B``, ... ``Z``, ``AA``), and the seats in it numbered from 1: ``C-1``,
  ``C-2``. Several blocks with ``row_start`` C, E, G make a hall like the usual LAN layout.

The rotation turns the numbering with the block, so seat 1 and row A are where a reader starts:
left and top as seen on the plan. ``reverse_numbers`` runs the numbers the other way.
The floor plan pages draw the seats the server lays out (blueprints/screen.py ``plan``), so no other copy
of these rules exists.
"""
import re

NAMINGS = ('block', 'rows')
ROW_LABELS = ('start', 'end', 'both', 'none')
LETTERS_RE = re.compile(r'^[A-Z]{1,2}\Z')


def row_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA, like spreadsheet columns."""
    out = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        out = chr(65 + rest) + out
    return out


def letter_index(letters):
    """``row_letter`` backwards: A -> 0, AA -> 26."""
    n = 0
    for ch in str(letters).upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _quarter(block):
    return round((int(block.get('rotation') or 0) % 360) / 90) % 4


def _block_numbering(block, cols, rows):
    base = list(range(1, cols * rows + 1))
    rotation = int(block.get('rotation') or 0) % 360
    if rotation < 90:
        ordered = base
    elif rotation < 180:
        ordered = [n for r in range(rows) for n in reversed(base[r * cols:(r + 1) * cols])]
    elif rotation < 270:
        ordered = list(reversed(base))
    else:
        ordered = [n for r in reversed(range(rows)) for n in base[r * cols:(r + 1) * cols]]
    if block.get('reverse_numbers'):
        ordered = list(reversed(ordered))
    prefix = f"{str(block['name']).upper()}-" if block.get('name') else ''
    return [[f'{prefix}{n}' for n in ordered[r * cols:(r + 1) * cols]] for r in range(rows)]


def row_letters(block):
    """The letter of each row of a ``rows`` block, top row of the block first; [] otherwise."""
    if block.get('naming') != 'rows':
        return []
    rows = int(block.get('rows') or 0)
    start = letter_index(block.get('row_start') or 'A')
    # Turned upside down or a quarter clockwise, the block's last row is the one read first.
    flip = _quarter(block) in (1, 2)
    return [row_letter(start + (rows - 1 - r if flip else r)) for r in range(rows)]


def label(block):
    """What people call a block: its name, or for a block named by its rows (which has none), the
    row letters it holds (C to D, with an en dash). Never empty for a block with rows, so no picker
    shows a dash."""
    if block.get('name'):
        return str(block['name'])
    letters = sorted(row_letters(block), key=letter_index)
    if not letters:
        return ''
    return letters[0] if len(letters) == 1 else f'{letters[0]}\u2013{letters[-1]}'


def row_names(block):
    """Each row's name, top row of the block first: its letter in a ``rows`` block, else 1, 2, ..."""
    return row_letters(block) or [str(n + 1) for n in range(int(block.get('rows') or 0))]


def row_id(block, index):
    """A row's id: its block and its place in the block (1 is the top row as drawn)."""
    return f"{block['id']}:{index}"


def hall_rows(data):
    """Every row of the hall, by name: ``[{id, block, block_label, index, name, naming, seats}]``,
    blocks in the order people read them, rows top first. The crew works a row at a time: a walker
    takes a row, a row is patched to one switch and fed by one circuit."""
    out = []
    blocks = sorted((b for b in data.get('seat_blocks') or [] if b.get('id')),
                    key=lambda b: (letter_index(row_letters(b)[0]) if row_letters(b) else 10**6,
                                   label(b).lower()))
    for block in blocks:
        names = row_names(block)
        for i, row in enumerate(block_rows(block)):
            out.append({'id': row_id(block, i + 1), 'block': block['id'], 'block_label': label(block),
                        'index': i + 1, 'name': names[i] if i < len(names) else str(i + 1),
                        'naming': block.get('naming') or 'block', 'seats': [s.upper() for s in row]})
    return out


def row_label(row):
    """What a ``hall_rows`` row is called in pickers and lists: its letter, or for a block numbered
    as a whole, the block and the row ("A 2")."""
    return row['name'] if row['naming'] == 'rows' else f"{row['block_label']} {row['name']}".strip()


def pick_rows(data, ids):
    """The rows behind ``ids`` (``hall_rows`` ids), in the order given; ValueError naming the first
    unknown one. Each row comes once."""
    by_id = {r['id']: r for r in hall_rows(data)}
    picked, seen = [], set()
    for raw in ids if isinstance(ids, list) else []:
        key = str(raw or '').strip()
        if key in seen:
            continue
        if key not in by_id:
            raise ValueError(key)
        seen.add(key)
        picked.append(by_id[key])
    return picked


def seat_one_first(block):
    """Is seat 1 of each row in the block's first column? Decides where "start" puts a row letter."""
    first = _quarter(block) in (0, 1)
    return first != bool(block.get('reverse_numbers'))


def block_rows(block):
    """The seat numbers of each row of a seat block as drawn, top row first, columns left to right
    (before the rotation)."""
    cols, rows = int(block.get('cols') or 0), int(block.get('rows') or 0)
    if block.get('naming') != 'rows':
        return _block_numbering(block, cols, rows)
    one_first = seat_one_first(block)
    return [[f'{letter}-{c + 1 if one_first else cols - c}' for c in range(cols)] for letter in row_letters(block)]


def seats(block):
    return [s for row in block_rows(block) for s in row]


_TYPED_RE = re.compile(r'([A-Z0-9]*[A-Z])\s*[-_ ]?\s*0*(\d{1,4})')


def typed_forms(text):
    """What someone may have meant by a typed seat, most literal first: "a3", "A 3" and "A03"
    all mean ``A-3``. People type what's on the ticket, not the plan's spelling."""
    seat = re.sub(r'\s+', ' ', str(text or '').strip()).upper()
    forms = [seat] if seat else []
    m = _TYPED_RE.fullmatch(seat)
    if m and f'{m[1]}-{int(m[2])}' not in forms:
        forms.append(f'{m[1]}-{int(m[2])}')
    return forms


def match_typed(text, known):
    """The seat in ``known`` that ``text`` means, or None."""
    return next((form for form in typed_forms(text) if form in known), None)
