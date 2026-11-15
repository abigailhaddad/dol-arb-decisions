"""Parse the ARB's two decision listings.

By name (ARBLIST_A-H, _I-P, _Q-Z): a caption paragraph (ARB and ALJ numbers, parties, the indexed name in bold),
then one list item per decision: title, (issuer and date), link. This is the table's source.

By date (one page per month, 1998 on): used only as a second listing to check the first against.
"""
import re
from datetime import date
from bs4 import BeautifulSoup

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12}
# "(ARB June 24, 2015)", "(Sec'y May 1, 1996)", "(Nov. 12, 2024)", "(ARB Sept. 29, 2026)", "(PWBA July 26, 1995)".
# Also the typos the listing has: "(ARB Jan.22, 2025)", "(ARB Nov, 16, 2020)", "(ARB May 30,2008)", "(ARB ;Apr. 20",
# "(ARB No. Oct. 10, 1997)", and "ARB July 26, 2011)" with no opening parenthesis.
MON = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE = re.compile(r"(?:\(\s*(?P<issuer>ARB|Sec'y|Sec’y|OAA|PWBA|Deputy Sec'y|Deputy Sec’y)?|\b(?P<issuer2>ARB))\s*(?:No\.)?\s*;?\s*"
                  r"(?P<mon>" + MON + r")\.?,?\s*(?P<day>\d{1,2}),?\s*(?P<year>\d{4})\b")
ALJ_NO = re.compile(r"\b(\d{2,4})-([A-Z]{2,5})-(\d{1,5}(?:-P)?)\b")
ARB_NO = re.compile(r"\b(\d{4}-\d{4}|\d{2}-\d{3})[A-Z]?\b")
DOC = re.compile(r"\.(pdf|htm|html)$", re.I)
CAPTION = re.compile(r"\b(ARB|ALJ|OAA|Sec'y)\s+(Case\s+)?Nos?\b\.?", re.I)


def absolute(href):
    h = href.strip().split("#")[0].split("?")[0]
    if h.startswith("/"):
        return "https://www.dol.gov" + h
    return re.sub(r"^https?://dol\.gov/", "https://www.dol.gov/", h)


def doc_key(url):
    """Match key for a document link across listings: the path from /PUBLIC/ on, lowercased.
    The two hosts (www.oalj.dol.gov and www.dol.gov/sites/dolgov/files/OALJ) are not interchangeable for
    fetching, but the path after PUBLIC/ names the same file."""
    u = absolute(url).lower()
    i = u.find("/public/")
    return u[i:] if i >= 0 else u


def program_from_url(url):
    """The case-type folder in the link, e.g. .../ARB_DECISIONS/ERA/2024-0049-ERAP.pdf -> ERA."""
    m = re.search(r"/(?:ARB_DECISIONS|DECISIONS)/([A-Z0-9_]+)/[^/]+$", absolute(url), re.I)
    return m.group(1).upper() if m else None


def file_arb_number(url):
    """ARB number in a file name as (two-digit year, sequence): 2024-0049-ERAP.pdf, 16_0085.FRSP_SLIP_OP.PDF and
    09_076.SOXP.PDF give (24, 49), (16, 85), (9, 76). None for names like 1996ERA10P.PDF."""
    if not url:
        return None
    b = url.rsplit("/", 1)[-1]
    m = re.match(r"(\d{4})-(\d{4})", b) or re.match(r"(\d{2})_(\d{4})(?!\d)", b) or re.match(r"(\d{2})_(\d{3})(?!\d)", b)
    return (int(m.group(1)) % 100, int(m.group(2))) if m else None


def caption_arb_numbers(text):
    """Every ARB number in a text as (two-digit year, sequence), expanding "15-032, -033" style lists."""
    out, last = set(), None
    text = text if isinstance(text, str) else ""
    for m in re.finditer(r"(?<![\d-])(\d{4}|\d{2})-(\d{3,4})(?!\d)|(?<=[,\s])-(\d{2,4})(?!\d)", text or ""):
        if m.group(1):
            last = m.group(1)
            out.add((int(last) % 100, int(m.group(2))))
        elif last:
            out.add((int(last) % 100, int(m.group(3))))
    return out


