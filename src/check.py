"""Checks on the built table, by a different path than the build.

    python src/check.py counts           # reconcile counts (no network)
    python src/check.py sample [n]       # live sample: n random rows plus edge cases -> checks/sample_<date>.md

counts: re-counts the by-name listing's document links with a plain regex over the raw HTML (the build uses
BeautifulSoup), accounts for every by-date link, and breaks down rows the by-date listing doesn't have.

sample: for each sampled row, re-fetches the listing page it came from and the decision document itself
(text read with pypdf; the build's text column uses pdftotext) and compares date, ARB number, party name and
the listing line field by field.
"""
import io, json, os, random, re, sys, time
from datetime import date
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
import arb
from crawl import BASE, NAME_PAGES

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def counts():
    df = pd.read_parquet("out/decisions.parquet")
    rep = json.load(open("out/report.json"))
    out = {}
    # 1. by-name links, counted with a regex instead of the parser
    keys = set()
    for p in NAME_PAGES:
        html = open(f"raw/{p}.html").read()
        body = html[html.find("<article"):html.find("</article>")]
        for h in re.findall(r'href="([^"]+)"', body):
            if re.search(r"\.(pdf|htm|html)$", h.strip().split("?")[0].split("#")[0], re.I):
                keys.add(arb.doc_key(h))
    name_rows = df[df["listed_on"] != "by-date only"]
    table_keys = set()
    for u, o in zip(name_rows["url"], name_rows["other_urls"]):
        for x in ([u] if isinstance(u, str) else []) + (o.split() if isinstance(o, str) else []):
            table_keys.add(arb.doc_key(x))
    out["by_name_distinct_links_regex"] = len(keys)
    out["by_name_distinct_links_in_table"] = len(table_keys)
    out["links_regex_found_not_in_table"] = sorted(keys - table_keys)
    out["links_in_table_not_found_by_regex"] = sorted(table_keys - keys)
    # 2. rows
    out["rows"] = len(df)
    out["rows_by_listed_on"] = df["listed_on"].value_counts().to_dict()
    out["name_listing_lines"] = rep["name_listing_lines"]
    out["collapsed_duplicate_lines"] = rep["collapsed_duplicate_lines"]
    assert rep["name_listing_lines"] - rep["collapsed_duplicate_lines"] == rep["name_listing_decisions"]
    assert rep["name_listing_decisions"] + rep["rows_added_from_date_listing"] == len(df)
    # 3. every by-date link accounted for
    matched = sum(rep["date_listing_links_matched"].values())
    acc = {"matched to a by-name row": matched,
           "became a by-date-only row": rep["date_listing_links_in_added_rows"],
           "other format (PDF/HTML) of the same by-date entry matched a row": len(rep["date_listing_links_whose_other_format_matched"]),
           "date differs from the by-name row by 7 days or less (not added)": len(rep["date_listing_date_disagreements"]),
           "not an ARB decision file (ALJ or court decision cited in a summary), or no date (not added)": len(rep["unmatched_links_not_added"])}
    out["date_listing_links"] = rep["date_listing_links"]
    out["date_listing_links_accounted"] = acc
    assert sum(acc.values()) == rep["date_listing_links"], (acc, rep["date_listing_links"])
    # 4. by-name rows the by-date listing doesn't have, by year
    only = df[df["listed_on"] == "by-name, unmatched"]
    out["by_name_only_by_year"] = {str(k): int(v) for k, v in
                                   pd.to_datetime(only["decision_date"]).dt.year.value_counts(dropna=False).sort_index().items()}
    json.dump(out, open("out/counts.json", "w"), indent=1, default=str)
    for k, v in out.items():
        print(k, ":", v if not isinstance(v, list) else f"{len(v)} {v[:5]}")
    return out


def date_strings(d):
    """Ways a decision date is written in ARB documents."""
    m = MONTH_NAMES[d.month - 1]
    ab = {9: "Sept"}.get(d.month, m[:3])
    return [f"{m} {d.day}, {d.year}", f"{ab}. {d.day}, {d.year}", f"{m} {d.day} {d.year}", f"{d.day} {m} {d.year}",
            f"{m} {d.day},{d.year}"]


