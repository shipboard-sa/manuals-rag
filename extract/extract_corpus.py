"""
Purpose: Extract the owner's boat-manual library (PDFs + a few text docs) into a page-numbered,
    greppable UTF-8 text corpus, with an incremental manifest.
Version: v3 (2026-10-07) - v3: OCR'd files (ocr_corpus.py) are never re-extracted while their source is unchanged - a re-run used to reset them to needs-ocr and drop them from the index. v2 (2026-10-02) - v2: skips 'Previous versions' folders (superseded revisions; their corpus text is pruned). v1 (2026-09-30)
Scope: STANDALONE UTILITY today; the ingest stage (text extraction) of manuals-rag once
    built (PRODUCTION-candidate).
Architecture: manuals-rag stage one. Reads the Manuals folder (READ-ONLY, never modified),
    writes corpus/<relative path>.txt with a marker line before every page
    ("===== [Electrical/Victron/foo.pdf] page 12 / 48 =====") plus corpus/_manifest.json.
    search.py greps the corpus; a later chunk/embed stage will read the same files.
    PDF text via PyMuPDF, run in a child worker process so a pathological PDF can be
    killed on timeout without stopping the run. Host-independent (laptop or Ship's PC).
Invocation: .venv\\Scripts\\python extract\\extract_corpus.py
        [--root D:\\Documents\\sailboat\\Manuals] [--out <manuals-rag>\\corpus]
        [--force] [--limit N] [--timeout 180]
    Run from anywhere; needs the project venv (pymupdf, see requirements.txt).
    Re-runs skip files whose size+mtime are unchanged; --force redoes all except OCR'd files (kept while unchanged).
"""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import multiprocessing as mp
import os
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
DEFAULT_ROOT = Path(r"D:\Documents\sailboat\Manuals")
DEFAULT_OUT = PROJECT / "corpus"
MANIFEST_NAME = "_manifest.json"
SCHEMA = 1

# A page with fewer than this many non-whitespace chars counts as "no text".
LOW_TEXT_CHARS = 25
# File is needs-ocr if at least this share of its pages have no text.
NEEDS_OCR_SHARE = 0.8

PDF_EXT = {".pdf"}
COPY_EXT = {".txt", ".md", ".csv", ".cfg"}
DOCX_EXT = {".docx"}
HTML_EXT = {".html", ".htm"}


