"""Download file names from names people typed: always a header a WSGI server can send."""
from floorbit.downloads import disposition


def test_a_plain_name_stays_as_it_is():
    assert disposition("floorbit-template-main-20261118.json") == \
        'attachment; filename="floorbit-template-main-20261118.json"'


def test_other_names_get_an_ascii_fallback_and_the_real_name():
    for name in ("東京-hall.json", "Zürich.json", 'a"b\\c.cfg', "x\r\ny.cfg"):
        header = disposition(name)
        header.encode("latin-1")                  # gunicorn refuses the response otherwise
        assert "\r" not in header and "\n" not in header
        assert header.count('"') == 2 and "filename*=UTF-8''" in header
    assert disposition("東京.json", "inline") == \
        "inline; filename=\"__.json\"; filename*=UTF-8''%E6%9D%B1%E4%BA%AC.json"
