"""What the agent's Captive Portal API answers (issue #473, RFC 8908). Docs: docs/seat-mapping.md.

The agent serves ``/.well-known/captive-portal`` on the event network. DHCP option 114 points
clients at it. It asks the hosted Floorbit, through ``GET /api/agent/v1/captive``, which client IPs
are done, and keeps the answer, so it goes on answering while the hosted side is away.

An IP counts as done when it belongs to a seat that checked in. That covers two cases:

- the IP the check-in has now (the check-in refresh follows the MAC to a new lease),
- any IP on a checked-in seat's cabled port, from the last MAC table read (port_clients.py), so a
  PC that changed its MAC still counts: the seat port is the key, not the machine.

Nothing is ever blocked. "Not done" only makes phones and laptops show a quiet "sign in to
network" note.
"""
from integrations import checkin, config


def answer(app):
    """``{"done": [ip, ...], "portal_url": str}`` for the agent."""
    rows = checkin.load_all()
    done = {row['ip'] for row in rows.values() if row.get('ip')}
    finder = app.extensions.get('floorbit_port_clients')
    if finder is not None:
        finder.request()      # at most every two minutes, in the background
        checked_in = {str(seat).upper() for seat in rows}
        done.update(ip for ip, seat in dict(finder.seat_ips).items() if seat in checked_in)
    public = str(config.get('PUBLIC_URL', '') or '').rstrip('/')
    return {'done': sorted(done), 'portal_url': f'{public}/checkin' if public else ''}
