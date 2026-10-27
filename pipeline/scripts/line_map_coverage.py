"""Which lines of the row-name map (``bse_intel/line_map.py``, TODO 93, F209) each source covers, and the gaps, over STORED
files. Read only: no network, no AI, no database.

    python -I -X utf8 scripts/line_map_coverage.py [--xbrl DIR] [--screener DIR] [--tijori DIR] [--top 25]
                                                   [--out report.md] [--json report.json]

Each directory is read recursively; a file may be gzipped (the way the R2 copies are: ``*.xml.gz``, ``*.html.gz``,
``*.json.gz``). Download the stored copies first (the maintenance runs keep ``raw/xbrl/``, ``raw/screener/<day>/`` and
``raw/tijori/<day>/``); this script only reads what is on disk.

- XBRL: per template (the file's own taxonomy name; "UNDECLARED" for the older files that name none), the files that carry
  each line's elements, the lines the code reads that NO file of the template carries, the lines a file carries only under
  a name the code does not read (``xbrl_seen`` candidates), and the element names in the files the map does not know at
  all (the top ``--top`` by number of files): those are where a new line may be hiding.
- Screener: the row names of the quarters and profit-loss sections, mapped to lines; the rows no line names.
- Tijori: the same over every section's rows and sub-rows.

This measures the MAP against the files you give it. It does not say how many of a company's figures are right.
"""
from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from bse_intel import line_map as lm  # noqa: E402
from bse_intel.screener_fill import _section_table  # noqa: E402
from bse_intel.xbrl import taxonomy  # noqa: E402

UNDECLARED = "UNDECLARED"
SCREENER_SECTIONS = ("quarters", "profit-loss")


def read_bytes(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def files_in(directory: str | None, suffixes: tuple[str, ...]) -> list[pathlib.Path]:
    if not directory:
        return []
    root = pathlib.Path(directory)
    ends = tuple(suffixes) + tuple(s + ".gz" for s in suffixes)
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name.lower().endswith(ends))


# --- XBRL --------------------------------------------------------------------------------------------------------------

