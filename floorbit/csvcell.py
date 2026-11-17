"""One CSV cell that a spreadsheet won't run: the cable list, the timeline and other exports."""


def cell(value):
    text = str(value)
    if text[:1] in ('=', '+', '-', '@'):
        text = "'" + text   # never a formula in a spreadsheet
    return f'"{text}"' if any(c in text for c in ',"\n') else text
