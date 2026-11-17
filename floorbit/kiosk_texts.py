"""The kiosk page's texts (templates/kiosk.html, static/js/kiosk.js) in English and Swiss German.

The kiosk is a Jinja page, not React, so its texts live here; ``{n}``-style fields are filled in
by kiosk.js. Standard German comes from the Swiss text through ``i18n.to_germany``.
"""
from . import i18n

EN = {
    'page': 'Kiosk', 'plan': 'Floor plan', 'logo': 'Event logo',
    'up': 'switches up', 'down': 'down', 'unknown': 'unknown', 'seats': 'seats taken',
    'heat': 'Seat colour: traffic from 100 kbit/s (green) to 1 Gbit/s (red)',
    'connecting': 'Connecting…',
    'empty_title': 'Nothing on the floor plan yet',
    'empty_text': 'Place switches and seat blocks in the editor and they show up here.',
    'alerts': 'Switches that are down', 'alerts_title': 'Down',
    'legend': 'Legend', 'sw_up': 'Switch up', 'sw_down': 'Switch down', 'no_status': 'No status',
    'seat_taken': 'Seat taken', 'seat_free': 'Seat free', 'fullscreen': 'Double-click for full screen',
    'powered': 'Powered by',
    'online': 'up', 'offline': 'down', 'status_unknown': 'no status',
    'updated_now': 'updated just now', 'updated_s': 'updated {n}s ago', 'updated_min': 'updated {n} min ago',
    'no_monitoring': 'No switch status (LibreNMS not set up)', 'live': 'Live', 'waiting': 'waiting for data',
    'every': 'Every {n}s', 'loading': 'loading',
    'stale': 'No fresh data since {time}. Status shown may be out of date.',
    'unreachable': 'Cannot reach the server. Retrying…',
    'just_now': 'just now', 'mins': '{n} min', 'hours': '{h} h {m} min', 'more': '+ {n} more',
    'traffic': 'Traffic',
}

DE_CH = {
    'page': 'Kiosk', 'plan': 'Hallenplan', 'logo': 'Event-Logo',
    'up': 'Switches online', 'down': 'offline', 'unknown': 'unbekannt', 'seats': 'Plätze besetzt',
    'heat': 'Platzfarbe: Datenverkehr von 100 kbit/s (grün) bis 1 Gbit/s (rot)',
    'connecting': 'Verbinde…',
    'empty_title': 'Noch nichts auf dem Hallenplan',
    'empty_text': 'Platziere Switches und Sitzblöcke im Editor, dann erscheinen sie hier.',
    'alerts': 'Switches, die offline sind', 'alerts_title': 'Offline',
    'legend': 'Legende', 'sw_up': 'Switch online', 'sw_down': 'Switch offline', 'no_status': 'Kein Status',
    'seat_taken': 'Platz besetzt', 'seat_free': 'Platz frei', 'fullscreen': 'Doppelklick für Vollbild',
    'powered': 'Powered by',
    'online': 'online', 'offline': 'offline', 'status_unknown': 'kein Status',
    'updated_now': 'gerade aktualisiert', 'updated_s': 'vor {n} s aktualisiert',
    'updated_min': 'vor {n} min aktualisiert',
    'no_monitoring': 'Kein Switch-Status (LibreNMS nicht eingerichtet)', 'live': 'Live', 'waiting': 'warte auf Daten',
    'every': 'Alle {n} s', 'loading': 'lädt',
    'stale': 'Keine frischen Daten seit {time}. Der Status ist vielleicht veraltet.',
    'unreachable': 'Server nicht erreichbar. Neuer Versuch…',
    'just_now': 'gerade eben', 'mins': '{n} min', 'hours': '{h} h {m} min', 'more': '+ {n} weitere',
    'traffic': 'Datenverkehr',
}


def texts(lang):
    """``lang`` as nav.language() gives it: 'en', 'de-CH' or 'de'."""
    if lang == 'de-CH':
        return DE_CH
    if lang == 'de':
        return {k: i18n.to_germany(v) for k, v in DE_CH.items()}
    return EN
