"""Build the official sums and labels of SEBI's results taxonomies into pipeline/config/xbrl_sums/ (item 23, owner
25 Oct 2026). Input: the taxonomy packages NSE publishes on its "XBRL information" page
(https://www.nseindia.com/static/companies-listing/xbrl-information), common to NSE and BSE. Run once per new version:

    python scripts/xbrl_taxonomy_build.py <package.zip> [<package.zip> ...]

For each package it writes one JSON: the template key, the version, every calculation relation as
{total: [[item, weight], ...]} (by element name, roles merged) and the official label of each element in them.
No network, no AI."""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "config" / "xbrl_sums"

# package folder -> the key xbrl.template_key() gives an instance filed on it
KEYS = {
    "IntegratedFinance_IndAS": "INDAS", "IntegratedFinance_OtherThanBank": "OTHERTHANBANK",
    "IntegratedFinance_Banking": "BANKING", "IntegratedFinance_NBFC": "NBFC", "IntegratedFinance_GI": "GI",
    "IntegratedFinance_LI": "LI",
    "Ind AS Taxonomy": "LEGACY_INDAS", "Main Taxonomy": "LEGACY_OTHERTHANBANK", "Banking Taxonomy": "LEGACY_BANKING",
    "NBFC Taxonomy": "LEGACY_NBFC", "General Insurance": "LEGACY_GI", "Life Insurance Taxonomy": "LEGACY_LI",
}
_LOC = re.compile(r'<(?:link:)?loc\b[^>]*?xlink:href="[^"#]*#([^"]+)"[^>]*?xlink:label="([^"]+)"', re.S)
_LOC2 = re.compile(r'<(?:link:)?loc\b[^>]*?xlink:label="([^"]+)"[^>]*?xlink:href="[^"#]*#([^"]+)"', re.S)
_ARC = re.compile(r'<(?:link:)?calculationArc\b([^>]*)/?>', re.S)
_ATTR = re.compile(r'([\w:]+)="([^"]*)"')
_LAB = re.compile(r'<(?:link:)?label\b([^>]*)>([^<]*)<', re.S)
_LABARC = re.compile(r'<(?:link:)?labelArc\b([^>]*)/?>', re.S)


def _name(href_id: str) -> str:
    return href_id.split("_", 1)[1] if "_" in href_id else href_id


def _locs(text: str) -> dict[str, str]:
    out = {label: _name(h) for h, label in _LOC.findall(text)}
    out.update({label: _name(h) for label, h in _LOC2.findall(text)})
    return out


def build(path: Path) -> dict:
    box = zipfile.ZipFile(path)
    names = box.namelist()
    key = next((k for folder, k in KEYS.items() for n in names if folder in n), None)
    if key is None:
        raise SystemExit(f"{path.name}: no known template folder in {names[:5]}")
    sums: dict[str, list] = {}
    version = ""
    for n in names:
        if n.endswith(".xml") and re.search(r"cal[-_]", n.rsplit("/", 1)[-1]):
            text = box.read(n).decode("utf-8", "ignore")
            version = max(version, (re.search(r"(\d{4}-\d{2}-\d{2})", n) or [""])[0] if re.search(r"\d{4}-\d{2}-\d{2}", n) else "")
            locs = _locs(text)
            for attrs in _ARC.findall(text):
                a = dict(_ATTR.findall(attrs))
                total, item = locs.get(a.get("xlink:from")), locs.get(a.get("xlink:to"))
                if total and item:
                    row = [item, float(a.get("weight", "1"))]
                    if row not in sums.setdefault(total, []):
                        sums[total].append(row)
    labels: dict[str, str] = {}
    wanted = set(sums) | {i for rows in sums.values() for i, _ in rows}
    for n in names:
        if n.endswith(".xml") and re.search(r"lab[-_.]", n.rsplit("/", 1)[-1]):
            text = box.read(n).decode("utf-8", "ignore")
            locs = _locs(text)
            texts = {}
            for attrs, body in _LAB.findall(text):
                a = dict(_ATTR.findall(attrs))
                if a.get("xlink:role", "").endswith("/label"):
                    texts[a.get("xlink:label")] = body.strip()
            for attrs in _LABARC.findall(text):
                a = dict(_ATTR.findall(attrs))
                element = locs.get(a.get("xlink:from"))
                if element in wanted and a.get("xlink:to") in texts:
                    labels.setdefault(element, texts[a["xlink:to"]])
    return {"template": key, "version": version, "source": path.name, "sums": sums, "labels": labels}


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for arg in argv:
        body = build(Path(arg))
        target = OUT / f"{body['template']}.json"
        target.write_text(json.dumps(body, indent=0, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"{target.name}: version {body['version']}, {len(body['sums'])} totals, {len(body['labels'])} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
