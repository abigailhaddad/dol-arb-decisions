import re

MONTH_SLUG = re.compile(r"^(\d{2})_?(\d{2}|\d{4})$")


def slug_month(slug):
    """'09_2026' -> '2026-09'; '0399' -> '1999-03'."""
    m = MONTH_SLUG.match(slug)
    mm, yy = m.group(1), m.group(2)
    if len(yy) == 2:
        yy = ("19" if int(yy) > 50 else "20") + yy
    return f"{yy}-{mm}"
