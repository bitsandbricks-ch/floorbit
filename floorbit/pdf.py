"""A small PDF writer: text, lines and filled boxes on A4 pages, with the built-in Helvetica fonts.

Enough for the post-event report (``report_pdf.py``) without a PDF library: the standard 14 fonts
need no embedding, text is Windows-1252 (covers English and German), pages are zlib-compressed.
"""
import zlib

A4 = (595.28, 841.89)

# Helvetica glyph widths (1/1000 em) for ASCII 32-126, from the standard AFM metrics.
_WIDTHS = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
# Bold is a little wider; close enough for fitting text into columns.
_BOLD = 1.06


def text_width(text, size, bold=False):
    total = 0
    for ch in str(text):
        code = ord(ch)
        total += _WIDTHS[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000 * (_BOLD if bold else 1)


def fit(text, size, width, bold=False):
    """``text`` cut with an ellipsis so it fits in ``width`` points."""
    text = str(text)
    if text_width(text, size, bold) <= width:
        return text
    while text and text_width(text + '…', size, bold) > width:
        text = text[:-1]
    return text + '…'


def _escape(text):
    raw = str(text).encode('cp1252', errors='replace')
    return raw.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def _rgb(color):
    color = color.lstrip('#')
    return ' '.join(f'{int(color[i:i + 2], 16) / 255:.3f}' for i in (0, 2, 4))


class Page:
    """One page. Coordinates are points from the top left, like the screen, not PDF's bottom left."""

    def __init__(self, size=A4):
        self.width, self.height = size
        self.ops = []

    def _y(self, y):
        return self.height - y

    def text(self, x, y, text, size=10, bold=False, color='#1a1d21', align='left'):
        if align != 'left':
            w = text_width(text, size, bold)
            x -= w if align == 'right' else w / 2
        font = 'F2' if bold else 'F1'
        self.ops.append(b'BT /%s %.2f Tf %s rg %.2f %.2f Td (' % (font.encode(), size, _rgb(color).encode(),
                                                                    x, self._y(y)) + _escape(text) + b') Tj ET')

    def line(self, x1, y1, x2, y2, color='#c9ced6', width=0.6, dash=None):
        d = b'[%d %d] 0 d ' % dash if dash else b'[] 0 d '
        self.ops.append(d + b'%s RG %.2f w %.2f %.2f m %.2f %.2f l S' % (
            _rgb(color).encode(), width, x1, self._y(y1), x2, self._y(y2)))

    def polyline(self, points, color, width=1.2):
        if len(points) < 2:
            return
        path = b' '.join(b'%.2f %.2f %s' % (x, self._y(y), b'm' if i == 0 else b'l') for i, (x, y) in enumerate(points))
        self.ops.append(b'[] 0 d %s RG %.2f w 1 j %s S' % (_rgb(color).encode(), width, path))

    def rect(self, x, y, w, h, fill=None, stroke=None, width=0.6):
        op = b'B' if fill and stroke else b'f' if fill else b'S'
        parts = []
        if fill:
            parts.append(b'%s rg' % _rgb(fill).encode())
        if stroke:
            parts.append(b'%s RG %.2f w' % (_rgb(stroke).encode(), width))
        parts.append(b'%.2f %.2f %.2f %.2f re %s' % (x, self._y(y + h), w, h, op))
        self.ops.append(b' '.join(parts))

    def stream(self):
        return b'\n'.join(self.ops)


def render(pages, title='', author=''):
    """The PDF file as bytes."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)

    catalog = add(None)
    pages_id = add(None)
    regular = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    bold = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
    kids = []
    for page in pages:
        data = zlib.compress(page.stream())
        content = add(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(data) + data + b'\nendstream')
        kids.append(add(b'<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] '
                        b'/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>'
                        % (pages_id, page.width, page.height, regular, bold, content)))
    objects[catalog - 1] = b'<< /Type /Catalog /Pages %d 0 R >>' % pages_id
    objects[pages_id - 1] = b'<< /Type /Pages /Kids [%s] /Count %d >>' % (
        b' '.join(b'%d 0 R' % k for k in kids), len(kids))
    info = add(b'<< /Title (%s) /Author (%s) /Producer (Floorbit) >>' % (_escape(title), _escape(author)))

    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % n + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    for off in offsets:
        out += b'%010d 00000 n \n' % off
    out += b'trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (
        len(objects) + 1, catalog, info, xref)
    return bytes(out)
