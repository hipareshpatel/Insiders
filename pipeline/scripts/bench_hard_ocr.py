"""RapidOCR on the seven complicated pages: the agent's best settings, rows rebuilt from box positions."""
import json, os, sys, time
sys.path.insert(0, r"D:\Insiders\data\bench\scripts\paddle")
import cv2, numpy as np, pymupdf
from rapidocr import RapidOCR, ModelType
import rowbuild as rb
PDFS = r"D:\Insiders\data\bench\pages\pdfs"
PAGES = {"A_novartis_statement": ("2ed299f9", 3), "B_jubilant_aoc1_left": ("a42957c1", 214),
         "C_ahluwalia_ppe_note": ("56a8f73b", 162), "D_kanoria_governance_grid": ("69b11463", 2),
         "E_sml_rating_letter": ("c6b7260b", 0), "F_kanoria_statement": ("83d503cf", 8),
         "G_jubilant_results": ("3eec0c2f", 8)}
engine = RapidOCR(params={"Global.max_side_len": 3300, "Global.use_cls": True, "Global.log_level": "warning",
                          "EngineConfig.onnxruntime.intra_op_num_threads": 4, "Det.model_type": ModelType("small"),
                          "Rec.model_type": ModelType("small"), "Det.box_thresh": 0.5, "Det.unclip_ratio": 1.6,
                          "Det.limit_type": "min", "Det.limit_side_len": 736})
def read(img):
    res = engine(img); bx = []
    if res is not None and res.boxes is not None and res.txts is not None:
        for pts, txt, sc in zip(res.boxes, res.txts, res.scores):
            xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
            bx.append({"x0": float(min(xs)), "y0": float(min(ys)), "x1": float(max(xs)), "y1": float(max(ys)), "text": txt, "score": float(sc)})
    n = sum(len(b["text"]) for b in bx)
    return bx, (sum(b["score"] * len(b["text"]) for b in bx) / n if n else 0.0)
out, log = {}, {}
for key, (prefix, idx) in PAGES.items():
    pg = pymupdf.open(os.path.join(PDFS, next(f for f in os.listdir(PDFS) if f.startswith(prefix))))[idx]
    pix = pg.get_pixmap(dpi=200)
    img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)
    t = time.time()
    boxes, ms = read(img); rot = "0"
    # A sideways table reads with high confidence - each line is recognised - but its boxes stand on end,
    # and grouping them by height then turns the table's columns into rows. Upright text lies flat.
    def upright(bx): return sum(1 for b in bx if (b["x1"] - b["x0"]) >= (b["y1"] - b["y0"])) / max(1, len(bx))
    if upright(boxes) < 0.5 and len(boxes) >= 8:
        best = None
        for name, code in (("90cw", cv2.ROTATE_90_CLOCKWISE), ("90ccw", cv2.ROTATE_90_COUNTERCLOCKWISE)):
            b2, m2 = read(cv2.rotate(img, code))
            if upright(b2) >= 0.5 and (best is None or m2 > best[1]):
                best = (b2, m2, name)
        if best:
            boxes, ms, rot = best
    elif ms < 0.92 and len(boxes) >= 8:
        for name, code in (("90cw", cv2.ROTATE_90_CLOCKWISE), ("90ccw", cv2.ROTATE_90_COUNTERCLOCKWISE), ("180", cv2.ROTATE_180)):
            b2, m2 = read(cv2.rotate(img, code))
            if m2 > ms + 0.01:
                boxes, ms, rot = b2, m2, name
    rows = rb.rows_to_entries(rb.group_rows(boxes), 1)
    out[key] = [(" ".join([r.get("label", "")] + r.get("cells", []))).strip() for r in rows]
    log[key] = f"{time.time() - t:.1f}s rot={rot} score={ms:.3f} rows={len(rows)}"
    print(key, log[key], flush=True)
json.dump(out, open(r"D:\Insiders\data\bench\hard\out\rapidocr-200.json", "w", encoding="utf-8"), ensure_ascii=False)
