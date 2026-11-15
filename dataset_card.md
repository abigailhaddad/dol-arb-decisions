---
license: cc0-1.0
pretty_name: DOL Administrative Review Board decisions
configs:
- config_name: decisions
  data_files: decisions.parquet
  default: true
- config_name: decision_text
  data_files: decision_text.parquet
---

# DOL Administrative Review Board decisions

Decisions of the U.S. Department of Labor's Administrative Review Board (ARB), from the two lists DOL publishes: [by party name](https://www.dol.gov/agencies/oalj/PUBLIC/ARB/REFERENCES/CASELISTS/ARBLIST_A-H) and [by month](https://www.dol.gov/agencies/oalj/PUBLIC/ARB/REFERENCES/CASELISTS/ARBINDEX). Not affiliated with DOL.

Lists read 2026-11-15 (about 00:20 EST). 3,418 decisions dated 1994-11-18 to 2026-09-29. The newest month page DOL has published is September 2026; October and November 2026 are still commented out of the index, so anything decided since then isn't here yet.

- `decisions.parquet`: one row per decision. Date, title, case name, ARB and ALJ numbers, case-type code (`program`), link, and where the row came from.
- `decision_text.parquet`: `decision_id`, `url`, `text_status`, `pages`, `text_chars`, `text`. Join on `decision_id`.

Code, checks and the weekly refresh: https://github.com/abigailhaddad/dol-arb-decisions. Browse it: https://dol-arb-decisions.pages.dev (once the explorer change is merged).

## Coverage

The name list is the base: 3,407 decision lines, 22 of them repeats of a decision listed under a second party's name, so 3,385 rows. The month list (357 pages, May 1996 to September 2026) has 4,758 document links. Each was matched to a row by the same file, a PDF/HTML or slip-opinion copy of it, or the same date plus a shared ARB or ALJ number:

| by-date links | count |
|---|---|
| matched to a name-list row | 4,650 |
| ARB decisions the name list doesn't have, added as 33 rows (`listed_on = "by-date only"`) | 51 |
| other format of an entry whose PDF or HTML link matched | 6 |
| the name list has it, but the dates differ by 7 days or less (not added; listed in `report.json`) | 4 |
| not ARB decisions (ALJ and court decisions cited in summaries), or no readable date | 47 |
| total | 4,758 |

The 33 added rows are mostly orders (reconsideration denials, dismissals, case closings) plus seven from September 2001. I searched the name list's text for ten of them by party name and ARB number: none of the ten decisions is there (two have other decisions from the same case).

106 name-list rows match no by-date link (`listed_on = "by-name, unmatched"`). 68 are from 1994 to 2000: the month list starts in May 1996, and in its early years it linked HTML copies named by ALJ number. 13 have no link in the name list. Unmatched does not mean missing from the month list: for 42 of the 96 that have a month page for their date, the party name appears on that page, so many are probably there in a form the matcher can't pair.

## Columns to read carefully

- `decision_date` is the listing's date. 12 rows have none because the listing's date is broken ("(ARB July 28, 202)", "(ARB ay 17, 2000)") or absent; they are left empty, not guessed.
- `program` is the case-type folder in the decision's link (STA, SOX, ERA, AIR, CAA, FRS, DBA, LCA...). These are OALJ's case-type codes; the table doesn't translate them.
- `file_number_in_caption` is False for 58 rows: the ARB number in the file name isn't in the caption the listing shows. Most are slips in DOL's list. Example: the name list puts Brault v. Ryder's 2007 decision (ARB No. 07-106) under the caption for Braun v. United Airlines, because Brault's caption has no decisions under it. The table keeps what the list says.
- `issued_by` is blank for 30 rows where the listing gives a date with no issuer. Ten rows are pre-ARB decisions by the Secretary, PWBA or OAA, as the list shows them.
- 10 rows share a file with another row (the list links the same PDF to two decision lines with different dates). Their `decision_id` ends in `@date`.
- No outcome column: titles such as "Decision and Order of Remand" are as listed, and I didn't derive winners from them. No judge or panel column.

## Text

523 of 3,418 rows have text. Most decisions before 2020 are hosted on www.oalj.dol.gov, whose robots.txt disallows all crawling, so they weren't fetched (`text_status = "not fetched: robots.txt disallows"`, 2,869 rows); the link still works in a browser. Of the 529 documents on www.dol.gov, 523 have text from pdftotext, 5 are scans with no text layer (no OCR was done), and 1 link is broken in DOL's list (HTTP 404). 20 rows have no link.

## Checks

- The name list's document links were counted a second way (a regex over the raw HTML instead of the parser): 3,496 distinct links both ways, none missing in either direction.
- Live sample of 106 rows (25 random, 25 random among documents on www.dol.gov, and edge cases: oldest, newest, one per case type, no link, no date, by-date only, mismatched file number, HTML document, non-ARB issuer, scanned PDF): the listing line was on the live listing page for all 106. For the 41 rows whose document could be fetched, the ARB number and party name were in the document for all 41 and the date for 40. The miss is a disagreement in DOL's own records: the list says April 18, 2002, the decision says April 19. Proof file: `checks/sample_2026-11-15.md`.
- Dates against the month list: of the 3,269 dated rows found on both lists, 3,250 sit on the month page for their own month. The other 19 are a month or a year off, which looks like a typo in one list (2019 against 2020, 2012 against 2011); the table keeps the name list's date.
- Not checked against the documents: dates and captions for rows whose documents are on www.oalj.dol.gov (most rows). For those, the month list is the only second source.
