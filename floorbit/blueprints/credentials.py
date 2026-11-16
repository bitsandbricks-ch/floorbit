"""Stored switch logins (issue #474). Rules in floorbit/credentials.py, docs in docs/credentials.md.

- ``GET /settings/credentials``: the page (React), admins only.
- ``GET /api/settings/credentials``: what is set: scope and username, never a password.
- ``PUT /api/settings/credentials/ssh``: set or replace ``{"scope", "username", "password"}``.
- ``DELETE /api/settings/credentials/<id>``.

All of ``/api/settings`` needs ``settings.manage`` (auth/roles.py); every change is audit-logged.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, credentials, spa, vault

bp = Blueprint('credentials', __name__)


@bp.route('/settings/credentials')
def credentials_page():
    return spa.render('Switch logins')


@bp.route('/api/settings/credentials', methods=['GET'])
def list_credentials():
    return jsonify({'credentials': credentials.listing()})


@bp.route('/api/settings/credentials/ssh', methods=['PUT'])
def set_ssh():
    try:
        entry = credentials.set_ssh(request.get_json(silent=True) or {}, g.get('audit_user'))
    except credentials.CredentialError as exc:
        return jsonify({'error': str(exc)}), exc.status
    except vault.VaultError as exc:
        return jsonify({'error': str(exc)}), 500
    audit.record('credentials', f"Set the switch login for {entry['scope']}", g.get('audit_user'), entry['username'])
    return jsonify(entry)


@bp.route('/api/settings/credentials/<cred_id>', methods=['DELETE'])
def delete_credential(cred_id):
    gone = credentials.delete(cred_id)
    if gone is None:
        return jsonify({'error': 'No such login.'}), 404
    audit.record('credentials', f"Removed the switch login for {gone['scope']}", g.get('audit_user'),
                 gone['username'])
    return jsonify({'ok': True})
