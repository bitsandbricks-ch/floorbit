"""The ``Content-Disposition`` of a download whose file name comes from a name people typed.

A response header must be Latin-1: gunicorn answers 500 for a template called "東京" or a switch
whose NetBox name has a character outside it. RFC 6266 gives the plain ``filename`` as an ASCII
fallback and the real name in ``filename*``, which every current browser prefers.
"""
from urllib.parse import quote


def disposition(name, kind='attachment'):
    plain = ''.join(c if 32 <= ord(c) < 127 and c not in '"\\' else '_' for c in name)
    header = f'{kind}; filename="{plain}"'
    if plain != name:
        header += "; filename*=UTF-8''" + quote(name, safe='')
    return header
