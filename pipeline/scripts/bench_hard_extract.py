"""Every text extractor's lines for the seven complicated pages."""
import json, os, collections, time
import pymupdf, pdfplumber, pymupdf4llm
PDFS = r"D:\Insiders\data\bench\pages\pdfs"
PAGES = {"A_novartis_statement": ("2ed299f9", 3), "B_jubilant_aoc1_left": ("a42957c1", 214),
         "C_ahluwalia_ppe_note": ("56a8f73b", 162), "D_kanoria_governance_grid": ("69b11463", 2),
         "E_sml_rating_letter": ("c6b7260b", 0), "F_kanoria_statement": ("83d503cf", 8),
         "G_jubilant_results": ("3eec0c2f", 8)}
def path(prefix): return os.path.join(PDFS, next(f for f in os.listdir(PDFS) if f.startswith(prefix)))

def pymupdf_text(pg, sort): return pg.get_text("text", sort=sort).splitlines()
def pymupdf_words(pg, tol=3.0):
    lines = []
    for w in sorted(pg.get_text("words"), key=lambda w: (round(w[3]), w[0])):
        if lines and abs(lines[-1][0][3] - w[3]) <= tol: lines[-1].append(w)
        else: lines.append([w])
    return [" ".join(w[4] for w in sorted(l, key=lambda w: w[0])) for l in lines]
def plumber_words(pl, tol=3):
    by = collections.defaultdict(list)
    for w in pl.extract_words(x_tolerance=1.5, use_text_flow=False):
        by[round(w["bottom"] / tol)].append(w)
    return [" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])) for _, ws in sorted(by.items())]
def plumber_layout(pl): return (pl.extract_text(layout=True) or "").splitlines()

out = collections.defaultdict(dict); timing = collections.defaultdict(float)
for key, (prefix, idx) in PAGES.items():
    doc = pymupdf.open(path(prefix)); pg = doc[idx]
    for name, fn in (("pymupdf-sorted", lambda: pymupdf_text(pg, True)), ("pymupdf-default", lambda: pymupdf_text(pg, False)),
                     ("pymupdf-words", lambda: pymupdf_words(pg))):
        t = time.monotonic(); out[name][key] = fn(); timing[name] += time.monotonic() - t
    with pdfplumber.open(path(prefix)) as pdf:
        pl = pdf.pages[idx]
        for name, fn in (("plumber-words", lambda: plumber_words(pl)), ("plumber-layout", lambda: plumber_layout(pl))):
            t = time.monotonic(); out[name][key] = fn(); timing[name] += time.monotonic() - t
    t = time.monotonic()
    md = pymupdf4llm.to_markdown(doc, pages=[idx], show_progress=False)
    out["pymupdf4llm"][key] = [l.replace("|", " ") for l in md.splitlines()]
    timing["pymupdf4llm"] += time.monotonic() - t
for name, pages in out.items():
    json.dump(pages, open(rf"D:\Insiders\data\bench\hard\out\{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
print({k: f"{v:.1f}s" for k, v in timing.items()})