def parse_date(text):
    """First date in parentheses. Returns (iso or None, issuer or None, raw match or None)."""
    m = DATE.search(text)
    if not m:
        return None, None, None
    mon = MONTHS.get(m.group("mon")[:3].lower())
    try:
        d = date(int(m.group("year")), mon, int(m.group("day"))).isoformat() if mon else None
    except ValueError:
        d = None
    issuer = (m.group("issuer") or m.group("issuer2") or "").replace("’", "'") or None
    return d, issuer, m.group(0)


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def blocks(article):
    """Innermost <p> and <li> elements in document order (a block holding other blocks is skipped)."""
    for el in article.find_all(["p", "li"]):
        if el.find(["p", "li"]) is None:
            yield el


def doc_links(el):
    return [absolute(a["href"]) for a in el.find_all("a", href=True) if DOC.search(absolute(a["href"]))]


def parse_caption(el, text=None):
    text = text or clean(el.get_text(" "))
    strong = clean(" ".join(s.get_text(" ") for s in el.find_all(["strong", "b"])))
    head = text.split(" v. ")[0] if " v. " in text else text
    arb = sorted(set(ARB_NO.findall(head.split("ALJ")[0]))) if re.search(r"\bARB\b", head) else []
    alj = ["-".join(m) for m in ALJ_NO.findall(text)]
    parties = strip_dockets(text)
    d, _, raw = parse_date(parties or "")
    if raw:  # "Dierkes v. West Linn-Wilsonville School District (ARB June 30, 2003) (Final Decision & Order)"
        parties = parties[:parties.find(raw)].strip(" ,") or parties
    return {"caption": text, "indexed_name": strong or None, "arb_numbers": "; ".join(arb) or None,
            "alj_numbers": "; ".join(dict.fromkeys(alj)) or None, "parties": parties or None}


LEAD = re.compile(r"^(?:(?:ARB|ALJ|OAA|Sec'y)\s+(?:Case\s+)?Nos?\.?|[\d]{2,4}-[A-Z]{2,5}-\d+[A-Z]?|\d{4}-\d{4}[A-Z]?"
                  r"|\d{2}-\d{3}[A-Z]?|-\d{2,4}|-P\b|\d{1,4}\b(?![A-Za-z&])|and\b|&(?=\s*\d)|through\b|thru\b|to\b(?=\s*\d)|\(formerly[^)]*\)|[,;:])\s*", re.I)


def strip_dockets(text):
    """The caption without its leading run of ARB/ALJ numbers."""
    t = text
    while True:
        m = LEAD.match(t)
        if not m or not m.group(0):
            return t.strip() or None
        t = t[m.end():]


def is_caption(el, text):
    if CAPTION.search(text[:40]):
        return True
    return bool(el.find(["strong", "b"])) and parse_date(text)[0] is None and len(text) < 400


TITLE_START = re.compile(r"\b(Final|Decision|Order|Errat|Amended|Notice|Remand|Approval|Corrected|Supplemental|Ruling|"
                         r"Reissued|Dismissal|Denial|Judgment)")


def split_inline_caption(el, text):
    """The caption part of a block that holds caption and decision line, or None if no split is found."""
    br = el.find("br")
    if br is not None:
        parts = [clean(t) for t in el.decode_contents().split("<br/>")]
        head = clean(BeautifulSoup(parts[0], "lxml").get_text(" ")) if len(parts) > 1 else ""
        if head and not parse_date(head)[0]:
            return head
    # otherwise the title starts after the bold indexed name and its party text
    strong = el.find(["strong", "b"])
    start = text.find(clean(strong.get_text(" "))) + len(clean(strong.get_text(" "))) if strong else 0
    m = TITLE_START.search(text, start)
    return clean(text[:m.start()]) if m else None


