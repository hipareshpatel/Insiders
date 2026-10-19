import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Insiders/pipeline/src")
import pymupdf
from bse_intel import ocr
for pdf in sorted(Path(sys.argv[1]).glob("reviewer_*/*.pdf")):
    out, ocred = [], 0
    with pymupdf.open(pdf) as doc:
        for n, page in enumerate(doc):
            text = page.get_text()
            if len(text.strip()) < 150 and ocr.available() and ocred < 40:
                text = "[page read by OCR]\n" + ocr.recognise(page.get_pixmap(dpi=200).tobytes("png")); ocred += 1
            out.append(f"--- page {n + 1} ---\n{text}")
    pdf.with_suffix(".pdf.txt").write_text("\n".join(out))
    print(pdf.parent.name, pdf.stem, len(out), "pages", ocred, "OCR")
