"""One local agent's recent events, for the Logs tab and the overview of its page (issue #905).
For admins (``settings.manage``, as all of ``/api/agents``):

- ``GET /api/agents/<id>/events?limit=50``: ``{"events": [{at, user, area, action, ok}]}``, newest
  first: what the audit log holds about this agent (enrolled, keys, certificates, settings, its
  plugins' and its own updates). The action is in the page's language; 404 for an unknown agent.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from .. import agent_link, audit, i18n

bp = Blueprint('agent_events', __name__)

AREAS = ('agents', 'settings')
MAX = 200
SCAN = 5000      # newest audit entries looked through: an agent's page needs the recent ones only


def about(entry, agent):
    """Is this audit entry about ``agent``? Admins' changes name it as the target; what the agent
    reports itself starts with its name ("Hall 1: kept plugin lancache 1.2.0")."""
    if entry.get('area') not in AREAS:
        return False
    names = {agent['id'], agent.get('name') or agent['id']}
    if entry.get('target') in names:
        return True
    action = str(entry.get('action') or '')
    return any(action.startswith(f'{n}: ') for n in names)


def _at(entry):
    try:
        return datetime.strptime(entry.get('time') or '', '%Y-%m-%dT%H:%M:%S%z').timestamp()
    except ValueError:
        return None


@bp.route('/api/agents/<agent_id>/events', methods=['GET'])
def events(agent_id):
    agent = next((a for a in agent_link.all_agents() if a['id'] == agent_id), None)
    if agent is None:
        return jsonify({'error': 'No such agent.'}), 404
    try:
        limit = min(max(int(request.args.get('limit', 50)), 1), MAX)
    except ValueError:
        limit = 50
    lang = i18n.language(request.headers.get('Accept-Language'))
    rows, _ = audit.read(limit=SCAN)
    found = [e for e in rows if about(e, agent)][:limit]
    return jsonify({'events': [{'at': _at(e), 'user': e.get('user'), 'area': e.get('area'),
                                'action': i18n.log_text(e.get('action'), lang), 'ok': e.get('ok', True)}
                               for e in found]})
