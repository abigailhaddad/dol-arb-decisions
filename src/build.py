"""raw/ -> out/decisions.parquet and out/report.json

    python src/build.py

One row per decision line on the by-name listing. A decision listed under two names (both parties, say)
with the same links and date is one row; `indexed_names` keeps both. The by-date pages are read only to
mark which rows they also list (`in_date_listing`, `date_listing_months`) and to count what they have that
the by-name listing doesn't (see src/check.py).
"""
import json, os, re, sys
from collections import defaultdict
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import arb, match
from crawl import NAME_PAGES

def name_rows(raw="raw"):
    rows, skipped = [], []
    for p in NAME_PAGES:
        r, s = arb.parse_name_page(open(f"{raw}/{p}.html").read(), p)
        rows += r
        skipped += [{"page": p, "text": t} for t in s]
    return rows, skipped


def dedupe(rows):
    """Collapse lines that list the same decision twice: same set of links and same date."""
    out, seen = [], {}
    for r in rows:
        sig = (tuple(sorted(arb.doc_key(u) for u in r["doc_urls"])), r["decision_date"]) if r["doc_urls"] else \
              ("nolink", r["arb_numbers"], r["alj_numbers"], r["decision_date"], r["decision_title"])
        if sig in seen:
            first = out[seen[sig]]
            if r["indexed_name"] and r["indexed_name"] not in first["indexed_names"]:
                first["indexed_names"].append(r["indexed_name"])
            first["times_listed"] += 1
            continue
        seen[sig] = len(out)
        out.append({**r, "indexed_names": [r["indexed_name"]] if r["indexed_name"] else [], "times_listed": 1})
    return out


def decision_id(r, n):
    if r["doc_urls"]:
        k = arb.doc_key(r["doc_urls"][0])
        return re.sub(r"^/public/(arb/)?decisions/arb_decisions/|^/public/", "", k).upper()
    return f"UNLINKED-{n:03d}"


def build(raw="raw"):
    rows, skipped = name_rows(raw)
    deduped = dedupe(rows)
    out, n_unlinked = [], 0
    for r in deduped:
        if not r["doc_urls"]:
            n_unlinked += 1
        fnum = arb.file_arb_number(r["doc_urls"][0]) if r["doc_urls"] else None
        prog = arb.program_from_url(r["doc_urls"][0]) if r["doc_urls"] else None
        alj_prog = sorted({a.split("-")[1].upper() for a in (r["alj_numbers"] or "").split("; ") if a})
        out.append({
            "decision_id": decision_id(r, n_unlinked),
            "decision_date": r["decision_date"],
            "issued_by": r["issued_by"],
            "decision_title": r["decision_title"],
            "case_name": r["parties"],
            "indexed_names": "; ".join(r["indexed_names"]) or None,
            "arb_numbers": r["arb_numbers"],
            "alj_numbers": r["alj_numbers"],
            "program": prog or (alj_prog[0] if len(alj_prog) == 1 else None),
            "program_source": "link folder" if prog else ("ALJ number" if len(alj_prog) == 1 else None),
            "file_number_in_caption": None if not fnum else bool(
                fnum in arb.caption_arb_numbers(r["caption"]) | arb.caption_arb_numbers(r["listing_line"])),
            "url": r["doc_urls"][0] if r["doc_urls"] else None,
            "other_urls": " ".join(r["doc_urls"][1:]) or None,
            "listing_line": r["listing_line"],
            "caption": r["caption"],
            "listing_page": r["listing_page"],
            "times_listed": r["times_listed"],
        })
    df = pd.DataFrame(out)
    # A few links are attached to two decision lines with different dates (the listing reuses a file).
    # Those rows keep the link and get the date added to the id.
    dup = df["decision_id"].duplicated(keep=False)
    df.loc[dup, "decision_id"] = df.loc[dup, "decision_id"] + "@" + df.loc[dup, "decision_date"].astype(str)
    report = {"name_listing_lines": len(rows), "name_listing_decisions": len(df),
              "collapsed_duplicate_lines": len(rows) - len(df), "unlinked_decisions": n_unlinked,
              "rows_sharing_a_link": df.loc[dup, ["decision_id", "listing_line"]].to_dict("records"),
              "skipped_blocks": skipped}
    df, extra = add_date_listing(df, raw)
    report.update(extra)
    df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date
    report["decisions"] = len(df)
    return df, report