def long_path(p: Path) -> str:
    """Windows MAX_PATH guard: use the \\\\?\\ prefix for long absolute paths."""
    s = str(p.resolve()) if not str(p).startswith("\\\\?\\") else str(p)
    if os.name == "nt" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + s
    return s


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(long_path(path), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_atomic(dest: Path, text: str) -> None:
    os.makedirs(long_path(dest.parent), exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with open(long_path(tmp), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(long_path(tmp), long_path(dest))


def marker(rel: str, page: int | None = None, total: int | None = None,
           kind: str | None = None) -> str:
    if page is not None:
        return f"===== [{rel}] page {page} / {total} ====="
    return f"===== [{rel}] ({kind}) ====="


# ---------------------------------------------------------------- PDF (worker side)

def extract_pdf(src: str, dest: str, rel: str) -> dict:
    """Runs in the worker process. Writes dest, returns manifest fields."""
    import pymupdf  # imported in worker only

    out: dict = {}
    try:
        doc = pymupdf.open(src)
    except Exception as e:  # broken / not a PDF
        msg = str(e).replace(src, "<file>")
        return {"status": "error", "message": f"open failed: {type(e).__name__}: {msg}"[:300]}
    try:
        if doc.needs_pass and not doc.authenticate(""):
            return {"status": "encrypted", "message": "password required",
                    "pages": doc.page_count}
        n = doc.page_count
        parts = []
        chars = 0
        low_pages = []
        page_errors = 0
        for i in range(n):
            try:
                txt = doc[i].get_text("text", sort=False)
            except Exception:
                txt = ""
                page_errors += 1
            txt = txt.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
            nonws = len(re.sub(r"\s+", "", txt))
            chars += nonws
            if nonws < LOW_TEXT_CHARS:
                low_pages.append(i + 1)
            parts.append(marker(rel, i + 1, n))
            parts.append(txt.rstrip("\n"))
            parts.append("")
        write_atomic(Path(dest), "\n".join(parts) + "\n")
        out.update(pages=n, chars=chars, low_text_pages=len(low_pages))
        if n == 0:
            out.update(status="error", message="zero pages")
        elif len(low_pages) >= NEEDS_OCR_SHARE * n:
            out.update(status="needs-ocr",
                       message=f"{len(low_pages)}/{n} pages with <{LOW_TEXT_CHARS} chars")
        else:
            out["status"] = "ok"
            if low_pages:
                # partially scanned files stay 'ok' but record which pages are empty
                out["low_text_page_list"] = compress_ranges(low_pages)
        if page_errors:
            out["message"] = f"{page_errors} page(s) failed to extract"
        return out
    finally:
        doc.close()


def compress_ranges(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for x in nums:
        if start is None:
            start = prev = x
        elif x == prev + 1:
            prev = x
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = x
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(out)


def worker_loop(conn) -> None:
    while True:
        job = conn.recv()
        if job is None:
            return
        try:
            res = extract_pdf(*job)
        except Exception as e:
            res = {"status": "error", "message": f"{type(e).__name__}: {e}"[:300]}
        conn.send(res)


class Worker:
    """One child process for PDF extraction; killed and restarted on timeout."""

    def __init__(self):
        self.proc = None
        self.conn = None

    def start(self):
        parent, child = mp.Pipe()
        self.proc = mp.Process(target=worker_loop, args=(child,), daemon=True)
        self.proc.start()
        self.conn = parent

    def run(self, job, timeout: float) -> dict:
        if self.proc is None or not self.proc.is_alive():
            self.start()
        self.conn.send(job)
        if self.conn.poll(timeout):
            try:
                return self.conn.recv()
            except EOFError:
                self.proc = None
                return {"status": "error", "message": "worker crashed"}
        self.proc.kill()
        self.proc.join()
        self.proc = None
        return {"status": "error", "message": f"timeout after {timeout:.0f}s"}

    def stop(self):
        if self.proc is not None and self.proc.is_alive():
            self.conn.send(None)
            self.proc.join(5)


# ---------------------------------------------------------------- non-PDF (main side)

def read_text_file(src: Path) -> str:
    raw = open(long_path(src), "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def docx_text(src: Path) -> str:
    with zipfile.ZipFile(long_path(src)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    lines = []
    for p in paras:
        runs = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, flags=re.S)
        lines.append(html_unescape("".join(runs)))
    return "\n".join(lines)


def html_unescape(s: str) -> str:
    import html
    return html.unescape(s)


class _HTMLText(html.parser.HTMLParser):
    SKIP = {"script", "style", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_text(src: Path) -> str:
    p = _HTMLText()
    p.feed(read_text_file(src))
    return re.sub(r"\n\s*\n+", "\n\n", "".join(p.out))


def extract_other(src: Path, dest: Path, rel: str, ext: str) -> dict:
    try:
        if ext in COPY_EXT:
            body, kind = read_text_file(src), "text file"
        elif ext in DOCX_EXT:
            body, kind = docx_text(src), "docx text"
        else:
            body, kind = html_text(src), "html text"
    except Exception as e:
        return {"status": "error", "message": f"{type(e).__name__}: {e}"[:300]}
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    write_atomic(dest, marker(rel, kind=kind) + "\n" + body.rstrip("\n") + "\n")
    chars = len(re.sub(r"\s+", "", body))
    return {"status": "ok" if chars else "empty", "pages": None, "chars": chars}


# ---------------------------------------------------------------- driver

def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema") == SCHEMA:
                return data
        except Exception:
            pass
    return {"schema": SCHEMA, "files": {}}


def save_manifest(path: Path, data: dict) -> None:
    write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="manual library (read-only)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="corpus output folder")
    ap.add_argument("--force", action="store_true", help="re-extract everything")
    ap.add_argument("--limit", type=int, default=0, help="process at most N files needing work")
    ap.add_argument("--timeout", type=float, default=180, help="per-PDF timeout, seconds")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    root, out = args.root.resolve(), args.out.resolve()
    if not root.is_dir():
        print(f"root not found: {root}")
        return 2
    if out == root or root in out.parents:
        print("refusing: --out must not be inside --root (the library is read-only)")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / MANIFEST_NAME
    manifest = load_manifest(mpath)
    files = manifest["files"]

    import pymupdf
    pdf_extractor = f"pymupdf {pymupdf.__version__}"
    other_extractor = f"extract_corpus v1 builtin (py {sys.version.split()[0]})"

    sources = sorted((p for p in root.rglob("*") if p.is_file()
                     and "Previous versions" not in p.relative_to(root).parts),  # superseded copies (the owner 10-02)
                     key=lambda p: p.relative_to(root).as_posix().lower())
    seen = set()
    todo = []
    for p in sources:
        rel = p.relative_to(root).as_posix()
        seen.add(rel)
        ext = p.suffix.lower()
        st = p.stat()
        if p.name.startswith("._"):
            files[rel] = {"size": st.st_size, "mtime": int(st.st_mtime),
                          "status": "skipped", "message": "macOS AppleDouble metadata, not a document",
                          "extractor": None}
            continue
        if ext in PDF_EXT:
            extractor = pdf_extractor
        elif ext in COPY_EXT | DOCX_EXT | HTML_EXT:
            extractor = other_extractor
        else:
            files[rel] = {"size": st.st_size, "mtime": int(st.st_mtime),
                          "status": "skipped", "message": f"unsupported type '{ext or p.name}'",
                          "extractor": None}
            continue
        prev = files.get(rel)
        # an OCR'd file (ocr_corpus.py: status ok, ocr true, its own extractor name) is kept while its source is
        # unchanged - even with --force; re-extracting it would write empty text and reset it to needs-ocr (v3)
        if (prev and prev.get("ocr") and prev.get("size") == st.st_size
                and prev.get("mtime") == int(st.st_mtime)):
            continue
        if (not args.force and prev and prev.get("size") == st.st_size
                and prev.get("mtime") == int(st.st_mtime)
                and prev.get("extractor") == extractor
                and prev.get("status") not in (None, "skipped")):
            continue
        todo.append((p, rel, ext, extractor, st))

    # prune entries (and derived text) whose source is gone
    for rel in [r for r in files if r not in seen]:
        dest = out / (rel + ".txt")
        if dest.exists():
            os.remove(long_path(dest))
        del files[rel]

    if args.limit:
        todo = todo[: args.limit]
    print(f"library: {root}\ncorpus:  {out}\n{len(sources)} files found, {len(todo)} to process")

    worker = Worker()
    t0 = time.time()
    try:
        for i, (p, rel, ext, extractor, st) in enumerate(todo, 1):
            dest = out / (rel + ".txt")
            t1 = time.time()
            if ext in PDF_EXT:
                res = worker.run((long_path(p), str(dest), rel), args.timeout)
            else:
                res = extract_other(p, dest, rel, ext)
            if res.get("status") in ("error", "encrypted") and dest.exists():
                os.remove(long_path(dest))  # no stale text for a file we couldn't read
            entry = {"size": st.st_size, "mtime": int(st.st_mtime), "sha1": sha1_of(p),
                     "extractor": extractor, "pages": res.get("pages"),
                     "chars": res.get("chars"), "status": res["status"],
                     "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "seconds": round(time.time() - t1, 2)}
            for k in ("low_text_pages", "low_text_page_list", "message"):
                if res.get(k):
                    entry[k] = res[k]
            files[rel] = entry
            print(f"[{i}/{len(todo)}] {entry['status']:<9} {entry['pages'] or '-':>5}p "
                  f"{entry['seconds']:6.1f}s  {rel}", flush=True)
            if i % 25 == 0:
                save_manifest(mpath, manifest)
    finally:
        worker.stop()
        manifest["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        manifest["root"] = str(root)
        manifest["files"] = dict(sorted(files.items(), key=lambda kv: kv[0].lower()))
        save_manifest(mpath, manifest)

    # summary over the whole manifest, not just this run
    counts: dict[str, int] = {}
    for e in files.values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    size = sum(f.stat().st_size for f in out.rglob("*.txt"))
    print(f"\nprocessed {len(todo)} file(s) in {time.time() - t0:.1f}s")
    print("manifest totals: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"corpus text: {size / 1e6:.1f} MB in {out}")
    for status in ("needs-ocr", "encrypted", "error"):
        bad = [r for r, e in files.items() if e["status"] == status]
        if bad:
            print(f"\n{status} ({len(bad)}):")
            for r in bad:
                print(f"  {r}  {files[r].get('message', '')}")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
