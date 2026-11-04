<!--
Purpose: The manual library, the duplicates folder, the extraction + OCR pipeline, the corpus format, the manifest
  schema and search.py - everything in stage one.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass; folds in extract/README.md (kept as the
  quick card) and adds OCR (repo-only ocr_corpus.py v1) and the extract/OCR interaction.
Scope: PRODUCTION-candidate - documentation for manuals-rag stage one.
Architecture: code/manuals-rag/wiki/. Writers: extract_corpus.py v2, ocr_corpus.py v1. Readers: search.py v1,
  rag/ingest.py, recall.py (manuals store).
Invocation: n/a (reference doc)
-->

# Corpus and extraction (stage one)

## The manual library

- **Master:** `D:\Documents\sailboat\Manuals\` on the laptop (Laptop-to-ShipsPC-Checklist A5: master stays on the
  laptop, the Ship's PC reads a mirror). Ship's PC copy: `E:\boat\Manuals` (USB copy 2026-10-03, 369 files,
  1,499,817,064 bytes). No automatic sync yet.
- the owner drops files in by hand, organised by system folder (`Electrical/`, `Engine/`, `Your Boat Model/`, `Victron/`,
  `Yacht Devices/` ...). Loose files also sit at the root (checklists, Captain's Locker guides).
- **`_ARCHIVE_prev-boat/`** - manuals of the previous boat (the Beneteau lost in Hurricane Beryl, 2024). Extracted
  and greppable, but excluded from the LLM index and from OCR (owner, Oct 2026).
- **`old/` folders** (any depth, e.g. `Electrical/Victron/old/`, `Electronics/old/`) - superseded manuals; extracted,
  excluded from the LLM index (owner, Oct 2026, "old is out").
- **`Previous versions/` folders** - superseded revisions (the owner 10-02, e.g. `Electrical/Batteries/Previous versions/`
  holds SSM manual Rev 1024); not extracted at all, and their corpus text is pruned.
- mx-inv also links into this folder (Settings "Manuals folder" / `MXINV_MANUALS_ROOT`).

## The duplicates folder

On 2026-09-30, 135 byte-identical duplicates (same SHA-1) were moved from `Manuals\` to
**`D:\Documents\sailboat\Manuals_DUPLICATES\`**, keeping their relative paths. `MOVED.csv` columns:
`moved_from (under Manuals)`, `identical_keeper (still in Manuals)`, `sha1`. One notable case: the misnamed
`Engine/EB 442 Wheel pilot Installation 426.pdf` was really the Yanmar JH-CR manual. **the owner deletes the folder when
happy** (still present 2026-10-07). New duplicates can appear; the manifest `sha1` identifies them. Exact
duplicates across *other* folders (Weather <-> Manuals/Weather, YD manuals under `Refit/Your Boat Model/Yacht Devices/`,
Max-Prop x4) were left alone (recall SOURCE-OF-TRUTH rulings).

## Extraction - extract/extract_corpus.py (v2)

```
.venv\Scripts\python extract\extract_corpus.py [--root D:\Documents\sailboat\Manuals] [--out <project>\corpus]
                                               [--force] [--limit N] [--timeout 180]