def squash(s):
    return re.sub(r"\s+", " ", s or "").strip()


def doc_text(url, session):
    import text as textmod
    if not textmod.allowed(url):
        return "robots.txt disallows", ""
    r = session.get(url, timeout=120)
    if r.status_code != 200:
        return r.status_code, ""
    if r.content[:5] == b"%PDF-":
        from pypdf import PdfReader
        try:
            t = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages[:3])
        except Exception as e:
            t = f"[pypdf failed: {type(e).__name__}]"
        return 200, t
    from bs4 import BeautifulSoup
    return 200, BeautifulSoup(r.content, "lxml").get_text(" ")


def arb_forms(row):
    """ARB numbers on the row, in the forms documents use: 14-021, 2014-0021, 14-0021."""
    nums = arb.caption_arb_numbers(row["caption"]) | arb.caption_arb_numbers(row["listing_line"])
    forms = set()
    for y, n in nums:
        yy = 1900 + y if y > 50 else 2000 + y
        forms |= {f"{y:02d}-{n:03d}", f"{yy}-{n:04d}", f"{y:02d}-{n:04d}"}
    return forms


def pick(df, n, seed):
    rnd = df.sample(n=n, random_state=seed)
    picks = [(r, "random") for _, r in rnd.iterrows()]
    have = set(rnd["decision_id"])
    # most documents are on www.oalj.dol.gov, whose robots.txt disallows fetching; a second random set from
    # documents on www.dol.gov gets the document-side comparison
    dolgov = df[df["url"].fillna("").str.startswith("https://www.dol.gov/") & ~df["decision_id"].isin(have)]
    for _, r in dolgov.sample(n=min(n, len(dolgov)), random_state=seed).iterrows():
        picks.append((r, "random, document on www.dol.gov"))
        have.add(r["decision_id"])

    def add(sub, why):
        sub = sub[~sub["decision_id"].isin(have)]
        if len(sub):
            r = sub.iloc[0]
            have.add(r["decision_id"])
            picks.append((r, why))

    dated = df.dropna(subset=["decision_date"]).sort_values("decision_date")
    add(dated.head(1), "oldest date")
    add(dated.tail(1), "newest date")
    for prog in sorted(df["program"].dropna().unique()):
        add(df[df["program"] == prog].sample(frac=1, random_state=seed), f"case type {prog}")
    add(df[df["url"].isna()], "no document link")
    add(df[df["decision_date"].isna() & df["url"].notna()], "no readable date")
    add(df[df["listed_on"] == "by-date only"].sample(frac=1, random_state=seed), "by-date listing only")
    add(df[df["file_number_in_caption"] == False].sample(frac=1, random_state=seed), "file number not in caption")
    add(df[df["url"].fillna("").str.lower().str.endswith(".htm")], "HTML document")
    add(df[df["issued_by"].isin(["Sec'y", "PWBA", "OAA"])], "not issued by the ARB")
    add(df[df["times_listed"] > 1], "listed twice on the by-name listing")
    if "text_status" in df:
        add(df[df["text_status"].isin(["no text layer"])], "PDF with no text layer")
    return picks


def listing_url(row):
    if row["listed_on"] == "by-date only":
        return BASE + row["listing_page"]
    return BASE + row["listing_page"]