def xbrl_elements(data: bytes) -> tuple[str, set[str]]:
    """(template, the names of every element carrying a number with a unit) of one instance; ("", set()) when it is no XML."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return "", set()
    names = {el.tag.rsplit("}", 1)[-1] for el in root.iter() if el.get("contextRef") and el.get("unitRef")}
    return taxonomy(data) or UNDECLARED, names


def xbrl_report(files: list[tuple[str, str, set[str]]], top: int) -> dict:
    """``files`` is (name, template, element names). Per template: files, the line coverage and the gaps."""
    by_template: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for name, template, names in files:
        by_template[template].append((name, names))
    out = {}
    for template, group in sorted(by_template.items()):
        n = len(group)
        read = {ln.key: sum(1 for _, names in group if names & set(lm.elements(ln.key, template)))
                for ln in lm.LINES if lm.elements(ln.key, template)}
        seen = {ln.key: sum(1 for _, names in group if names & set(lm.seen_only(ln.key, template)))
                for ln in lm.LINES if lm.seen_only(ln.key, template)}
        known = lm.known_elements()
        unmapped = Counter(el for _, names in group for el in names if el not in known)
        out[template] = {
            "files": n,
            "covered": {k: v for k, v in read.items() if v},
            "read_but_in_no_file": sorted(k for k, v in read.items() if not v),
            "seen_not_read": {k: v for k, v in seen.items() if v},
            "unmapped_elements": unmapped.most_common(top),
            "template_sample_in_repo": bool(lm.FIXTURES.get(template)),
            "read_names_missing_from_taxonomy": sorted(
                el for ln in lm.LINES for el in lm.elements(ln.key, template)
                if lm.taxonomy_labels(template) and not lm.in_taxonomy(template, el)),
        }
    return out


# --- screener ----------------------------------------------------------------------------------------------------------

def screener_rows(body: str) -> dict[str, list[str]]:
    """section -> its row labels (a page without the section gives none)."""
    out = {}
    for section in SCREENER_SECTIONS:
        got = _section_table(body, section)
        if got:
            out[section] = list(got[1])
    return out


def screener_report(pages: list[tuple[str, dict[str, list[str]]]], top: int) -> dict:
    known = lm.known_screener_rows()
    line_of = defaultdict(set)
    for ln in lm.LINES:
        for row in ln.screener:
            line_of[row].add(ln.key)
    rows = Counter(row for _, sections in pages for labels in sections.values() for row in set(labels))
    n_sections = Counter(section for _, sections in pages for section in sections)
    return {
        "pages": len(pages),
        "pages_with_section": dict(n_sections),
        "rows": {row: {"pages": c, "lines": sorted(line_of.get(row, ()))} for row, c in rows.most_common()},
        "unmapped_rows": [(row, c) for row, c in rows.most_common() if row not in known][:top],
        "lines_never_seen": sorted(ln.key for ln in lm.LINES if ln.screener and not any(r in rows for r in ln.screener)),
        "lines_without_screener_name": sorted(ln.key for ln in lm.LINES if not ln.screener and not ln.derived_from
                                              and ln.group in ("income", "cost", "profit", "eps", "lender")),
    }


# --- tijori ------------------------------------------------------------------------------------------------------------

def tijori_rows(data: dict) -> dict[str, list[str]]:
    """section id -> its rows' names and their sub-rows' names."""
    tables = data.get("fin_tables_data", data) if isinstance(data, dict) else {}
    out = {}
    for sid, section in (tables or {}).items():
        if not isinstance(section, dict) or not isinstance(section.get("data"), list):
            continue
        names = []
        for row in section["data"]:
            if not isinstance(row, dict):
                continue
            names.append(str(row.get("name") or ""))
            names += [str(s.get("name") or "") for s in row.get("sub_section") or [] if isinstance(s, dict)]
        out[sid] = [n for n in names if n]
    return out


def tijori_report(pages: list[tuple[str, dict[str, list[str]]]], top: int) -> dict:
    known = lm.known_tijori_rows()
    line_of = defaultdict(set)
    for ln in lm.LINES:
        for row in (*ln.tijori, *ln.tijori_lender):
            line_of[row].add(ln.key)
    rows = Counter(row for _, sections in pages for names in sections.values() for row in set(names))
    return {
        "pages": len(pages),
        "rows": {row: {"pages": c, "lines": sorted(line_of.get(row, ()))} for row, c in rows.most_common()},
        "unmapped_rows": [(row, c) for row, c in rows.most_common() if row not in known][:top],
        "lender_revenue_rows_present": sorted(r for r in lm.tijori_rows("revenue", lender=True) if r in rows),
    }


# --- the report --------------------------------------------------------------------------------------------------------

def render(report: dict) -> str:
    lines = ["# Line map coverage (stored files only)", ""]
    x = report.get("xbrl")
    if x is not None:
        lines += ["## XBRL results files", ""]
        if not x:
            lines += ["No file given.", ""]
        for template, r in x.items():
            sample = "a sample file of this template is in the repo" if r["template_sample_in_repo"] else "NO sample file of this template in the repo"
            lines += [f"### {template}: {r['files']} files ({sample})", ""]
            lines.append("Lines the code reads, files carrying each: " + (", ".join(
                f"{k} {v}" for k, v in sorted(r["covered"].items())) or "none"))
            lines.append("")
            lines.append("Lines the code reads that no file carries: " + (", ".join(r["read_but_in_no_file"]) or "none"))
            lines.append("")
            if r["seen_not_read"]:
                lines.append("Carried under a name the code does not read: " + ", ".join(
                    f"{k} {v}" for k, v in sorted(r["seen_not_read"].items())))
                lines.append("")
            if r["unmapped_elements"]:
                lines.append("Elements the map does not know (files): " + ", ".join(f"{n} {c}" for n, c in r["unmapped_elements"]))
                lines.append("")
    s = report.get("screener")
    if s is not None:
        lines += ["## Screener pages", "", f"{s['pages']} pages; sections found: {s['pages_with_section']}", ""]
        lines.append("Rows without a line: " + (", ".join(f"{n} {c}" for n, c in s["unmapped_rows"]) or "none"))
        lines += ["", "Lines with a screener name that no page showed: " + (", ".join(s["lines_never_seen"]) or "none"), "",
                  "Income, cost, profit, EPS and lender lines with no screener name in the map: "
                  + (", ".join(s["lines_without_screener_name"]) or "none"), ""]
    t = report.get("tijori")
    if t is not None:
        lines += ["## Tijori pages", "", f"{t['pages']} pages", ""]
        lines.append("Rows without a line: " + (", ".join(f"{n} {c}" for n, c in t["unmapped_rows"]) or "none"))
        lines += ["", "Lender revenue row names found on a page: " + (", ".join(t["lender_revenue_rows_present"]) or "none"), ""]
    return "\n".join(lines)


def build(xbrl_dir: str | None, screener_dir: str | None, tijori_dir: str | None, top: int = 25) -> dict:
    report: dict = {}
    if xbrl_dir:
        files = []
        for path in files_in(xbrl_dir, (".xml",)):
            template, names = xbrl_elements(read_bytes(path))
            if names:
                files.append((path.name, template, names))
        report["xbrl"] = xbrl_report(files, top)
    if screener_dir:
        pages = [(p.name, screener_rows(read_bytes(p).decode("utf-8", "ignore"))) for p in files_in(screener_dir, (".html",))]
        report["screener"] = screener_report([(n, s) for n, s in pages if s], top)
    if tijori_dir:
        pages = []
        for path in files_in(tijori_dir, (".json",)):
            try:
                pages.append((path.name, tijori_rows(json.loads(read_bytes(path)))))
            except ValueError:
                continue
        report["tijori"] = tijori_report([(n, s) for n, s in pages if s], top)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--xbrl")
    ap.add_argument("--screener")
    ap.add_argument("--tijori")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    if not (args.xbrl or args.screener or args.tijori):
        ap.error("give at least one of --xbrl, --screener, --tijori")
    report = build(args.xbrl, args.screener, args.tijori, args.top)
    text = render(report)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
