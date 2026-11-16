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

## Data dictionary

[`docs/data_dictionary.md`](docs/data_dictionary.md) lists every column of both tables with its type, a description, the share of rows that have a value, and an example, plus a diagram of how the tables join. Types, counts and examples are read from the published parquet files; descriptions are in [`docs/tables.toml`](docs/tables.toml), written from the code that builds each column. Regenerate it with

    python src/data_docs.py fetch data   # download the current files from Hugging Face
    python src/data_docs.py write data   # write docs/data_dictionary.md

`write` also updates the same section in `dataset_card.md`, the dataset card kept in this repo; the card is still uploaded to Hugging Face by hand. `src/data_docs.py` stops with an error if a parquet column has no description in `docs/tables.toml` or a described column is gone, and the weekly workflow runs that check too.

## SQLite download

The weekly workflow builds `dol-arb-decisions.sqlite` from the files on Hugging Face (tables `decisions` and `decision_text`, plus `_source`, which records the Hugging Face commit) and attaches it to the GitHub release [`latest-data`](https://github.com/abigailhaddad/dol-arb-decisions/releases/tag/latest-data). The release is replaced whenever the Hugging Face commit changes. To build it yourself:

    python src/build_sqlite.py data dol-arb-decisions.sqlite
