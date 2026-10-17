"""Apply the scorer audit's hand-checked findings (data/bench/reports/scorer-audit.md) to the answer key:
the figures each PDF never prints, and the unit of the filings whose text layer does not say it."""
import json, pathlib
p = pathlib.Path(r"D:\Insiders\data\bench\manifest.json")
man = json.loads(p.read_text(encoding="utf-8"))
SUM_OF_ROWS = "the XBRL figure is a total of rows the statement prints separately"
UNPRINTED = {
    "daee44c8": {"tax_expense": SUM_OF_ROWS},
    "e87824b7": {"tax_expense": SUM_OF_ROWS, "other_expenses": SUM_OF_ROWS, "total_expenses": "the XBRL total includes lines the printed total does not"},
    "85751073": {"tax_expense": SUM_OF_ROWS, "total_expenses": "the XBRL total includes finance cost and depreciation; the printed one does not"},
    "5f89acb4": {"tax_expense": SUM_OF_ROWS, "total_expenses": "the PDF prints 43,741 lakh; the XBRL total is 46,500"},
    "697d0fbb": {"tax_expense": SUM_OF_ROWS, "other_expenses": SUM_OF_ROWS, "pbt": "XBRL is before the share of associates; the PDF prints PBT after it"},
    "bcad18ec": {"tax_expense": SUM_OF_ROWS, "other_expenses": "1,090.73 is the sum of four printed rows", "pbt": "159.37 is before the share of associates; printed PBT is 165.97"},
    "1e874774": {"tax_expense": "0.22 = current 0.03 + deferred 0.19, printed separately"},
    "cfe58901": {"tax_expense": SUM_OF_ROWS},
    "983aa10c": {"other_expenses": SUM_OF_ROWS}, "e4a61c7f": {"other_expenses": SUM_OF_ROWS},
    "e9ae2c81": {"other_expenses": SUM_OF_ROWS}, "2531d7cc": {"other_expenses": SUM_OF_ROWS},
    "139e9236": {"pbt": "the PDF prints 1,305 million (130.5 crore); XBRL says 130.8"},
    "db04e18b": "ALL",
}
UNIT = {"f6495f61": 100, "697d0fbb": 1, "bcad18ec": 1, "1e874774": 1, "cfe58901": 1}   # read off the PDFs
for item in man:
    k = item["news_id"][:8]
    u = UNPRINTED.get(k)
    if u == "ALL":
        item["unprinted"] = {m: "the PDF is a press release, not the results statement" for m in item["truth_crore"]}
    elif u:
        item["unprinted"] = {m: why for m, why in u.items() if m in item["truth_crore"]}
    if k in UNIT:
        item["unit_checked"] = UNIT[k]
p.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
print(sum(len(i.get("unprinted", {})) for i in man), "figures marked unprinted;",
      sum(len(i["truth_crore"]) - len(i.get("unprinted", {})) for i in man), "printed figures left")
