"""Fetch each decision's document (the row's `url`) and extract its text with pdftotext (poppler).

    python src/text.py              # resumes: skips urls already in raw/text.jsonl
    python src/text.py --ids A B    # only these decision_ids (used by the daily refresh)

One request per second, and only where the host's robots.txt allows it. Most pre-2020 decisions are on
www.oalj.dol.gov, whose robots.txt disallows all crawling, so they get no text
(`text_status = "not fetched: robots.txt disallows"`). The PDF is deleted after extraction; only the text is kept. Scanned PDFs with no
text layer come back empty (no OCR is done) and are marked `text_status = "no text layer"`.
"""
import json, os, subprocess, sys, tempfile, time
from urllib import robotparser
from urllib.parse import urlsplit
import pandas as pd
import requests
from bs4 import BeautifulSoup

CACHE = "raw/text.jsonl"


_robots = {}


def allowed(url):
    """robots.txt for the url's host. www.oalj.dol.gov disallows everything, so its documents are not fetched."""
    host = urlsplit(url).scheme + "://" + urlsplit(url).netloc
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        r = requests.get(host + "/robots.txt", timeout=60)
        if r.status_code in (401, 403):
            rp.disallow_all = True
        elif r.status_code >= 400:
            rp.allow_all = True
        else:
            rp.parse(r.text.splitlines())
        _robots[host] = rp
    return _robots[host].can_fetch("*", url)


def extract(url, session):
    r = session.get(url, timeout=120)
    out = {"url": url, "http_status": r.status_code, "content_type": r.headers.get("content-type", "")}
    if r.status_code != 200:
        return {**out, "text": None, "pages": None, "text_status": f"HTTP {r.status_code}"}
    if r.content[:5] == b"%PDF-":
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "doc.pdf")
            open(p, "wb").write(r.content)
            res = subprocess.run(["pdftotext", "-enc", "UTF-8", p, "-"], capture_output=True, timeout=300)
        text = res.stdout.decode("utf-8", "replace")
        pages = text.count("\f") or None  # pdftotext ends every page with a form feed
        status = "ok" if len(text.strip()) > 200 else "no text layer"
        if res.returncode != 0:
            status = "pdftotext error"
        return {**out, "text": text, "pages": pages, "text_status": status}
    if "html" in out["content_type"].lower() or url.lower().endswith((".htm", ".html")):
        soup = BeautifulSoup(r.content, "lxml")
        for t in soup(["script", "style"]):
            t.decompose()
        text = soup.get_text("\n")
        return {**out, "text": text, "pages": None, "text_status": "ok (html)" if len(text.strip()) > 200 else "short html"}
    return {**out, "text": None, "pages": None, "text_status": "not a PDF or HTML file"}


def main():
    df = pd.read_parquet("out/decisions.parquet")
    if "--ids" in sys.argv:
        df = df[df["decision_id"].isin(sys.argv[sys.argv.index("--ids") + 1:])]
    done = set()
    if os.path.exists(CACHE):
        done = {json.loads(l)["url"] for l in open(CACHE)}
    todo = [u for u in df["url"].dropna().unique() if u not in done]
    print(len(todo), "to fetch;", len(done), "cached", flush=True)
    s = requests.Session()
    last = 0.0
    with open(CACHE, "a") as f:
        for i, u in enumerate(todo):
            if not allowed(u):
                f.write(json.dumps({"url": u, "http_status": None, "content_type": None, "text": None, "pages": None,
                                    "text_status": "not fetched: robots.txt disallows"}) + "\n")
                f.flush()
                continue
            time.sleep(max(0.0, 1.0 - (time.time() - last)))  # at most one request a second
            last = time.time()
            try:
                rec = extract(u, s)
            except Exception as e:  # recorded, not skipped silently: the row keeps text_status
                rec = {"url": u, "http_status": None, "content_type": None, "text": None, "pages": None,
                       "text_status": f"error: {type(e).__name__}"}
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if i % 200 == 0:
                print(i, rec["text_status"], u, flush=True)


if __name__ == "__main__":
    main()
