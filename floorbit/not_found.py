"""A mistyped or turned-off address answers 404 in Floorbit's own look, not Flask's bare page.

The API keeps answering JSON. Pages get the React app with ``page={'kind': 'not-found'}``, so it
draws its 404 (frontend/src/pages/NotFound.tsx) even where the path is a known page, as for a
feature an admin turned off (floorbit/features.py).
"""
from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from . import spa

# Werkzeug's own texts are long and English only; an abort() without a description says this.
SHORT = {400: 'The request is not valid.', 401: 'Sign in required', 403: 'Not allowed.',
         405: 'This address does not take that method.', 409: 'That can\'t be done right now.',
         413: 'The request is too large.', 429: 'Too many requests. Wait a moment and try again.'}

# Files: a missing script or image gets the short answer, not a whole page.
_FILES = ('/static/', '/assets/', '/favicon', '/robots.txt')


def init_not_found(app):
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/api/') or request.path.startswith(_FILES) or request.method != 'GET':
            return jsonify({'error': 'Not found'}), 404
        if request.accept_mimetypes.best_match(['text/html', 'application/json']) == 'application/json':
            return jsonify({'error': 'Not found'}), 404
        html, _status = spa.render('Not found', page={'kind': 'not-found'})
        return html, 404

    @app.errorhandler(HTTPException)
    def api_error(error):
        """The API answers every refusal as ``{"error": ...}``, as the pages read it (api/client.ts):
        an ``abort(403, description=...)`` gave an HTML page, and the page could only say "HTTP 403"."""
        if not request.path.startswith('/api/') or error.code is None or error.code < 400:
            return error
        own = error.description != type(error).description
        text = error.description if own and error.description else SHORT.get(error.code, error.name)
        response = jsonify({'error': text})
        response.status_code = error.code
        kept = dict(error.get_headers())
        for header in ('Retry-After', 'Allow', 'WWW-Authenticate'):
            if header in kept:
                response.headers[header] = kept[header]
        return response

