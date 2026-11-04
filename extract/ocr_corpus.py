"""
Purpose: OCR the image-only manuals (manifest status "needs-ocr") into the corpus, so they become searchable and
  answerable - e.g. the 454-page Yanmar operation manual and the 3JH40-4JH110 OPM (CHECKPOINT open item "OCR").
Version: v1 (2026-10-03)
Scope: PRODUCTION-candidate - manuals-rag stage one (extension of extract_corpus.py); run on the Ship's PC.
Architecture: manuals-rag/extract. PyMuPDF page.get_textpage_ocr() driving Tesseract 5 (installed at
  C:\\Program Files\\Tesseract-OCR, tessdata beside it). Writes corpus/<rel>.txt with the same page markers as
  extract_corpus.py and sets the manifest entry to status "ok" + "ocr": true. Skips _ARCHIVE_prev-boat/ (out of the
  LLM's scope, owner, Oct 2026). Reads the manuals read-only.
Invocation: .venv\\Scripts\\python extract\\ocr_corpus.py --root E:\\boat\\Manuals [--dpi 300] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pymupdf

PROJECT = Path(__file__).resolve().parent.parent
CORPUS = PROJECT / "corpus"
TESSDATA = r"C:\Program Files\Tesseract-OCR\tessdata"
SKIP = ("_ARCHIVE_prev-boat/",)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="manual library (read-only)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.environ.setdefault("TESSDATA_PREFIX", TESSDATA)
    mpath = CORPUS / "_manifest.json"
    man = json.loads(mpath.read_text(encoding="utf-8"))
    todo = [rel for rel, e in sorted(man["files"].items()) if e.get("status") == "needs-ocr" and not rel.startswith(SKIP)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} image-only manuals to OCR at {a.dpi} dpi")
    for i, rel in enumerate(todo, 1):
        t0 = time.time()
        doc = pymupdf.open(a.root / rel)
        parts, chars = [], 0
        for n, page in enumerate(doc, 1):
            tp = page.get_textpage_ocr(language="eng", dpi=a.dpi, full=True, tessdata=TESSDATA)
            text = page.get_text(textpage=tp).strip()
            chars += len(text)
            parts.append(f"===== [{rel}] page {n} / {doc.page_count} =====\n{text}\n")
        dest = CORPUS / (rel + ".txt")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text("\n".join(parts), encoding="utf-8", newline="\n")
        tmp.replace(dest)
        e = man["files"][rel]
        e.update({"status": "ok", "ocr": True, "chars": chars, "extractor": f"tesseract-ocr {a.dpi}dpi via pymupdf",
                  "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - t0, 1)})
        mpath.write_text(json.dumps(man, indent=1), encoding="utf-8")  # after every file - resumable
        print(f"[{i}/{len(todo)}] {doc.page_count:4d}p {chars:8d} chars {time.time() - t0:6.0f}s  {rel}", flush=True)


if __name__ == "__main__":
    main()
