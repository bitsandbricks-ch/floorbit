"""A mistyped or turned-off address answers 404 in Floorbit's own look, not Flask's bare page.

The API keeps answering JSON. Pages get the React app with ``page={'kind': 'not-found'}``, so it
draws its 404 (frontend/src/pages/NotFound.tsx) even where the path is a known page, as for a
feature an admin turned off (floorbit/features.py).
"""
from flask import jsonify, request

from . import spa

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
