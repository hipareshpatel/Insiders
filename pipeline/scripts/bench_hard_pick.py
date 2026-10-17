"""Pages where text extractors disagree most about which figures sit on which line: the complicated ones."""
import sys, json, re, collections
import pymupdf, pdfplumber
pages = json.load(open(r"D:\Insiders\data\bench\pages\pages.json", encoding="utf-8"))
NUM = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?%?")
def lines_figs(lines):
    return [tuple(n for n in NUM.findall(l) if sum(c.isdigit() for c in n) >= 2) for l in lines]
def pairs(lines):
    """(figure, neighbour figure) pairs on the same line: which figures an extractor puts together."""
    out = collections.Counter()
    for figs in lines_figs(lines):
        for a, b in zip(figs, figs[1:]):
            out[(a, b)] += 1
    return out
rows = []
for p in pages:
    path = r"D:\Insiders\data\bench\pages\\" + p["pdf"].replace("/", "\\")
    doc = pymupdf.open(path); pg = doc[p["page"]]
    sort = pg.get_text("text", sort=True).splitlines()
    default = pg.get_text("text").splitlines()
    with pdfplumber.open(path) as pl:
        words = pl.pages[p["page"]].extract_words(x_tolerance=1.5, keep_blank_chars=False)
    by_line = collections.defaultdict(list)
    for w in words:
        by_line[round(w["bottom"])].append(w)
    plumb = [" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])) for _, ws in sorted(by_line.items())]
    a, b, c = pairs(sort), pairs(plumb), pairs(default)
    union = (a | b)
    agree = sum((a & b).values()) / max(1, sum(union.values()))
    cols = len({round(blk[0] / 50) for blk in pg.get_text("blocks") if blk[4].strip() and len(blk[4]) > 40})
    rows.append((agree, p["event_type"], p["company"][:20], p["news_id"], p["page"], len(p["figures"]), cols))
rows.sort()
print("lowest agreement between reading-order text and pdfplumber on which figures share a line:")
for agree, et, co, nid, pg, nf, cols in rows[:24]:
    print(f"  {agree:.2f}  {et:24} {co:20} {nid[:8]} p{pg+1:<3} figures {nf:4}  text-block columns {cols}")
json.dump([{"news_id": r[3], "page": r[4], "event_type": r[1], "company": r[2], "agree": r[0]} for r in rows],
          open(r"D:\Insiders\data\bench\pages\disagreement.json", "w"), indent=1)
