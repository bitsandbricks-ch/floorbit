"""Reading NetFlow v5, NetFlow v9 and IPFIX (v10) packets into plain flow records.

Every record comes out as ``{'src', 'dst', 'sport', 'dport', 'proto', 'bytes', 'packets', 'end'}``
(addresses as strings, ``end`` in unix seconds). Fields Floorbit has no use for are skipped.

v9 and IPFIX describe their records with templates that come in separate packets, so a
``Templates`` object keeps them per exporter. Data that arrives before its template is dropped (the
exporter resends templates every few minutes); ``Templates.missing`` counts it.
"""
import ipaddress
import struct

# Information elements (the same numbers in v9 and IPFIX, RFC 3954 and IANA's IPFIX registry).
BYTES, PACKETS, PROTO, SPORT, SRC4, DPORT, DST4 = 1, 2, 4, 7, 8, 11, 12
SRC6, DST6 = 27, 28
LAST_SWITCHED, FIRST_SWITCHED = 21, 22          # v9: router uptime in ms
OUT_BYTES, OUT_PACKETS = 23, 24                 # v9: some exporters count the other direction here
TOTAL_BYTES, TOTAL_PACKETS = 85, 86
END_SECONDS, END_MS = 151, 153                  # IPFIX: flowEndSeconds, flowEndMilliseconds
SAMPLING = 34                                   # v9: sampling interval
WANTED = {BYTES, PACKETS, PROTO, SPORT, SRC4, DPORT, DST4, SRC6, DST6, LAST_SWITCHED, OUT_BYTES,
          OUT_PACKETS, TOTAL_BYTES, TOTAL_PACKETS, END_SECONDS, END_MS, SAMPLING}

V5_HEADER = struct.Struct('!HHIIIIBBH')
V5_RECORD = struct.Struct('!4s4s4sHHIIIIHHBBBBHHBBH')
V9_HEADER = struct.Struct('!HHIIII')
IPFIX_HEADER = struct.Struct('!HHIII')
SET_HEADER = struct.Struct('!HH')


class ParseError(ValueError):
    pass


class Templates:
    """Templates per exporter, observation domain and template id."""

    def __init__(self):
        self.known = {}
        self.missing = 0

    def add(self, key, fields):
        self.known[key] = fields

    def get(self, key):
        return self.known.get(key)


def _uint(raw):
    return int.from_bytes(raw, 'big') if raw else 0


def _addr(raw):
    if len(raw) == 4:
        return str(ipaddress.IPv4Address(raw))
    if len(raw) == 16:
        return str(ipaddress.IPv6Address(raw))
    return None


def parse(data, exporter='', templates=None):
    """Flow records in one UDP payload. Raises ParseError for something that isn't flow data."""
    if len(data) < 4:
        raise ParseError('too short')
    version = struct.unpack_from('!H', data)[0]
    if version == 5:
        return _v5(data)
    if templates is None:
        templates = Templates()
    if version == 9:
        return _v9(data, exporter, templates)
    if version == 10:
        return _ipfix(data, exporter, templates)
    raise ParseError(f'not NetFlow or IPFIX (version {version})')


def _v5(data):
    if len(data) < V5_HEADER.size:
        raise ParseError('short v5 header')
    _v, count, uptime, secs, _ns, _seq, _et, _ei, sampling = V5_HEADER.unpack_from(data)
    rate = (sampling & 0x3FFF) or 1
    out = []
    for i in range(count):
        offset = V5_HEADER.size + i * V5_RECORD.size
        if offset + V5_RECORD.size > len(data):
            break
        r = V5_RECORD.unpack_from(data, offset)
        src, dst, _hop, _in, _out, packets, octets, _first, last, sport, dport, _p1, _flags, proto = r[:14]
        out.append({'src': _addr(src), 'dst': _addr(dst), 'sport': sport, 'dport': dport, 'proto': proto,
                    'bytes': octets * rate, 'packets': packets * rate,
                    'end': secs - (uptime - last) / 1000})
    return out


