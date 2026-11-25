"""The event report's numbers as Overview tiles (Mike, #898: "Report's numbers become widgets on the
Overview dashboard"). The report page stays, as the printable export.

The stats wall has some of the same numbers (dashboard_event.py), but those tiles are public and go
away with the stats wall; these are the crew's and follow the report.

The numbers come from ``report.build`` without people: counts per event, switch names and seat
numbers, which the crew sees anyway. Not public (the stats wall's tiles are, dashboard_event.py).
"""

TEXTS = {
    'en': {'event_online': 'Most seats online', 'event_moved': 'Data moved', 'rep_peak': 'peak {rate}',
           'event_checked_in': 'Most checked in', 'event_incidents': 'Incidents this event',
           'event_outages': 'Switch outages', 'event_problem_ports': 'Ports with the most trouble',
           'rep_of': 'of {n} seats', 'rep_fixed': '{fixed} fixed · {open} open',
           'rep_half': 'half fixed within {d}', 'rep_switches': 'on {n} switches · longest {d}',
           'rep_still': '{n} still down', 'rep_times': '{n} times', 'rep_none': 'Nothing yet',
           'rep_no_outages': 'No switch went down', 'rep_no_ports': 'No port trouble',
           'rep_min': '{n} min', 'rep_h': '{h} h {m} min', 'rep_s': 'under a minute'},
    'de': {'event_online': 'Meiste Plätze online', 'event_moved': 'Bewegte Daten', 'rep_peak': 'Spitze {rate}',
           'event_checked_in': 'Meiste eingecheckt', 'event_incidents': 'Störungen an diesem Event',
           'event_outages': 'Switch-Ausfälle', 'event_problem_ports': 'Ports mit den meisten Problemen',
           'rep_of': 'von {n} Plätzen', 'rep_fixed': '{fixed} behoben · {open} offen',
           'rep_half': 'die Hälfte in {d} behoben', 'rep_switches': 'an {n} Switches · längster {d}',
           'rep_still': '{n} noch aus', 'rep_times': '{n} Mal', 'rep_none': 'Noch nichts',
           'rep_no_outages': 'Kein Switch ist ausgefallen', 'rep_no_ports': 'Keine Port-Probleme',
           'rep_min': '{n} Min.', 'rep_h': '{h} Std. {m} Min.', 'rep_s': 'unter einer Minute'},
}

TILES = {tid: {'label': tid, 'size': 'small', 'refresh': 60, 'feature': 'report'}
         for tid in ('event_online', 'event_moved', 'event_checked_in', 'event_incidents', 'event_outages',
                     'event_problem_ports')}
TOP = 8


def _took(text, seconds):
    mins = int(max(0, seconds or 0) // 60)
    if mins < 1:
        return text['rep_s']
    return text['rep_min'].format(n=mins) if mins < 60 else text['rep_h'].format(h=mins // 60, m=mins % 60)


def widget(tile, lang, r):
    """Tile ``tile`` from the report ``r`` (``report.build``, without people)."""
    from .dashboard_core import NONE, rate
    text = TEXTS.get(lang, TEXTS['en'])
    if tile == 'event_online':
        if not r.get('online_max'):
            return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['rep_none'], 'link': '/report'}
        return {'type': 'stat', 'value': r['online_max'], 'unit': '', 'min': 0,
                'max': r.get('seats') or r['online_max'], 'sub': text['rep_of'].format(n=r.get('seats') or 0),
                'link': '/report'}
    if tile == 'event_moved':
        if not r.get('bytes_moved'):
            return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['rep_none'], 'link': '/report'}
        peak = (r.get('peak') or {}).get('bps')
        return {'type': 'stat', 'value': r['bytes_moved'], 'unit': 'B', 'link': '/report',
                **({'sub': text['rep_peak'].format(rate=rate(peak))} if peak else {})}
    if tile == 'event_checked_in':
        if not r.get('checked_in_max'):
            return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['rep_none'], 'link': '/checkins'}
        return {'type': 'stat', 'value': r['checked_in_max'], 'unit': '', 'min': 0,
                'max': r.get('seats') or r['checked_in_max'], 'sub': text['rep_of'].format(n=r.get('seats') or 0),
                'link': '/checkins'}
    if tile == 'event_incidents':
        found = r.get('incidents') or {}
        if not found.get('total'):
            return {'type': 'stat', 'value': 0, 'unit': '', 'sub': text['rep_none'], 'link': '/report'}
        sub = text['rep_fixed'].format(fixed=found.get('fixed', 0), open=found.get('open', 0))
        if found.get('median_fix_s') is not None:
            sub += ' · ' + text['rep_half'].format(d=_took(text, found['median_fix_s']))
        return {'type': 'stat', 'value': found['total'], 'unit': '', 'sub': sub, 'link': '/report',
                'tone': 'warn' if found.get('open') else ''}
    if tile == 'event_outages':
        rows = r.get('outages') or []
        if not rows:
            return {'type': 'stat', 'value': 0, 'unit': '', 'sub': text['rep_no_outages'], 'link': '/report'}
        still = sum(1 for o in rows if o.get('still_down'))
        sub = text['rep_switches'].format(n=len(rows), d=_took(text, max(o.get('longest_s') or 0 for o in rows)))
        if still:
            sub += ' · ' + text['rep_still'].format(n=still)
        return {'type': 'stat', 'value': sum(o.get('times') or 0 for o in rows), 'unit': '', 'sub': sub,
                'link': '/report', 'tone': 'err' if still else 'warn'}
    if tile == 'event_problem_ports':
        ports = (r.get('problem_ports') or [])[:TOP]
        if not ports:
            return {'type': 'list', 'items': [], 'sub': text['rep_no_ports']}
        top = max(p.get('count') or 0 for p in ports) or 1
        return {'type': 'list', 'items': [
            {'label': f"{p.get('switch') or ''} {p.get('port') or ''}".strip(),
             'value': text['rep_times'].format(n=p.get('count') or 0),
             'tone': 'warn', 'number': (p.get('count') or 0) / top, 'max': 1,
             **({'sub': p['seat']} if p.get('seat') else {})}
            for p in ports]}
    raise KeyError(tile)
