"""CSV exports (cables, timeline): a cell can't end early or become a formula."""
import csv
import io

import pytest

from floorbit.csvcell import cell

NAMES = [
    'sw-a-01",=HYPERLINK("http://example.com/x")',
    '=1+1', '+1', '-1', '@SUM(A1)', '\t=1', '\r=1',
    'a,b', 'two\nlines', 'cr\rhere', 'say "hi"', 'plain', '',
]


@pytest.mark.parametrize("name", NAMES)
def test_a_cell_reads_back_as_one_cell_and_never_as_a_formula(name):
    line = ",".join(cell(v) for v in ("2026-11-18", name, "who"))
    row = next(csv.reader(io.StringIO(line, newline="")))
    assert len(row) == 3 and row[0] == "2026-11-18" and row[2] == "who"
    assert row[1].lstrip("'") == name
    assert row[1][:1] not in ("=", "+", "-", "@", "\t", "\r")


def test_the_timeline_export_keeps_its_columns():
    from floorbit import timeline
    rows = [{"t": 1_700_000_000, "kind": "switch", "title": NAMES[0], "target": "a,b", "who": 'Mike "M"'}]
    out = list(csv.reader(io.StringIO(timeline.csv_text(rows))))
    assert out[0] == ["time", "kind", "title", "target", "who"]
    assert len(out[1]) == 5 and out[1][2] == NAMES[0] and out[1][4] == 'Mike "M"'
