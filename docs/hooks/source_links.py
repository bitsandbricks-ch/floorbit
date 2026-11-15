"""MkDocs hook: links from a doc to the code (``../floorbit/x.py``) point at GitHub on the site.

In the repository those relative links work as they are; on the site there is no code next to the
pages, so they would break.
"""
import re

REPO = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/'
LINK = re.compile(r'\]\(\.\./([^)\s]+)\)')


def on_page_markdown(markdown, **_):
    return LINK.sub(lambda m: f']({REPO}{m.group(1)})', markdown)