def add_date_listing(df, raw):
    """Mark rows the by-date listing also has, and add the ARB decisions only it has.

    An unmatched by-date link becomes a row when it is a file in an ARB decisions folder, its entry has a date,
    and no row shares its ARB or ALJ number within 7 days (those are date typos in one listing, reported).
    The PDF and HTML links of one entry become one row."""
    entries = match.date_entries(raw)
    how, matched, unmatched, row_months = match.compare(df, entries)
    df["listed_on"] = "both"
    df.loc[~df.index.isin(matched), "listed_on"] = "by-name, unmatched"
    df["date_listing_months"] = [("; ".join(sorted(row_months[i])) or None) for i in df.index]
    added, near, other, used_links = {}, [], [], []
    rows_nums = match.row_numbers(df)
    matched_sigs = {match.entry_sig(e) for e in entries if e.get("matched")} - {None}
    same_entry = []
    for e in unmatched:
        if "/arb_decisions/" not in e["key"] or not e["date"]:
            other.append(e)
            continue
        if match.entry_sig(e) in matched_sigs:
            same_entry.append(e["url"])  # the PDF (or HTML) link of the same by-date entry matched a row
            continue
        nm = match.near_miss(e, rows_nums)
        if nm:
            near.append({"url": e["url"], "date_listing_date": e["date"], "page": e["page"],
                         "rows": [(df.loc[i, "decision_id"], str(df.loc[i, "decision_date"])) for i in nm]})
            continue
        r = match.entry_row(e)
        sig = (r["decision_date"], r["arb_numbers"], r["case_name"], r["decision_title"])  # PDF and HTML lines
        used_links.append(e["url"])
        if sig in added:
            added[sig]["other_urls"] = " ".join(filter(None, [added[sig]["other_urls"], e["url"]]))
            continue
        prog = arb.program_from_url(e["url"])
        fnum = arb.file_arb_number(e["url"])
        added[sig] = {**r, "decision_id": re.sub(r"^/public/[a-z_]+/decisions/arb_decisions/", "", e["key"]).upper(),
                      "indexed_names": None, "program": prog, "program_source": "link folder",
                      "file_number_in_caption": None if not fnum else fnum in arb.caption_arb_numbers(r["listing_line"]),
                      "url": e["url"], "other_urls": None, "listing_page": e["page"], "times_listed": 1,
                      "listed_on": "by-date only", "date_listing_months": e["month"]}
    df = pd.concat([df, pd.DataFrame(list(added.values()))], ignore_index=True)
    extra = {"date_listing_links": len(entries), "date_listing_links_matched": dict(sorted(how.items())),
             "date_listing_links_unmatched": len(unmatched), "rows_added_from_date_listing": len(added),
             "date_listing_links_in_added_rows": len(used_links),
             "date_listing_date_disagreements": near,
             "date_listing_links_whose_other_format_matched": same_entry,
             "unmatched_links_not_added": [{k: e[k] for k in ("url", "page", "date")} | {"text": e["block"][:200]}
                                           for e in other]}
    return df, extra


TEXT_COLS = ["decision_id", "url", "text_status", "pages", "text_chars", "text"]


def write(df, out="out"):
    """decisions.parquet (no text) and decision_text.parquet (decision_id, url, text and its status)."""
    os.makedirs(out, exist_ok=True)
    if "text" in df:
        df[TEXT_COLS].to_parquet(f"{out}/decision_text.parquet", index=False)
        df = df.drop(columns=["text"])
    df.to_parquet(f"{out}/decisions.parquet", index=False)


def attach_text_cache(df, path="raw/text.jsonl"):
    """Text columns from src/text.py's cache, by url. Rows whose url isn't cached get text_status "not fetched"."""
    recs = {}
    for line in open(path):
        r = json.loads(line)
        recs[r["url"]] = r
    def get(u, k):
        return recs[u][k] if isinstance(u, str) and u in recs else None
    df["text"] = [get(u, "text") for u in df["url"]]
    df["text_chars"] = [len(t) if isinstance(t, str) else 0 for t in df["text"]]
    df["pages"] = pd.array([get(u, "pages") for u in df["url"]], dtype="Int64")
    df["text_status"] = [get(u, "text_status") or ("no document link" if not isinstance(u, str) else "not fetched")
                         for u in df["url"]]
    return df


if __name__ == "__main__":
    df, report = build()
    if os.path.exists("raw/text.jsonl"):
        df = attach_text_cache(df)
    assert df["decision_id"].is_unique, df[df["decision_id"].duplicated(keep=False)]
    os.makedirs("out", exist_ok=True)
    write(df)
    json.dump(report, open("out/report.json", "w"), indent=1, default=str)
    print({k: v for k, v in report.items() if k != "skipped_blocks"}, "skipped:", len(report["skipped_blocks"]))
    print(df["decision_date"].dropna().min(), df["decision_date"].dropna().max(), "no date:", df["decision_date"].isna().sum())