def parse_name_page(html, page):
    """Rows (one per decision line) and a list of skipped blocks with their text."""
    art = BeautifulSoup(html, "lxml").find("article")
    rows, skipped, cap = [], [], None
    for el in blocks(art):
        text = clean(el.get_text(" "))
        if not text:
            continue
        links = doc_links(el)
        d, issuer, raw = parse_date(text)
        if not links and is_caption(el, text) and not (el.name == "li" and raw):
            cap = parse_caption(el)
            continue
        if links or (raw and el.name == "li"):
            if CAPTION.match(text):
                # caption and decision in one block: "ARB No. 12-075, ALJ No. 2012-AIR-10 Barrett v. Shuttle
                # America<br>Final Decision and Order (ARB Feb. 28, 2014) PDF"
                cap_text = split_inline_caption(el, text)
                if cap_text:
                    cap = parse_caption(el, cap_text)
            title = clean(text[:text.find(raw)]) if raw else clean(re.sub(r"\bPDF\b|\bHTML?\b", "", text))
            if cap and title and title.startswith(cap["caption"]):
                title = clean(title[len(cap["caption"]):]) or None  # the line repeats the caption
            if not raw and not title and cap:
                # the line is just a link; the caption carries "(ARB June 30, 2003) (Final Decision & Order)"
                d, issuer, raw = parse_date(cap["caption"])
                after = cap["caption"][cap["caption"].find(raw) + len(raw):] if raw else ""
                m = re.search(r"\(([^()]+)\)", after)
                title = title or (clean(m.group(1)) if m else None)
            rows.append({**(cap or {"caption": None, "indexed_name": None, "arb_numbers": None,
                                    "alj_numbers": None, "parties": None}),
                         "decision_title": title or None, "decision_date": d, "issued_by": issuer,
                         "listing_line": text, "doc_urls": links, "listing_page": page})
            continue
        skipped.append(text)
    return rows, skipped


def parse_month_page(html):
    """Every document link on a by-date page (1998-99 pages put the citation in <dt> and the link in <dd>), summaries included, with the text of the block around it.
    Returns [{"url", "block"}], one per distinct url (the first block it appears in)."""
    art = BeautifulSoup(html, "lxml").find("article")
    out, seen = [], set()
    for a in art.find_all("a", href=True):
        u = absolute(a["href"])
        if not DOC.search(u) or u in seen:
            continue
        seen.add(u)
        blk = a.find_parent(["li", "p", "dd", "dt", "h2", "h3", "h4", "td", "blockquote", "div"])
        text = clean(blk.get_text(" ")) if blk else ""
        if len(text) > 800:
            # the enclosing block holds several entries: use only the text just before the link
            got = []
            for st in a.find_all_previous(string=True, limit=60):
                got.insert(0, str(st))
                t = clean(" ".join(got))
                cap = CAPTION.search(t)
                has_name = cap and re.search(r"[A-Za-z]{3}", t[:cap.start()])
                if parse_date(t)[0] and has_name or len(t) > 600:
                    break
            text = clean(" ".join(got)) + " " + clean(a.get_text(" "))
        if parse_date(text)[0] is None:
            # a bare "PDF (slip opinion)" line: the citation is in a block just above it
            for prev in a.find_all_previous(["li", "p", "dt", "h2", "h3", "h4"], limit=6):
                t = clean(prev.get_text(" "))
                if parse_date(t)[0]:
                    text = t + " | " + text
                    break
        if not (ALJ_NO.search(text) or ARB_NO.search(text)):
            # 1996-97 pages put the case caption (with its ALJ number) in a block above the decision lines
            for prev in a.find_all_previous(["li", "p", "dt", "h2", "h3", "h4"], limit=12):
                t = clean(prev.get_text(" "))
                if ALJ_NO.search(t) or CAPTION.search(t):
                    text = t + " | " + text
                    break
        out.append({"url": u, "block": text})
    return out


def family_key(url):
    """(case-type folder, file stem) with the format, program suffix and slip/redacted tags removed, so that
    .../DBA_SCA/DECISIONS/ARB_DECISIONS/SCA/03_017.HTM and .../ARB/DECISIONS/ARB_DECISIONS/SCA/03_017.SCAP.PDF
    give the same key. None when the file name doesn't follow the ARB-number pattern."""
    prog = program_from_url(url)
    b = absolute(url).rsplit("/", 1)[-1].lower()
    m = re.match(r"^(\d{2}_\d{3,4}[a-z]?|\d{4}-\d{4}[a-z]?)(?=[._-]|$)", b)
    return (prog, m.group(1).replace("-", "_")) if prog and m else None


def twin_keys(key):
    """Other names the same decision's file goes by: the PDF for an HTML copy and back, and the file without
    a _SLIP_OP or _REDACTED suffix."""
    stem, ext = key.rsplit(".", 1) if "." in key.rsplit("/", 1)[-1] else (key, "")
    stems = {stem, re.sub(r"[._]?(slip_op|slip|redacted)$", "", stem), re.sub(r"_$", "", stem)}
    for st in list(stems):
        stems |= {st + "_slip_op", st + ".slip_op", st + "_redacted"}
    return {f"{st}.{e}" for st in stems for e in ("pdf", "htm", "html")} - {key}
