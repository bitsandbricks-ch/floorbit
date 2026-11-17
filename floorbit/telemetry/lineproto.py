"""InfluxDB line protocol, the format Telegraf (on the agent, in the sidecar, or on an OPNsense or
pfSense firewall) sends telemetry in: ``measurement,tag=v field=1i,other="text" 1700000000000000000``.

Only what Telegraf writes is needed: escaped commas, spaces and equals signs in names and tags,
quoted strings with escaped quotes and backslashes in fields, the i/u integer suffixes, booleans,
and an optional timestamp in nanoseconds. A line that doesn't parse is skipped and counted, never
fatal: one bad sender must not drop the batch.
"""
from dataclasses import dataclass, field

MAX_LINE = 64 * 1024


@dataclass
class Point:
    measurement: str
    tags: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    time: float | None = None       # seconds; None: when it arrived


class BadLine(ValueError):
    pass


def _split(text, sep, quotes=False):
    """Split on ``sep`` outside backslash escapes (and, for fields, outside double quotes)."""
    if '\\' not in text and not (quotes and '"' in text):
        return text.split(sep)    # most lines: str.split, ten times faster than the walk below
    out, cur, i, quoted = [], [], 0, False
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            cur.append(text[i:i + 2])
            i += 2
            continue
        if quotes and ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quoted:
        raise BadLine('unclosed quote')
    out.append(''.join(cur))
    return out


def _unescape(text):
    if '\\' not in text:
        return text
    out, i = [], 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in ' ,="\\':
            out.append(text[i + 1])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def _value(raw):
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"'):
            raise BadLine('bad string')
        return _unescape(raw[1:-1])
    if raw in ('t', 'T', 'true', 'True', 'TRUE'):
        return True
    if raw in ('f', 'F', 'false', 'False', 'FALSE'):
        return False
    if raw[-1:] in ('i', 'u'):
        return int(raw[:-1])
    return float(raw)


def _fast_parts(line):
    """[head, fields(, time)] without walking the line, when nothing is escaped: the head has no
    quotes, and a time is the digits after the last space. None: take the slow walk."""
    if '\\' in line:
        return None
    head, sep, rest = line.partition(' ')
    if not sep or '"' in head:
        return None
    rest = rest.strip()
    stamp = None
    last = rest.rfind(' ')
    if last > 0 and rest[last + 1:].lstrip('-').isdigit():
        rest, stamp = rest[:last].rstrip(), rest[last + 1:]
    if not rest or (' ' in rest and '"' not in rest):
        return None
    if '"' in rest and rest.count('"') % 2:
        return None
    return [head, rest] if stamp is None else [head, rest, stamp]


def parse_line(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    if len(line) > MAX_LINE:
        raise BadLine('line too long')
    parts = _fast_parts(line)
    if parts is None:
        parts = [p for p in _split(line, ' ', quotes=True) if p != '']
    if len(parts) not in (2, 3):
        raise BadLine('expected measurement, fields and maybe a time')
    head = _split(parts[0], ',')
    measurement = _unescape(head[0])
    if not measurement:
        raise BadLine('no measurement')
    tags = {}
    for item in head[1:]:
        key, sep, value = item.partition('=')
        if not sep:
            raise BadLine('bad tag')
        tags[_unescape(key)] = _unescape(value)
    fields = {}
    for item in _split(parts[1], ',', quotes=True):
        key, sep, value = item.partition('=')
        if not sep or not value:
            raise BadLine('bad field')
        try:
            fields[_unescape(key)] = _value(value)
        except ValueError as exc:
            raise BadLine(f'bad field value {value[:20]!r}') from exc
    stamp = None
    if len(parts) == 3:
        try:
            stamp = int(parts[2]) / 1e9
        except ValueError as exc:
            raise BadLine('bad time') from exc
    return Point(measurement, tags, fields, stamp)


def parse(text):
    """(points, bad line count) of a batch."""
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    points, bad = [], 0
    for line in text.splitlines():
        try:
            point = parse_line(line)
        except BadLine:
            bad += 1
            continue
        if point is not None:
            points.append(point)
    return points, bad


def _esc(text, chars):
    text = str(text)
    for ch in '\\' + chars:
        text = text.replace(ch, '\\' + ch)
    return text


def _format_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return f'{value}i'
    if isinstance(value, float):
        return repr(value)
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def format_point(point):
    """One line, for forwarding to VictoriaMetrics (it speaks the same protocol on /write)."""
    head = _esc(point.measurement, ', ')
    for key in sorted(point.tags):
        if point.tags[key] != '':
            head += f',{_esc(key, ",= ")}={_esc(point.tags[key], ",= ")}'
    fields = ','.join(f'{_esc(k, ",= ")}={_format_value(v)}' for k, v in point.fields.items())
    line = f'{head} {fields}'
    if point.time is not None:
        line += f' {int(point.time * 1e9)}'
    return line