def sample(n=25, seed=20261115):
    df = pd.read_parquet("out/decisions.parquet")
    df = df.astype(object).where(df.notna(), None)
    picks = pick(df, n, seed)
    s = requests.Session()
    pages = {}
    results = []
    for row, why in picks:
        lu = listing_url(row)
        if lu not in pages:
            time.sleep(1)
            r = s.get(lu, timeout=60)
            from bs4 import BeautifulSoup
            pages[lu] = squash(BeautifulSoup(r.text, "lxml").get_text(" ")) if r.status_code == 200 else ""
        page = pages[lu]
        # " | " joins a by-date citation to its link label in our listing_line; the page has just a space
        line_ok = squash(row["listing_line"].replace(" | ", " "))[:120] in page
        status, text = (None, "")
        if isinstance(row["url"], str):
            time.sleep(1)
            status, text = doc_text(row["url"], s)
        t = squash(text)
        d = row["decision_date"]
        date_ok = None if pd.isna(d) or not t else any(x in t for x in date_strings(d))
        forms = arb_forms(row)
        arb_ok = None if not forms or not t else any(f in t for f in forms)
        party = re.split(r"[ ,.]", squash(row["indexed_names"] or row["case_name"] or ""))[0]
        party_ok = None if len(party) < 3 or not t else party.lower() in t.lower()
        results.append({"why": why, "row": row, "listing": lu, "line_ok": line_ok, "status": status,
                        "date_ok": date_ok, "arb_ok": arb_ok, "party": party, "party_ok": party_ok,
                        "snippet": t[:400]})
    write_md(results)
    return results


def mark(v):
    return {True: "yes", False: "**NO**", None: "n/a"}[v]


def write_md(results):
    today = date.today().isoformat()
    os.makedirs("checks", exist_ok=True)
    path = f"checks/sample_{today}.md"
    n = len(results)
    tally = {k: sum(r[k] is True for r in results) for k in ("line_ok", "date_ok", "arb_ok", "party_ok")}
    applicable = {k: sum(r[k] is not None for r in results) for k in ("line_ok", "date_ok", "arb_ok", "party_ok")}
    L = [f"# Live sample, {today}", "",
         f"{n} rows: 25 picked at random from the whole table, 25 at random from rows whose document is on "
         "www.dol.gov, and edge cases (seed 20261115). Documents on www.oalj.dol.gov were not fetched because that "
         "host's robots.txt disallows it, so for those rows only the listing line is checked. For each row, the listing page it came from "
         "was fetched again and searched for the row's listing line, and the decision document was fetched and "
         "read with pypdf (first three pages) or as HTML, then searched for the row's date, ARB number and first "
         "party name. \"n/a\" means the row has no value to check (no link, no date, no ARB number).", "",
         "| check | matched | checked |", "|---|---|---|"]
    for k, lab in [("line_ok", "listing line on the live listing page"), ("date_ok", "date in the document"),
                   ("arb_ok", "ARB number in the document"), ("party_ok", "party name in the document")]:
        L.append(f"| {lab} | {tally[k]} | {applicable[k]} |")
    L += ["", "Misses are explained under each row below.", ""]
    for i, r in enumerate(results, 1):
        row = r["row"]
        L += [f"## {i}. {row['decision_id']} ({r['why']})", "",
              f"- Listing page: <{r['listing']}> - listing line found: {mark(r['line_ok'])}",
              f"- Document: <{row['url']}> (HTTP {r['status']})" if isinstance(row["url"], str) else "- Document: none listed",
              "", "| field | our value | in the document |", "|---|---|---|",
              f"| decision_date | {row['decision_date']} | {mark(r['date_ok'])} |",
              f"| arb_numbers | {row['arb_numbers']} | {mark(r['arb_ok'])} |",
              f"| party ({r['party']}) | {row['case_name']} | {mark(r['party_ok'])} |",
              f"| decision_title | {row['decision_title']} | (listing) |",
              f"| program | {row['program']} | (link folder) |",
              f"| listing_line | {squash(row['listing_line'])[:200]} | |", "",
              f"Document opens with: `{r['snippet'][:300].replace('`', '')}`", ""]
    open(path, "w").write("\n".join(L))
    print("wrote", path)
    for k in tally:
        print(k, tally[k], "of", applicable[k])
    for r in results:
        bad = [k for k in ("line_ok", "date_ok", "arb_ok", "party_ok") if r[k] is False]
        if bad:
            print("MISS", r["row"]["decision_id"], r["why"], bad)


if __name__ == "__main__":
    if sys.argv[1:2] == ["sample"]:
        sample(int(sys.argv[2]) if len(sys.argv) > 2 else 25)
    else:
        counts()