```

1. Walk `--root` recursively (skip `Previous versions/`), sorted by lower-case relative path. Refuses if `--out` is
   inside `--root` (the library is never written).
2. Classify each file:
   - `._*` (macOS AppleDouble) -> `skipped`.
   - `.pdf` -> PyMuPDF, extractor tag `pymupdf <version>`.
   - `.docx` (body text from `word/document.xml`), `.html/.htm` (tags stripped, script/style/head skipped),
     `.txt .md .csv .cfg` (copied; utf-8-sig -> cp1252 -> latin-1) -> extractor tag
     `extract_corpus v1 builtin (py <version>)`.
   - anything else (`.zip .xlsx .pptx`, images, `.bin` ...) -> `skipped`, message `unsupported type`.
3. **Skip-if-unchanged:** same size + mtime + extractor tag + previous status not skipped. `--force` redoes all.
4. Sources that disappeared: their `.txt` and manifest entry are deleted.
5. Each PDF runs in a **child worker process** (multiprocessing pipe); a PDF that hangs past `--timeout` seconds is
   killed and recorded `error`, and the run continues. Long Windows paths get the `\\?\` prefix.
6. Per PDF page: `get_text("text")`, CR/NUL normalised; a page with **< 25 non-whitespace chars** is "low text".
   Status `needs-ocr` if **>= 80 %** of pages are low text; `error` for zero pages or open failure; `encrypted` if
   a password is required (empty password tried). Error / encrypted files get no `.txt`.
7. Manifest saved every 25 files and at the end; summary printed over the whole manifest.

Run history: first run 2026-09-30 - 506 files, 416 ok, 27 needs-ocr, 63 skipped, 10,715 PDF pages, 20.6 MB text,
69 s. After the duplicate move: 371 files. Laptop manifest 2026-10-06 17:18: **372 files - 288 ok, 64 skipped,
20 needs-ocr** (49 under `_ARCHIVE_prev-boat/`).

## Corpus format

One UTF-8 (LF) file per source: `corpus/<relative source path>.txt` (e.g. `corpus/Engine/JH-CR_OPM.pdf.txt`).
Before every PDF page a marker line:

```
===== [Electrical/Victron/foo.pdf] page 12 / 48 =====
```

Non-PDF sources get one marker `===== [<rel>] (<kind>) =====`. Page numbers are **PDF page indexes** (1 = first
sheet), what a viewer's "go to page" uses - usually not the printed page number (JH-CR OPM PDF p.66 = printed
p.58). Cite as "PDF p.N". Tables come out in drawing order (often one cell per line).

The corpus is text derived from copyrighted manuals: **local only, git-ignored, never committed, pushed, published
or shared off the boat.**

## Manifest - corpus/_manifest.json

`{"schema": 1, "generated": "<local ISO time>", "root": "<library path>", "files": {"<rel path>": {...}}}`, keys
sorted case-insensitively.

| Field | Meaning |
|---|---|
| `size`, `mtime` | Source bytes and mtime (epoch s) - the skip key |
| `sha1` | SHA-1 of the source at extraction (duplicate detection; the index's change key) |
| `extractor` | `pymupdf 1.28.2`, `extract_corpus v1 builtin (py 3.14.7)`, or after OCR `tesseract-ocr 300dpi via pymupdf`; null if skipped |
| `pages` | PDF page count (null for non-PDF) |
| `chars` | Non-whitespace characters extracted (OCR: total characters) |
| `status` | `ok`, `needs-ocr`, `encrypted`, `error`, `empty`, `skipped` |
| `low_text_pages`, `low_text_page_list` | Count / ranges (`1-3,17`) of pages under 25 chars |
| `message` | Reason for error / needs-ocr / skipped |
| `extracted_at`, `seconds` | When and how long |
| `ocr` | `true` when the text came from `ocr_corpus.py` |

`corpus/_last_run.log` is the console log of the first full run (09-30).

## OCR - extract/ocr_corpus.py (v1, repo / Ship's PC only)

```
.venv\Scripts\python extract\ocr_corpus.py --root E:\boat\Manuals [--dpi 300] [--limit N]
```

For every manifest entry with `status: needs-ocr` outside `_ARCHIVE_prev-boat/`: render each page and OCR it with
Tesseract 5 through PyMuPDF `get_textpage_ocr(language="eng", dpi=300, full=True)`, tessdata
`C:\Program Files\Tesseract-OCR\tessdata`; write the `.txt` with the same page markers; set the entry to
`status: ok`, `ocr: true`, new `chars` / `extractor` / `extracted_at` / `seconds`; save the manifest after every
file (resumable). Done 2026-10-03 for the 16 in-scope image-only manuals, including the 454-page
`Your Boat Model/Yanmar Operation Manual 49961-201372.pdf` and the 204-page `Your Boat Model/0AJHC-M0001E_2025.02.pdf`
(3JH40-4JH110 OPM). Schematic pages OCR to noise (expected).

**OCR'd files are kept (extract_corpus.py v3, 2026-10-07, repo commit 3626dd5):** an entry with `ocr: true` whose
source size + mtime are unchanged is skipped, even with `--force`. Before v3 the extractor-tag mismatch made the next
run re-extract it with PyMuPDF, write empty text, reset it to `needs-ocr`, and `ingest.py` then dropped it. A changed
source file is re-extracted normally and needs `ocr_corpus.py` again.

## Search - extract/search.py (v1)

```
python extract\search.py "EMGSW"
python extract\search.py "emergency stop" --context 2 --path yanmar
python extract\search.py "relay.*alarm" --regex --path victron --path multiplus
python extract\search.py "K67" --files            # file + hit pages only
```

Stdlib only (no venv needed). Literal, case-insensitive by default; `--regex`/`-E`, `--case`, `--path`/`-p`
(substring of the relative path, repeatable, all must match), `--context`/`-C N`, `--max N` hit lines (default 200,
0 = none), `--files`/`-l`, `--corpus DIR`. Files are walked in case-insensitive path order.

Output: `<file> p.<N>: <line>` (context lines use `-`, groups separated by `--`); with `--files`:
`<file>  pages 3, 5, 9`. On stdout, `[stopped at --max N]` when the cap is hit; on stderr `[N hit(s)]`. Exit 0 if
anything matched, 1 if nothing. Plain `grep -rn` on `corpus\` works too (look up to the nearest `=====` line for the
page).
