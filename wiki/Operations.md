<!--
Purpose: Running manuals-rag day to day - search, adding manuals, refreshing corpus and index, starting / checking
  the service, testing, failure modes and gotchas.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass.
Scope: PRODUCTION-candidate - documentation for manuals-rag.
Architecture: code/manuals-rag/wiki/. Host setup is in LLM-Host.md; formats in Corpus-and-Extraction.md and
  Index-and-QA-Service.md.
Invocation: n/a (reference doc)
-->

# Operations

## Search the manuals (laptop, any time)

```
python D:\Documents\sailboat\code\manuals-rag\extract\search.py "raw water pump" --path yanmar -C 2
python D:\Documents\sailboat\code\recall\recall.py "raw water pump" --store manuals
```

Cite as `<manual> PDF p.N`. The laptop corpus has no OCR, so the image-only manuals (Yanmar 454-page operation
manual, 0AJHC OPM, Hylas plumbing / electrical diagrams, Engel fridge) return nothing here - open the PDF.

## Add new manuals

1. the owner drops the files into `D:\Documents\sailboat\Manuals\<system folder>\` (the master). Superseded copies go in
   a `Previous versions\` subfolder beside the current file (the owner 10-02), or an `old\` folder (excluded from the
   LLM, still greppable). Previous-boat material goes under `_ARCHIVE_prev-boat\`.
2. Laptop: `code\manuals-rag\.venv\Scripts\python code\manuals-rag\extract\extract_corpus.py` (incremental;
   prints any new `needs-ocr` files).
3. Ship's PC: copy the new files to `E:\boat\Manuals` (no automatic sync yet), then in
   `E:\boat\manuals-rag`:
   ```
   .venv\Scripts\python extract\extract_corpus.py --root E:\boat\Manuals
   .venv\Scripts\python extract\ocr_corpus.py --root E:\boat\Manuals      # ALWAYS after extract (see gotcha 1)
   .venv\Scripts\python rag\ingest.py
   ```
   No service restart needed - the persistent connection sees the updated index.
4. Duplicates: check the new file's `sha1` in the manifest against existing entries; byte-identical copies go to
   `Manuals_DUPLICATES\` with a `MOVED.csv` line (the 09-30 convention).

## Start / stop / check the service (Ship's PC)

- Starts at logon (Task Scheduler "boat manuals"); manual start = desktop icon "Boat Manuals"; stop = close its
  console window. The .bat refuses to start a second copy if something already listens on :8200.
- Ollama must be running (tray app) with the GPU env vars, or answers fall back to CPU (100-125 s to first word).
- Health: `http://192.168.1.113:8200/api/health` (counts, model) and the Pi landing page tile "Boat manuals"
  (probe `/probe/manuals`).
- Retrieval without the LLM: `http://192.168.1.113:8200/api/search?q=impeller` - fast check that the index and
  the embedding model work.
- Timing: `.venv\Scripts\python bench\ask_timing.py "question"` prints time to sources, first word, total, sources.

## Testing

There is **no automated test suite** in manuals-rag. Verification used so far:
- extraction: the run summary (status counts, needs-ocr list) and `search.py` spot checks;
- service: `bench/ask_timing.py` answers checked by hand against the cited pages (10-03: Fireboy 175 F p.4,
  watermaker pickling, Yanmar impeller interval 1,000 h);
- model choice: `bench/bench_models.py qwen3:4b qwen3:8b` (prompt and generation tokens/s on a fixed impeller
  question over ~6,000 corpus characters);
- the spec's acceptance pass (offline query with the internet cut, citation spot-check, host health under a query
  burst) was written for the Pi design and has not been run on the Ship's PC (Roadmap).

## Failure modes and recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| Landing tile red / page does not load | Ship's PC down, not signed in (task runs at logon), console closed, firewall rule missing or network profile Public | sign in / icon; check `netstat -ano | findstr :8200`; firewall rule + Private profile |
| Answer takes ~2 min, CPU at 100 %, GPU idle | Ollama started without the user env vars (e.g. launched from an elevated shell) | quit tray Ollama, restart Explorer, relaunch; check `server.log` for Vulkan + 37/37 layers |
| First answer after a reboot ~100 s | both models load cold (keep-alive 30 min after that) | expected |
| `/api/ask` streams sources then stops, no `done` | Ollama crashed or the model is missing | `ollama list`; pull `qwen3:8b` |
| Rambling, very long answers | started without `MANUALS_LLM` (old default `qwen3:4b`) | `git pull` (app.py v4 defaults to 8b) or start via `run-manuals.bat` |
| A manual stopped being answerable after a corpus refresh | its source changed (re-extracted, needs OCR again) - or a pre-v3 extractor reset an OCR'd file | run `ocr_corpus.py`, then `ingest.py` |
| `/api/health` shows 0 documents | `index\manuals.db` missing (an empty one was created) | `rag\ingest.py --force` |
| Old-boat or superseded manual cited | excluded only by path - a file misplaced outside `_ARCHIVE_prev-boat/` / `old/` | move the file, rerun extract + ingest |
| Procedure answer mixes in unrelated steps | page-level chunks; the procedure spans pages | fixed in v4 by neighbor-page expansion; open the cited pages if still wrong |

## Gotchas

1. **extract after OCR undoes OCR** (extractor-tag mismatch) - always rerun `ocr_corpus.py` after
   `extract_corpus.py`, before `ingest.py`. Derived from the code (Corpus-and-Extraction).
2. Page numbers everywhere are **PDF page indexes**, not printed page numbers.
3. Port 8200 is also the rules engine's port on the Pi (127.0.0.1 there) - different host.
4. The laptop folder is not the repo. Code edits belong in `hutchel/manuals-rag` (Ship's PC clone); the laptop has
   only stage one, and its `CHECKPOINT.md` is older than the repo's.
5. `corpus/` and `index/` must never be committed or shared (copyrighted source text).
6. Plain `ollama` in a terminal opens a launcher offering cloud models - pull models by name instead.
