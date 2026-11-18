"""The words the demo writes into the floor plan and the event: hall and range names, plan labels,
incidents, status updates and the schedule. English, or Swiss German with
``FLOORBIT_DEMO_LANGUAGE=de`` ("ss", never "ß"). What the demo plugin reports live (health tiles,
findings) is translated per viewer like any other server text (floorbit/locales/de-CH.json).
"""
import os

TEXTS = {
    'en': {
        'main_hall': 'Main hall', 'side_hall': 'Side hall', 'range': 'Seat range {}', 'block': 'Block {}',
        'board_west': 'West wall', 'board_east': 'East wall', 'rack': 'Network rack', 'row': '{} row {}',
        'stage': 'Main stage', 'entrance': 'Entrance',
        'isp': 'ISP {}', 'lancache_dns': 'LAN cache DNS', 'provider_dns': 'Provider DNS',
        'incidents': [
            # (where, problem, title, status, minutes ago, assignee, team, notes)
            ('seat:B-5', 'slow', 'Slow connection', 'assigned', 25, 'alex', 'access',
             ['Port runs at half duplex. Bringing a new cable.']),
            ('switch:sw-c-02', None, 'sw-c-02 keeps dropping off', 'assigned', 70, 'alex', 'access',
             ['Uplink came up at 1G as well: probably the optic. Spare is in the crew room.']),
            ('seat:A-7', 'no-internet', 'No internet at the seat', 'open', 6, None, 'operations', []),
            ('circuit:c2', None, 'C row 2 near its limit', 'open', 15, None, 'electrics',
             ['Someone brought a fridge. Asked them to plug it in at the bar.']),
            ('seat:D-17', 'slow', 'Slow connection', 'fixed', 180, 'sam', 'access',
             ['CRC errors on the port.', 'Swapped the cable, errors stopped.']),
            ('seat:C-3', 'power', 'No power at the seat', 'fixed', 300, 'robin', 'electrics',
             ['Power strip was switched off.']),
        ],
        'status_updates': [
            (40, 'degraded', 'Firewall 3', 'Firewall 3 is down. Its seats now go through firewall 4: '
                                            'you may notice a short break.'),
            (600, 'operational', '', 'Doors are open and the network is up. Have fun!'),
        ],
        'schedule': [
            # (hour of the day, counted from today's midnight: -8 is 16:00 yesterday; length in hours or None,
            #  kind, title, where)
            (-8, None, 'other', 'Doors open', 'Entrance'),
            (-6, 1, 'talk', 'Welcome and house rules', 'Main stage'),
            (-5, 1, 'meal', 'Dinner', 'Bar'),
            (2, 6, 'quiet', 'Quiet hours: lights dimmed', ''),
            (8, 2, 'meal', 'Breakfast', 'Bar'),
            (10, 4, 'tournament', 'Demo Cup: quarter-finals', 'Main stage'),
            (15, 1, 'tournament', 'Demo Cup: final', 'Main stage'),
            (20, None, 'other', 'Doors close', 'Entrance'),
        ],
        'layouts': [('noc-wall', 'NOC wall', 4), ('ops-desk', 'Ops desk', 2)],
    },
    'de': {
        'main_hall': 'Haupthalle', 'side_hall': 'Nebenhalle', 'range': 'Sitzbereich {}', 'block': 'Block {}',
        'board_west': 'Westwand', 'board_east': 'Ostwand', 'rack': 'Netzwerk-Rack', 'row': '{} Reihe {}',
        'stage': 'Hauptbühne', 'entrance': 'Eingang',
        'isp': 'Provider {}', 'lancache_dns': 'LAN-Cache-DNS', 'provider_dns': 'Provider-DNS',
        'incidents': [
            ('seat:B-5', 'slow', 'Langsame Verbindung', 'assigned', 25, 'alex', 'access',
             ['Port läuft auf Halbduplex. Bringe ein neues Kabel.']),
            ('switch:sw-c-02', None, 'sw-c-02 fällt immer wieder aus', 'assigned', 70, 'alex', 'access',
             ['Uplink kam auch nur mit 1G hoch: wohl das Modul. Ersatz liegt im Crew-Raum.']),
            ('seat:A-7', 'no-internet', 'Kein Internet am Platz', 'open', 6, None, 'operations', []),
            ('circuit:c2', None, 'C Reihe 2 nahe am Limit', 'open', 15, None, 'electrics',
             ['Jemand hat einen Kühlschrank mitgebracht. Gebeten, ihn an der Bar einzustecken.']),
            ('seat:D-17', 'slow', 'Langsame Verbindung', 'fixed', 180, 'sam', 'access',
             ['CRC-Fehler am Port.', 'Kabel getauscht, keine Fehler mehr.']),
            ('seat:C-3', 'power', 'Kein Strom am Platz', 'fixed', 300, 'robin', 'electrics',
             ['Steckerleiste war ausgeschaltet.']),
        ],
        'status_updates': [
            (40, 'degraded', 'Firewall 3', 'Firewall 3 ist ausgefallen. Ihre Plätze laufen jetzt über Firewall 4: '
                                            'kurze Unterbrüche sind möglich.'),
            (600, 'operational', '', 'Die Türen sind offen und das Netz läuft. Viel Spass!'),
        ],
        'schedule': [
            (-8, None, 'other', 'Türöffnung', 'Eingang'),
            (-6, 1, 'talk', 'Begrüssung und Hausregeln', 'Hauptbühne'),
            (-5, 1, 'meal', 'Abendessen', 'Bar'),
            (2, 6, 'quiet', 'Nachtruhe: Licht gedimmt', ''),
            (8, 2, 'meal', 'Frühstück', 'Bar'),
            (10, 4, 'tournament', 'Demo Cup: Viertelfinals', 'Hauptbühne'),
            (15, 1, 'tournament', 'Demo Cup: Final', 'Hauptbühne'),
            (20, None, 'other', 'Ende', 'Eingang'),
        ],
        'layouts': [('noc-wall', 'NOC-Wand', 4), ('ops-desk', 'Ops-Pult', 2)],
    },
}


def language():
    """``de`` when FLOORBIT_DEMO_LANGUAGE asks for German (de, de-CH, de-DE...), else ``en``."""
    lang = os.environ.get('FLOORBIT_DEMO_LANGUAGE', '').strip().lower()
    return 'de' if lang.startswith('de') else 'en'


def text():
    return TEXTS[language()]
