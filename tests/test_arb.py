import os, sys
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import arb, match, refresh
from months import slug_month


def fx(name):
    return open(os.path.join(HERE, "fixtures", name)).read()


def test_dates_including_listing_typos():
    assert arb.parse_date("Final Decision and Order (ARB June 24, 2015) PDF")[:2] == ("2015-06-24", "ARB")
    assert arb.parse_date("(ARB Sept. 29, 2026)")[0] == "2026-09-29"
    assert arb.parse_date("Decision & Order (Sec'y May 1, 1996)")[:2] == ("1996-05-01", "Sec'y")
    assert arb.parse_date("Decision and Order (Nov. 12, 2024) PDF")[:2] == ("2024-11-12", None)
    assert arb.parse_date("(ARB Jan.22, 2025)")[0] == "2025-01-22"
    assert arb.parse_date("(ARB Nov, 16, 2020)")[0] == "2020-11-16"
    assert arb.parse_date("(ARB May 30,2008)")[0] == "2008-05-30"
    assert arb.parse_date("(ARB ;Apr. 20, 2021)")[0] == "2021-04-20"
    assert arb.parse_date("Petition for Reviw Without Prejudice ARB July 26, 2011) PDF")[0] == "2011-07-26"
    # broken in the listing: left empty, not guessed
    assert arb.parse_date("(ARB July 28, 202)(per curiam)")[0] is None
    assert arb.parse_date("(ARB ay 17, 2000)")[0] is None


def test_strip_dockets():
    assert arb.strip_dockets("ARB Nos. 99-073 to 99-088 AAA Striping Service Co.") == "AAA Striping Service Co."
    assert arb.strip_dockets("ARB No. 2026-0047 3M Company") == "3M Company"
    assert arb.strip_dockets("ALJ No. 1995-TSC-5 and 6 Acord v. Arco Alaska, Inc.") == "Acord v. Arco Alaska, Inc."
    assert arb.strip_dockets("ARB No. 03-086, ALJ No. 1997-MSP-9-P Zappala Farms") == "Zappala Farms"
    assert arb.strip_dockets("ARB Nos. 2024-0049, -0050, ALJ No. 2016-ERA-00012 Booker v. X") == "Booker v. X"


def test_name_page():
    rows, skipped = arb.parse_name_page(fx("name_page.html"), "ARBLIST_A-H")
    assert skipped == []
    assert len(rows) == 6
    r = rows[0]
    assert (r["arb_numbers"], r["alj_numbers"], r["decision_date"]) == ("14-021", "2013-SCA-4", "2015-06-24")
    assert r["parties"] == "Administrator, Wage and Hour Div., USDOL v. 5 Star Forestry, LLC"
    assert r["indexed_name"] == "5 Star Forestry, LLC"
    # caption and decision in one paragraph, split at <br>
    b = [x for x in rows if x["arb_numbers"] == "12-075"][0]
    assert b["parties"] == "Barrett v. Shuttle America" and b["decision_title"] == "Final Decision and Order"
    # a line that is only "PDF": date and title come from the caption
    d = rows[-1]
    assert (d["decision_date"], d["decision_title"]) == ("2003-06-30", "Final Decision & Order")
    assert d["parties"] == "Dierkes v. West Linn-Wilsonville School District"
    # the listing puts Brault's 2007 decision under Braun's caption; we keep what the listing says
    br = [x for x in rows if x["decision_date"] == "2007-10-31"][0]
    assert br["parties"].startswith("Braun")
    assert arb.file_arb_number(br["doc_urls"][0]) not in arb.caption_arb_numbers(br["caption"])


def test_doc_keys_and_twins():
    a = arb.doc_key("/sites/dolgov/files/OALJ/PUBLIC/ARB/DECISIONS/ARB_DECISIONS/ERA/2024-0049-ERAP.pdf")
    b = arb.doc_key("https://www.oalj.dol.gov/PUBLIC/ARB/DECISIONS/ARB_DECISIONS/ERA/2024-0049-ERAP.PDF")
    assert a == b
    k = arb.doc_key("https://www.oalj.dol.gov/PUBLIC/ARB/DECISIONS/ARB_DECISIONS/ERA/17_053.ERAP.PDF")
    assert k.replace(".pdf", "_slip_op.pdf") in arb.twin_keys(k)
    assert k.replace(".pdf", ".htm") in arb.twin_keys(k)
    assert arb.program_from_url("https://x/PUBLIC/ARB/DECISIONS/ARB_DECISIONS/SOX/09_076.SOXP.PDF") == "SOX"


def test_arb_numbers():
    assert arb.file_arb_number("https://x/SOX/2024-0049-ERAP.pdf") == (24, 49)
    assert arb.file_arb_number("https://x/FRS/16_0085.FRSP_SLIP_OP.PDF") == (16, 85)
    assert arb.file_arb_number("https://x/SOX/09_076.SOXP.PDF") == (9, 76)
    assert arb.file_arb_number("https://x/ERA/1996ERA10P.PDF") is None
    assert arb.caption_arb_numbers("ARB Nos. 15-032, -033, ALJ No. 2014-LCA-8") == {(15, 32), (15, 33)}
    assert arb.caption_arb_numbers("ARB No. 2018-0020") == {(18, 20)}


def test_month_pages():
    e26 = arb.parse_month_page(fx("month_2026_09.html"))
    first = e26[0]
    assert first["url"].endswith("2024-0049-ERAP.pdf")
    assert arb.parse_date(match.head(first["block"]))[0] == "2026-09-29"
    # 2017 pages put "PDF (slip opinion)" on its own line; the citation is found in the block above
    e17 = arb.parse_month_page(fx("month_2017_01.html"))
    assert e17 and all(arb.parse_date(match.head(e["block"]))[0] for e in e17[:10])
    assert slug_month("09_2026") == "2026-09" and slug_month("0399") == "1999-03"


def test_entry_row():
    e = {"block": "Del Signore v. Nokia , ARB No. 2020-0052, ALJ No. 2019-CFP-00001 (ARB Oct. 21, 2020) "
                  "(Order of Dismissal) PDF", "alj": {"2019-CFP-00001"}}
    r = match.entry_row(e)
    assert (r["case_name"], r["decision_date"], r["decision_title"], r["arb_numbers"]) == \
        ("Del Signore v. Nokia", "2020-10-21", "Order of Dismissal", "2020-0052")


def test_refresh_merge_keeps_old_rows_and_adds_new():
    old = pd.DataFrame({"decision_id": ["A", "B"], "x": [1, 2]})
    new = pd.DataFrame({"decision_id": ["B", "C"], "x": [20, 3]})
    m = refresh.merge(old, new)
    assert sorted(m["decision_id"]) == ["A", "B", "C"]
    assert m.set_index("decision_id").loc["B", "x"] == 20
