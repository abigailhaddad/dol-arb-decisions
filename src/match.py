"""Match the by-date listing's document links to rows built from the by-name listing.

Each link is matched in this order:
  1. same file
  2. a twin file: the HTML copy of a PDF (or back), or the same file with or without _SLIP_OP/_REDACTED,
     including the same ARB-numbered file under another collection folder (03_017.HTM and 03_017.SCAP.PDF)
  3. same decision date and a shared ARB number (from the text around the link)
  4. same decision date and a shared ALJ number (old pages cite only the ALJ number)
"""
import os, re, sys
from collections import Counter, defaultdict
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import arb
from crawl import month_pages
from months import slug_month


def head(block):
    """The citation part of a by-date entry, without its summary."""
    return re.split(r"\s(?:Summary|Casenote\(s\))\s?:", block)[0]


def date_entries(raw="raw"):
    out = []
    for slug in month_pages(open(f"{raw}/ARBINDEX.html").read()):
        for e in arb.parse_month_page(open(f"{raw}/month/{slug}.html").read()):
            h = head(e["block"])
            d, _, _ = arb.parse_date(h)
            out.append({**e, "key": arb.doc_key(e["url"]), "month": slug_month(slug), "page": slug, "date": d,
                        "arb": arb.caption_arb_numbers(h),
                        "alj": {m.upper() for m in ("-".join(x) for x in arb.ALJ_NO.findall(h))}})
    return out


def norm_alj(a):
    """1997-STA-23 and 97-STA-23 -> (97, 'STA', 23)."""
    y, p, n = a.split("-")[:3]
    return (int(y) % 100, p.upper(), int(n.split("-")[0]))


def indexes(df):
    by_key, by_arb, by_alj, by_family = {}, defaultdict(set), defaultdict(set), defaultdict(set)
    for i, r in df.iterrows():
        for u in [r["url"]] + (r["other_urls"].split() if isinstance(r["other_urls"], str) else []):
            if isinstance(u, str):
                by_key[arb.doc_key(u)] = i
                if arb.family_key(u):
                    by_family[arb.family_key(u)].add(i)
        date = str(r["decision_date"]) if pd.notna(r["decision_date"]) else None
        for n in arb.caption_arb_numbers(r["caption"]) | arb.caption_arb_numbers(r["listing_line"]):
            by_arb[(n, date)].add(i)
        for a in (r["alj_numbers"] or "").split("; ") if isinstance(r["alj_numbers"], str) else []:
            by_alj[(norm_alj(a), date)].add(i)
    return by_key, by_arb, by_alj, by_family


def match_one(e, by_key, by_arb, by_alj, by_family):
    """(level, set of row indexes) or (None, empty set)."""
    if e["key"] in by_key:
        return "1 same file", {by_key[e["key"]]}
    tw = {by_key[k] for k in arb.twin_keys(e["key"]) if k in by_key}
    if tw:
        return "2 twin file", tw
    fam = by_family.get(arb.family_key(e["url"]), set())
    if len(fam) == 1:
        return "2 twin file", fam
    if not e["date"]:
        return None, set()
    hits = set().union(*[by_arb.get((n, e["date"]), set()) for n in e["arb"]])
    if hits:
        return "3 ARB number + date", hits
    for a in e["alj"]:
        try:
            hits |= by_alj.get((norm_alj(a), e["date"]), set())
        except ValueError:
            pass
    if hits:
        return "4 ALJ number + date", hits
    return None, set()


def compare(df, entries):
    """Counts by match level, matched row indexes, unmatched entries, and row index -> months linked."""
    idx = indexes(df)
    how, matched, unmatched, row_months = Counter(), set(), [], defaultdict(set)
    for e in entries:
        if "/arb_decisions/" not in e["key"]:
            unmatched.append(e)  # an ALJ or court decision cited in a summary, not an ARB decision
            continue
        level, rows = match_one(e, *idx)
        if level is None:
            unmatched.append(e)
            continue
        how[level] += 1
        matched |= rows
        e["matched"] = True
        for i in rows:
            row_months[i].add(e["month"])
    return how, matched, unmatched, row_months


def row_numbers(df):
    """(index, date or None, ARB numbers, ALJ numbers) per row, for near_miss."""
    out = []
    for i, r in df.iterrows():
        nums = arb.caption_arb_numbers(r["caption"]) | arb.caption_arb_numbers(r["listing_line"])
        aljs = {norm_alj(a) for a in r["alj_numbers"].split("; ")} if isinstance(r["alj_numbers"], str) else set()
        out.append((i, pd.Timestamp(r["decision_date"]) if pd.notna(r["decision_date"]) else None, nums, aljs))
    return out


def entry_sig(e):
    """One by-date entry's citation, for pairing its PDF and HTML links: page, date and ARB numbers."""
    return (e["page"], e["date"], frozenset(e["arb"])) if e["date"] and e["arb"] else None


def near_miss(e, rows, days=7):
    """Rows sharing an ARB or ALJ number with the entry, dated within `days` of it or undated (a date typo in one
    listing). `rows` comes from row_numbers()."""
    if not e["date"]:
        return []
    d0 = pd.Timestamp(e["date"])
    e_alj = set()
    for a in e["alj"]:
        try:
            e_alj.add(norm_alj(a))
        except ValueError:
            pass
    # a row with no readable date can't be ruled out by date, so it counts if the numbers match
    return [i for i, d, nums, aljs in rows
            if (d is None or abs((d - d0).days) <= days) and (nums & e["arb"] or aljs & e_alj)]


def entry_row(e):
    """A table row from a by-date entry, for decisions the by-name listing doesn't have."""
    h = head(e["block"]).split(" | ")[-1] if " | " in head(e["block"]) and arb.parse_date(head(e["block"]).split(" | ")[-1])[0] else head(e["block"])
    d, issuer, raw = arb.parse_date(h)
    before = h[:h.find(raw)] if raw else h
    after = h[h.find(raw) + len(raw):] if raw else ""
    case = re.split(r"\s*,?\s*\b(?:ARB|ALJ)\s+(?:Case\s+)?Nos?\.", before)[0].strip(" ,") or None
    paren = re.findall(r"\(([^()]+)\)", after)
    paren = [p for p in paren if not re.search(r"per curiam|slip op|reporter|^\s*pdf|^\s*html?", p, re.I)]
    title = paren[0].strip() if paren else (re.split(r"\bPDF\b|\bHTML?\b|\|", after.lstrip(") |"))[0].strip() or None)
    alj = sorted(e["alj"])
    return {"decision_date": d, "issued_by": issuer, "decision_title": title, "case_name": case,
            "arb_numbers": "; ".join(dict.fromkeys(m.group(0) for m in arb.ARB_NO.finditer(before.split("ALJ")[0]))) or None,
            "alj_numbers": "; ".join(alj) or None, "listing_line": h[:500], "caption": None}