def _sets(data, start, end):
    offset = start
    while offset + SET_HEADER.size <= end:
        set_id, length = SET_HEADER.unpack_from(data, offset)
        if length < SET_HEADER.size or offset + length > end:
            raise ParseError('bad set length')
        yield set_id, offset + SET_HEADER.size, offset + length
        offset += length


def _template_fields(data, offset, count, ipfix):
    fields = []
    for _ in range(count):
        field_id, length = struct.unpack_from('!HH', data, offset)
        offset += 4
        if ipfix and field_id & 0x8000:     # enterprise-specific: skip its number
            offset += 4
            field_id = None
        fields.append((field_id, length))
    return fields, offset


def _templates(data, start, end, key, templates, ipfix):
    offset = start
    while offset + 4 <= end:
        template_id, count = struct.unpack_from('!HH', data, offset)
        offset += 4
        if template_id < 256 or count == 0:
            break   # padding, or a withdrawal
        fields, offset = _template_fields(data, offset, count, ipfix)
        templates.add((*key, template_id), fields)


def _records(data, start, end, fields, header):
    secs, uptime = header
    out = []
    offset = start
    fixed = all(length != 0xFFFF for _f, length in fields)
    size = sum(length for _f, length in fields) if fixed else None
    while offset < end and (size is None or offset + size <= end):
        values = {}
        for field_id, length in fields:
            if length == 0xFFFF:            # IPFIX variable length
                length = data[offset]
                offset += 1
                if length == 255:
                    length = struct.unpack_from('!H', data, offset)[0]
                    offset += 2
            raw = data[offset:offset + length]
            offset += length
            if field_id in WANTED:
                values[field_id] = raw
        if not values:
            break
        out.append(_record(values, secs, uptime))
    return out


def _record(v, secs, uptime):
    octets = _uint(v.get(BYTES) or v.get(TOTAL_BYTES)) + _uint(v.get(OUT_BYTES))
    packets = _uint(v.get(PACKETS) or v.get(TOTAL_PACKETS)) + _uint(v.get(OUT_PACKETS))
    rate = _uint(v.get(SAMPLING)) or 1
    if END_MS in v:
        end = _uint(v[END_MS]) / 1000
    elif END_SECONDS in v:
        end = _uint(v[END_SECONDS])
    elif LAST_SWITCHED in v and uptime is not None:
        end = secs - (uptime - _uint(v[LAST_SWITCHED])) / 1000
    else:
        end = secs
    return {'src': _addr(v.get(SRC4) or v.get(SRC6) or b''), 'dst': _addr(v.get(DST4) or v.get(DST6) or b''),
            'sport': _uint(v.get(SPORT)), 'dport': _uint(v.get(DPORT)), 'proto': _uint(v.get(PROTO)),
            'bytes': octets * rate, 'packets': packets * rate, 'end': end}


def _v9(data, exporter, templates):
    if len(data) < V9_HEADER.size:
        raise ParseError('short v9 header')
    _v, _count, uptime, secs, _seq, source_id = V9_HEADER.unpack_from(data)
    key = (exporter, 9, source_id)
    out = []
    for set_id, start, end in _sets(data, V9_HEADER.size, len(data)):
        if set_id == 0:
            _templates(data, start, end, key, templates, ipfix=False)
        elif set_id >= 256:
            fields = templates.get((*key, set_id))
            if fields is None:
                templates.missing += 1
                continue
            out += _records(data, start, end, fields, (secs, uptime))
    return out


def _ipfix(data, exporter, templates):
    if len(data) < IPFIX_HEADER.size:
        raise ParseError('short IPFIX header')
    _v, length, export_time, _seq, domain = IPFIX_HEADER.unpack_from(data)
    key = (exporter, 10, domain)
    out = []
    for set_id, start, end in _sets(data, IPFIX_HEADER.size, min(length, len(data))):
        if set_id == 2:
            _templates(data, start, end, key, templates, ipfix=True)
        elif set_id >= 256:
            fields = templates.get((*key, set_id))
            if fields is None:
                templates.missing += 1
                continue
            out += _records(data, start, end, fields, (export_time, None))
    return out
