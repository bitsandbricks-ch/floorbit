"""The post-event report as a PDF (issue #22): key figures, two charts and three tables on A4.

Drawn with ``pdf.py``. Texts in English and German; times in the reader's time zone, which the page
passes as ``tz`` (minutes behind UTC, like JavaScript's ``getTimezoneOffset``).
"""
import time

from .pdf import Page, fit, render, text_width

TEXTS = {
    'en': {
        'kicker': 'FLOORBIT · EVENT REPORT', 'title': 'Event report', 'period': '{start} to {end}',
        'generated': 'Made {when}', 'no_data': 'No port reads kept yet: the report fills in while the event runs.',
        'peak': 'Peak bandwidth', 'online': 'Most seats online', 'checked_in': 'Most seats checked in',
        'moved': 'Data moved (estimate)', 'incidents': 'Incidents', 'outages': 'Switch outages',
        'of_seats': 'of {n} seats', 'fixed': '{fixed} fixed, {open} open', 'switches': '{n} switches',
        'median': 'half fixed within {d}', 'from_hourly': 'from the hourly averages',
        'chart_seats': 'Seats over the event', 'chart_bw': 'Bandwidth per hour',
        'legend_online': 'Online (port up)', 'legend_checked': 'Checked in',
        'legend_peak': 'Busiest read', 'legend_avg': 'Average',
        'switch': 'Switch', 'times': 'Times down', 'down_all': 'Down in all', 'longest': 'Longest',
        'still': 'still down', 'none_outages': 'No switch went down.',
        'ports': 'Top problem ports', 'port': 'Port', 'seat': 'Seat', 'problems': 'Problems', 'kinds': 'What',
        'none_ports': 'No port problems were noticed.',
        'opened': 'Opened', 'where': 'Where', 'what': 'What', 'team': 'Team', 'took': 'Fixed after',
        'open': 'open', 'none_incidents': 'No incidents were filed.', 'reported_by': 'Reported by',
        'nick': 'Nick', 'ip': 'IP', 'cut': 'Showing the first {n} of {total}.',
        'people': 'Includes nicks and IPs (asked for by an admin). Handle as personal data.',
        'page': 'Page {n} of {total}',
        'kind': {'flapping': 'flapping', 'errors': 'errors', 'duplex': 'half duplex', 'checkin': 'no check-in'},
        'helpdesk': 'seat report',
    },
    'de': {
        'kicker': 'FLOORBIT · EVENT-BERICHT', 'title': 'Event-Bericht', 'period': '{start} bis {end}',
        'generated': 'Erstellt {when}', 'no_data': 'Noch keine Port-Abfragen gespeichert: Der Bericht füllt '
                                                  'sich während des Events.',
        'peak': 'Spitzen-Bandbreite', 'online': 'Am meisten Plätze online', 'checked_in': 'Am meisten eingecheckt',
        'moved': 'Datenmenge (Schätzung)', 'incidents': 'Störungen', 'outages': 'Switch-Ausfälle',
        'of_seats': 'von {n} Plätzen', 'fixed': '{fixed} behoben, {open} offen', 'switches': '{n} Switches',
        'median': 'die Hälfte in {d} behoben', 'from_hourly': 'aus den Stundenmitteln',
        'chart_seats': 'Plätze über das Event', 'chart_bw': 'Bandbreite pro Stunde',
        'legend_online': 'Online (Port aktiv)', 'legend_checked': 'Eingecheckt',
        'legend_peak': 'Stärkste Abfrage', 'legend_avg': 'Mittel',
        'switch': 'Switch', 'times': 'Ausfälle', 'down_all': 'Gesamt down', 'longest': 'Am längsten',
        'still': 'noch down', 'none_outages': 'Kein Switch ist ausgefallen.',
        'ports': 'Ports mit den meisten Problemen', 'port': 'Port', 'seat': 'Platz', 'problems': 'Probleme',
        'kinds': 'Was', 'none_ports': 'Keine Port-Probleme bemerkt.',
        'opened': 'Eröffnet', 'where': 'Wo', 'what': 'Was', 'team': 'Team', 'took': 'Behoben nach',
        'open': 'offen', 'none_incidents': 'Keine Störungen erfasst.', 'reported_by': 'Gemeldet von',
        'nick': 'Nick', 'ip': 'IP', 'cut': 'Die ersten {n} von {total}.',
        'people': 'Enthält Nicks und IPs (von einem Admin verlangt). Als Personendaten behandeln.',
        'page': 'Seite {n} von {total}',
        'kind': {'flapping': 'Flattern', 'errors': 'Fehler', 'duplex': 'Halbduplex', 'checkin': 'kein Check-in'},
        'helpdesk': 'Platzmeldung',
    },
}

