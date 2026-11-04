"""
Purpose: Grep the manuals-rag text corpus and print hits citable as file + page.
Version: v1 (2026-09-30)
Scope: STANDALONE UTILITY today; the lookup tool Claude (and later the manuals-rag
    service) uses against the extracted corpus.
Architecture: manuals-rag stage one, reader side. Reads corpus/**/*.txt written by
    extract_corpus.py, tracks the "===== [file] page N / M =====" marker lines, and
    prints each hit as "file p.N: line" with optional context. Read-only; stdlib only.
Invocation: .venv\\Scripts\\python extract\\search.py "EMGSW" [--context 2]
        [--path Victron] [--regex] [--case] [--max 200] [--corpus <dir>]
    Plain (non-venv) python works too. Default match is literal, case-insensitive.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "corpus"
MARK = re.compile(r"^===== \[(?P<file>.+?)\] (?:page (?P<page>\d+) / \d+|\((?P<kind>[^)]*)\)) =====$")


def main() -> int:
    ap = argparse.ArgumentParser(description="Search the manuals text corpus.")
    ap.add_argument("pattern")
    ap.add_argument("--context", "-C", type=int, default=0, help="lines of context")
    ap.add_argument("--path", "-p", action="append", default=[],
                    help="only files whose path contains this (case-insensitive; repeatable, AND)")
    ap.add_argument("--regex", "-E", action="store_true", help="treat pattern as a regex")
    ap.add_argument("--case", action="store_true", help="case-sensitive")
    ap.add_argument("--max", type=int, default=200, help="stop after N hits (0 = no limit)")
    ap.add_argument("--files", "-l", action="store_true", help="list file + hit pages only")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    flags = 0 if a.case else re.IGNORECASE
    rx = re.compile(a.pattern if a.regex else re.escape(a.pattern), flags)
    filters = [f.lower() for f in a.path]
    hits = 0
    for txt in sorted(a.corpus.rglob("*.txt"), key=lambda p: str(p).lower()):
        rel = txt.relative_to(a.corpus).as_posix()
        if any(f not in rel.lower() for f in filters):
            continue
        lines = txt.read_text(encoding="utf-8", errors="replace").split("\n")
        page = "-"
        pages_of = []  # page label per line
        for ln in lines:
            m = MARK.match(ln)
            if m:
                page = m.group("page") or "-"
            pages_of.append(page)
        src = rel[:-4]
        file_pages = []
        last_printed = -1
        for i, ln in enumerate(lines):
            if MARK.match(ln) or not rx.search(ln):
                continue
            hits += 1
            if a.files:
                if pages_of[i] not in file_pages:
                    file_pages.append(pages_of[i])
            else:
                lo, hi = max(0, i - a.context), min(len(lines), i + a.context + 1)
                if a.context and lo > last_printed + 1 and last_printed >= 0:
                    print("--")
                for j in range(max(lo, last_printed + 1), hi):
                    if MARK.match(lines[j]):
                        continue
                    sep = ":" if j == i else "-"
                    print(f"{src} p.{pages_of[j]}{sep} {lines[j].rstrip()}")
                last_printed = hi - 1
            if a.max and hits >= a.max:
                break
        if a.files and file_pages:
            print(f"{src}  pages {', '.join(file_pages)}")
        elif a.context and last_printed >= 0:
            print("--")
        if a.max and hits >= a.max:
            print(f"[stopped at --max {a.max}]")
            break
    print(f"[{hits} hit(s)]", file=sys.stderr)
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
