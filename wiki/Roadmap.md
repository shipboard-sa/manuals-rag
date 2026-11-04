<!--
Purpose: manuals-rag open items only.
Version: v2 (2026-11-02) - v2: Ship's PC back, v4 deployed; RMA items closed, neighbor-page done, Brave Search done.
  v1 (2026-10-07): created in the rebuild-from-spec wiki pass.
Scope: PRODUCTION-candidate - documentation for manuals-rag.
Architecture: code/manuals-rag/wiki/. Remove an item when done (fold the result into the other pages).
Invocation: n/a (reference doc)
-->

# Roadmap (open items only)

## Service

1. **Acceptance pass** on the Ship's PC: an offline query with the internet cut, a citation spot-check, and host
   health during a query burst (spec work-breakdown step 7, never run for this host).

## Repo and docs hygiene

2. **Reconcile the two copies.** The laptop folder lacks `rag/`, `bench/`, `extract/ocr_corpus.py`,
   `run-manuals.bat`, `requirements.txt` v2, `.gitignore` (index rule). Which copy is the
   working tree going forward (clone the repo onto the laptop vs keep stage one only) - **ask Lee**.
3. **Move this wiki into `hutchel/manuals-rag`** (and point its CHECKPOINT at it).

## Pipeline

4. **Library sync laptop -> Ship's PC** - manual copy today; the planned Syncthing mirror is parked until the GL
   router work (memory `backup-infrastructure.md`). The Ship's PC copy misses manuals added since 10-03 (e.g. the
   10-06 Refrigeration additions).
5. **OCR on the laptop corpus** (Tesseract not installed there) or copy the OCR'd `.txt` files back, so recall's
   `manuals` store can grep the Yanmar books. 66+ "ok" PDFs also have some empty pages (`low_text_page_list`).
6. **Missing manual:** the Wakespeed WS500 manual is not in the library (MORNING-REPORT 10-01).
7. **Duplicates folder** - `Manuals_DUPLICATES\` awaits the owner's delete.
8. `.xlsx`, `.pptx`, `.zip` contents are not extracted (e.g. `Inventroy.xlsx`, `Sailboat_Systems_Spreadsheet.xlsx`
   at the library root).

## Not decided

9. Whether a manuals chat panel is ever folded into mx-inv's frontend (out of scope for v1, spec s.2).
10. Where the service lives long-term: D-077 moves mx-inv onto the Pi stack after cut-over; manuals stays on the
    Ship's PC per D-054 - no record says otherwise.