INK = '#111118'
MUTED = '#52525b'
LINE = '#dcdce3'
RAISED = '#eeeef2'
GREEN = '#047857'
CYAN = '#0e7490'
LIGHT_GREEN = '#a7e9cf'
DOWN = '#c81e1e'
MARGIN = 48
DASH = '\u2013'    # for a missing value
TIMES = '\u00d7'


def _nice(top):
    """The axis top: ``top`` rounded up to 1, 2, 2.5, 4 or 5 times a power of ten (four steps)."""
    import math
    if top <= 0:
        return 1
    power = 10 ** math.floor(math.log10(top))
    return next(m * power for m in (1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10) if m * power >= top)


def bps(value):
    value = float(value or 0)
    for unit, step in (('Gbps', 1e9), ('Mbps', 1e6), ('kbps', 1e3)):
        if value >= step:
            return f'{value / step:.1f} {unit}'
    return f'{value:.0f} bps'


def size(value):
    value = float(value or 0)
    for unit, step in (('TB', 1e12), ('GB', 1e9), ('MB', 1e6)):
        if value >= step:
            return f'{value / step:.1f} {unit}'
    return f'{value / 1e3:.0f} kB'


def duration(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return f'{seconds} s'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes} min'
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f'{hours} h {minutes:02d} min'
    return f'{hours // 24} d {hours % 24} h'


class _Doc:
    def __init__(self, tz, lang):
        self.tz = tz
        self.lang = lang
        self.pages = []
        self.y = 0
        self.new_page()

    @property
    def page(self):
        return self.pages[-1]

    def new_page(self):
        self.pages.append(Page())
        self.y = MARGIN

    def need(self, height):
        if self.y + height > self.page.height - MARGIN:
            self.new_page()

    def num(self, text):
        """German writes 4,1 Gbit/s."""
        return text.replace('.', ',') if self.lang == 'de' else text

    def when(self, t, fmt='%d.%m. %H:%M'):
        return time.strftime(fmt, time.gmtime(t - self.tz * 60))


def _figure(page, x, y, w, label, value, sub=''):
    page.rect(x, y, w, 58, fill=RAISED)
    page.text(x + 10, y + 16, fit(label, 8.5, w - 20), size=8.5, color=MUTED)
    page.text(x + 10, y + 36, fit(value, 16, w - 20, bold=True), size=16, bold=True, color=INK)
    if sub:
        page.text(x + 10, y + 50, fit(sub, 7.5, w - 20), size=7.5, color=MUTED)


