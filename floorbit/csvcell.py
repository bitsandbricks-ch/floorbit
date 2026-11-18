"""One CSV cell that a spreadsheet won't run: the cable list, the timeline and other exports."""

# Tab and carriage return too: some spreadsheets drop them and then read what follows as a formula.
FORMULA_START = ('=', '+', '-', '@', '\t', '\r')


def cell(value):
    text = str(value)
    if text[:1] in FORMULA_START:
        text = "'" + text   # never a formula in a spreadsheet
    if any(c in text for c in ',"\n\r'):
        # A quote inside is doubled: else a name like  x",=HYPERLINK(...)  ended the cell early and
        # its rest became a cell of its own, a formula after all.
        return '"' + text.replace('"', '""') + '"'
    return text
