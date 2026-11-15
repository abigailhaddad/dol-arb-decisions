# dol-arb-decisions

Decisions of the Department of Labor's Administrative Review Board (ARB), as one table on Hugging Face: https://huggingface.co/datasets/abigailhaddad/dol-arb-decisions. Not affiliated with DOL.

The ARB hears appeals of DOL administrative law judge decisions: whistleblower cases (STAA trucking, Sarbanes-Oxley, the nuclear and environmental statutes, AIR21, FRSA rail), Davis-Bacon and Service Contract Act wage cases, H-1B and H-2A/H-2B cases, OFCCP contract compliance, and a few dozen smaller programs.

DOL publishes two lists of these decisions: one by party name (three pages, A-H, I-P, Q-Z) and one by month (a page per month back to 1996). The table is built from the name list, checked against the month list, and the decisions only the month list has are added. Each row has the date, title, case name, ARB and ALJ numbers, the case-type code, the link to the decision, and, for decisions hosted on www.dol.gov, the decision's text (extracted from the PDF with pdftotext, in a second file). Older decisions are on www.oalj.dol.gov, whose robots.txt disallows all crawling, so they have a link but no text.

A GitHub Action runs every Monday, re-reads both lists, and uploads only if something changed. It needs a repository secret `HF_TOKEN` with write access to the dataset. **That secret is not set yet**: until it is, the run does everything except the upload and says so in its log.

## Run it

    pip install -r requirements-dev.txt     # plus poppler (pdftotext)
    python -m pytest tests
    python src/crawl.py                     # the two lists, one request a second, into raw/ (about 6 minutes)
    python src/text.py                      # documents on www.dol.gov into raw/text.jsonl (about 10 minutes)
    python src/build.py                     # raw/ -> out/decisions.parquet, out/decision_text.parquet, out/report.json
    python src/check.py counts              # reconcile counts against the raw pages, by a separate path
    python src/check.py sample              # re-fetch a sample from dol.gov, write checks/sample_<date>.md
    python src/refresh.py --dry-run         # what the weekly job does, without the upload

`src/arb.py` parses the pages. `src/match.py` matches the month list's links to rows. The checks and their results are on the dataset card (`dataset_card.md`, uploaded as the Hugging Face README); the most recent live sample is in `checks/`.

dol.gov's CDN refused the custom User-Agent strings I tried and accepts the `requests` default, so the code sends the default.