def _axis_times(doc, x, y, w, h, start, end):
    """Hour marks along the bottom: every 3 or 6 hours, with the day at midnight."""
    span = max(1, end - start)
    step = 3600 * (3 if span <= 36 * 3600 else 6 if span <= 4 * 86400 else 24)
    first = (int(start - doc.tz * 60) // step + 1) * step + doc.tz * 60
    t = first
    while t < end:
        px = x + (t - start) / span * w
        doc.page.line(px, y + h, px, y + h + 3, color=MUTED)
        label = doc.when(t, '%d.%m.') if doc.when(t, '%H') == '00' else doc.when(t, '%H:%M')
        doc.page.text(px, y + h + 12, label, size=7, color=MUTED, align='center')
        t += step


def _chart(doc, title, hours, series, legend, fmt, bars=None):
    """Lines (and bars) over the hours. ``series`` is [(key, colour)], ``bars`` a (key, colour)."""
    page = doc.page
    x, y, w, h = MARGIN + 44, doc.y + 30, page.width - 2 * MARGIN - 44, 120
    page.text(MARGIN, doc.y + 12, title, size=12, bold=True)
    lx = page.width - MARGIN
    for label, color in reversed(legend):
        page.text(lx, doc.y + 12, label, size=8, color=MUTED, align='right')
        lx -= text_width(label, 8) + 4
        page.rect(lx - 8, doc.y + 5, 8, 8, fill=color)
        lx -= 18
    keys = [k for k, _c in series] + ([bars[0]] if bars else [])
    top = _nice(max([h_[k] for h_ in hours for k in keys] + [1]))
    start, end = hours[0]['t'], hours[-1]['t'] + 3600
    span = end - start
    for i in range(5):
        gy = y + h - h * i / 4
        page.line(x, gy, x + w, gy, color=LINE, dash=None if i == 0 else (2, 2))
        page.text(x - 6, gy + 3, doc.num(fmt(top * i / 4)), size=7, color=MUTED, align='right')
    if bars:
        key, color = bars
        bw = max(0.6, w * 3600 / span * 0.7)
        for row in hours:
            bh = row[key] / top * h
            bx = x + (row['t'] - start) / span * w + w * 3600 / span * 0.15
            if bh > 0:
                page.rect(bx, y + h - bh, bw, bh, fill=color)
    for key, color in series:
        points = [(x + (row['t'] + 1800 - start) / span * w, y + h - row[key] / top * h) for row in hours]
        page.polyline(points, color, width=1.4)
    _axis_times(doc, x, y, w, h, start, end)
    doc.y = y + h + 30


def _table(doc, title, columns, rows, empty, note=''):
    """``columns`` is [(label, width, align)]; widths are shares of the page width."""
    doc.need(60)
    page = doc.page
    page.text(MARGIN, doc.y + 12, title, size=12, bold=True)
    doc.y += 22
    if not rows:
        page.text(MARGIN, doc.y + 10, empty, size=9, color=MUTED)
        doc.y += 28
        return
    full = page.width - 2 * MARGIN
    total = sum(c[1] for c in columns)
    widths = [c[1] / total * full for c in columns]

    def header():
        px = MARGIN
        for (label, _w, align), cw in zip(columns, widths, strict=True):
            tx = px + cw - 4 if align == 'right' else px + 4
            doc.page.text(tx, doc.y + 10, fit(label, 8, cw - 8, bold=True), size=8, bold=True, color=MUTED,
                          align=align)
            px += cw
        doc.page.line(MARGIN, doc.y + 15, MARGIN + full, doc.y + 15, color=MUTED)
        doc.y += 18

    header()
    for n, row in enumerate(rows):
        if doc.y + 16 > doc.page.height - MARGIN:
            doc.new_page()
            header()
        if n % 2:
            doc.page.rect(MARGIN, doc.y - 1, full, 15, fill='#f6f6f8')
        px = MARGIN
        for (_l, _w, align), cw, cell in zip(columns, widths, row, strict=True):
            color = DOWN if isinstance(cell, tuple) else INK
            text = cell[0] if isinstance(cell, tuple) else cell
            tx = px + cw - 4 if align == 'right' else px + 4
            doc.page.text(tx, doc.y + 10, fit(text if text is not None else DASH, 8.5, cw - 8), size=8.5,
                          color=color, align=align)
            px += cw
        doc.y += 15
    if note:
        doc.page.text(MARGIN, doc.y + 10, note, size=7.5, color=MUTED)
        doc.y += 14
    doc.y += 16


def pdf(report, lang='en', tz=0):
    lang = lang if lang in TEXTS else 'en'
    tx = TEXTS[lang]
    doc = _Doc(tz, lang)
    page = doc.page
    page.text(MARGIN, doc.y + 8, tx['kicker'], size=8, bold=True, color=GREEN)
    page.text(MARGIN, doc.y + 34, fit(report['event_name'] or tx['title'], 22, page.width - 2 * MARGIN, bold=True),
              size=22, bold=True)
    line = tx['generated'].format(when=doc.when(report['generated'], '%d.%m.%Y %H:%M'))
    if report['start'] and report['end']:
        line = tx['period'].format(start=doc.when(report['start'], '%d.%m.%Y %H:%M'),
                                   end=doc.when(report['end'], '%d.%m.%Y %H:%M')) + ' · ' + line
    page.text(MARGIN, doc.y + 54, line, size=9, color=MUTED)
    doc.y += 70
    if report['people']:
        page.rect(MARGIN, doc.y, page.width - 2 * MARGIN, 20, fill='#fdecec')
        page.text(MARGIN + 8, doc.y + 13, tx['people'], size=8.5, bold=True, color=DOWN)
        doc.y += 28

    found = report['incidents']
    outages = report['outages']
    peak = report['peak'] or {}
    w = (page.width - 2 * MARGIN - 2 * 10) / 3
    figures = [
        (tx['peak'], doc.num(bps(peak.get('bps'))) if peak else DASH, doc.when(peak['at']) if peak.get('at') else ''),
        (tx['online'], str(report['online_max']), tx['of_seats'].format(n=report['seats']) if report['seats'] else ''),
        (tx['checked_in'], str(report['checked_in_max']),
         tx['of_seats'].format(n=report['seats']) if report['seats'] else ''),
        (tx['moved'], doc.num(size(report['bytes_moved'])) if report['hours'] else DASH, tx['from_hourly']),
        (tx['incidents'], str(found['total']), tx['fixed'].format(fixed=found['fixed'], open=found['open'])
         + (' · ' + tx['median'].format(d=duration(found['median_fix_s'])) if found['median_fix_s'] else '')),
        (tx['outages'], str(sum(o['times'] for o in outages)), tx['switches'].format(n=len(outages))),
    ]
    for i, (label, value, sub) in enumerate(figures):
        _figure(page, MARGIN + (i % 3) * (w + 10), doc.y + (i // 3) * 66, w, label, value, sub)
    doc.y += 2 * 66 + 12

    if len(report['hours']) >= 2:
        _chart(doc, tx['chart_seats'], report['hours'], [('online_max', GREEN), ('checked_in', CYAN)],
               [(tx['legend_online'], GREEN), (tx['legend_checked'], CYAN)], lambda v: f'{v:.0f}')
        _chart(doc, tx['chart_bw'], report['hours'], [('avg_bps', GREEN)],
               [(tx['legend_peak'], LIGHT_GREEN), (tx['legend_avg'], GREEN)], bps, bars=('peak_bps', LIGHT_GREEN))
    else:
        page.text(MARGIN, doc.y + 10, tx['no_data'], size=9, color=MUTED)
        doc.y += 30

    _table(doc, tx['outages'], [(tx['switch'], 3, 'left'), (tx['times'], 1.4, 'right'),
                                (tx['down_all'], 1.8, 'right'), (tx['longest'], 1.8, 'right')],
           [[o['switch'], str(o['times']), (duration(o['down_s']) + ' · ' + tx['still'],) if o['still_down']
             else duration(o['down_s']), duration(o['longest_s'])] for o in outages], tx['none_outages'])

    people = report['people']
    cols = [(tx['switch'], 2.2, 'left'), (tx['port'], 1.4, 'left'), (tx['seat'], 1, 'left'),
            (tx['problems'], 1.2, 'right'), (tx['kinds'], 3, 'left')]
    if people:
        cols += [(tx['nick'], 1.6, 'left'), (tx['ip'], 1.8, 'left')]
    rows = []
    for p in report['problem_ports']:
        kinds = ', '.join(f"{tx['kind'].get(k, k)} {n}{TIMES}"
                          for k, n in sorted(p['kinds'].items(), key=lambda kv: -kv[1]))
        row = [p['switch'], p['port'], p['seat'], str(p['count']), kinds]
        if people:
            row += [p.get('nick'), p.get('ip')]
        rows.append(row)
    _table(doc, tx['ports'], cols, rows, tx['none_ports'])

    cols = [(tx['opened'], 1.5, 'left'), (tx['where'], 1.6, 'left'), (tx['what'], 4, 'left'),
            (tx['team'], 1.4, 'left'), (tx['took'], 1.5, 'right')]
    if people:
        cols += [(tx['reported_by'], 1.6, 'left'), (tx['nick'], 1.4, 'left')]
    rows = []
    for i in found['items']:
        where = i['seat'] or i['switch'] or i['circuit']
        title = i['title']
        if i['source'] == 'helpdesk':
            title += f" ({tx['helpdesk']}, {i['reports']}{TIMES})" if i['reports'] > 1 else f" ({tx['helpdesk']})"
        took = duration(i['end'] - i['start']) if i['end'] else (tx['open'],)
        row = [doc.when(i['start']), where, title, i['team'], took]
        if people:
            row += [i.get('reported_by'), i.get('nick')]
        rows.append(row)
    note = tx['cut'].format(n=len(rows), total=found['total']) if found['total'] > len(rows) else ''
    _table(doc, tx['incidents'], cols, rows, tx['none_incidents'], note)

    for n, pg in enumerate(doc.pages, start=1):
        pg.line(MARGIN, pg.height - 34, pg.width - MARGIN, pg.height - 34, color=LINE)
        pg.text(MARGIN, pg.height - 22, 'Floorbit' + (' · ' + report['event_name'] if report['event_name'] else ''),
                size=7.5, color=MUTED)
        pg.text(pg.width - MARGIN, pg.height - 22, tx['page'].format(n=n, total=len(doc.pages)), size=7.5,
                color=MUTED, align='right')
    return render(doc.pages, title=report['event_name'] or tx['title'], author='Floorbit')
