"""Save the ARB's published decision listings to raw/.

    python src/crawl.py            # the three by-name pages, the by-date index, and every month it links to

One request per second. Stops on any status other than 200.
"""
import os, re, sys, time
import requests

BASE = "https://www.dol.gov/agencies/oalj/PUBLIC/ARB/REFERENCES/CASELISTS/"
# No custom User-Agent: dol.gov's CDN refused the two custom strings tried, and accepts the requests default.
NAME_PAGES = ["ARBLIST_A-H", "ARBLIST_I-P", "ARBLIST_Q-Z"]


def get(session, url, pause=1.0):
    time.sleep(pause)
    r = session.get(url, timeout=60)
    if r.status_code != 200:
        sys.exit(f"STOP: {r.status_code} on {url}")
    return r.text


def month_pages(index_html):
    """Month page slugs linked from the by-date index, e.g. 09_2026, in page order."""
    index_html = re.sub(r"<!--.*?-->", "", index_html, flags=re.S)  # future months sit in comments
    seen = []
    for slug in re.findall(r'href="/agencies/oalj/PUBLIC/ARB/REFERENCES/CASELISTS/([0-9A-Za-z_\-]+)"', index_html):
        if slug.upper().startswith("ARBLIST") or slug.upper() == "ARBINDEX" or slug in seen:
            continue
        seen.append(slug)
    return seen


def main(out="raw"):
    os.makedirs(f"{out}/month", exist_ok=True)
    s = requests.Session()
    for p in NAME_PAGES:
        open(f"{out}/{p}.html", "w").write(get(s, BASE + p))
    idx = get(s, BASE + "ARBINDEX")
    open(f"{out}/ARBINDEX.html", "w").write(idx)
    slugs = month_pages(idx)
    print(len(slugs), "month pages linked")
    for slug in slugs:
        open(f"{out}/month/{slug}.html", "w").write(get(s, BASE + slug))
    print("done")


if __name__ == "__main__":
    main()
