import sys, fitz
d=fitz.open(sys.argv[1])
for i,p in enumerate(d): print(f"=== page {i+1}"); print(p.get_text())
