<!--
Purpose: Start-here page of the manuals-rag engineering wiki - what it is, current status, where both copies live,
  page index.
Version: v1 (2026-10-07) - v1: wiki created (rebuild-from-spec pass); folds in CHECKPOINT.md, design/MANUALS_RAG_SPEC.md,
  extract/README.md, the hutchel/manuals-rag repo (read-only via gh) and Ship's Automation docs/Ships-PC-Setup.md.
Scope: PRODUCTION-candidate - documentation for manuals-rag (the Q&A service runs on the Ship's PC, D-054).
Architecture: code/manuals-rag/wiki/. The code repo is the private hutchel/manuals-rag
  (Ship's PC clone at E:\boat\manuals-rag).
Invocation: n/a (reference doc)
-->

# manuals-rag - engineering wiki

**manuals-rag** answers questions from the boat's own equipment manuals, entirely offline. Three stages:

1. **Extract** - the manual library (`Manuals\`, ~370 files) becomes a page-numbered plain-text corpus;
   `extract/search.py` greps it and cites **file + PDF page**. Claude uses this every day (it is recall's
   `manuals` store).
2. **Index** - the corpus is chunked, embedded locally (nomic-embed-text via Ollama) and stored in one SQLite file
   with sqlite-vec + FTS5.
3. **Ask** - a FastAPI service on the Ship's PC (`:8200`, chat page + API) retrieves the best excerpts and has a local
   LLM (**qwen3:8b**, Ollama, Intel iGPU via Vulkan) answer from them only, with `[n]` citations linked to the PDF page.

## Status (2026-11-02)

| Stage | Ship's PC (`E:\boat\manuals-rag`, repo `hutchel/manuals-rag`) |
|---|---|
| 1 Extract + search | **Working** - manifest: 372 files, 288 ok, 64 skipped, 20 needs-ocr; 16 OCR'd |
| 2 Index | **Working** - 307 manuals / 12,460 chunks (`index\manuals.db`) |
| 3 Q&A service | **Running** - `rag/app.py` v4, `:8200`, desktop icon "Boat Manuals" |

**The Q&A service is LIVE** on the Ship's PC at `http://192.168.1.113:8200`. v4 features: neighbor-page retrieval,
Brave Search inline web results, model pre-warm, connection pool, chat UI v4 (Search/Ask tabs, web results, dark mode).

## Pages

| Page | What it covers |
|---|---|
| [Architecture](Architecture.md) | Purpose, users, requirements, non-goals; the two copies; components, hosts, ports; what calls what |
| [Corpus-and-Extraction](Corpus-and-Extraction.md) | The manual library, the duplicates folder, extraction + OCR pipeline, the manifest, `search.py` |
| [Index-and-QA-Service](Index-and-QA-Service.md) | Index schema, chunking, embedding, hybrid retrieval, the prompt, the HTTP API contract, the chat page |
| [LLM-Host](LLM-Host.md) | The Ship's PC: hardware, Ollama + Vulkan iGPU, env vars, firewall, auto-start, Tesseract |
| [Operations](Operations.md) | Run, refresh after new manuals, check health, testing, failure modes, gotchas |
| [Design-Decisions](Design-Decisions.md) | Decision log with why + rejected options (incl. the superseded Pi design) |
| [Roadmap](Roadmap.md) | Open items only |

## Where things are

| Path | Role |
|---|---|
| `D:\Documents\sailboat\Manuals\` | The manual library - master copy on the laptop (read-only to this project) |
| `D:\Documents\sailboat\Manuals_DUPLICATES\` | 135 byte-identical duplicates moved out 2026-09-30, `MOVED.csv`; the owner deletes when happy |
| `extract/extract_corpus.py`, `extract/search.py`, `extract/README.md` | Stage one (identical on laptop and in the repo) |
| `extract/ocr_corpus.py`, `rag/`, `bench/`, `run-manuals.bat` | Stages two + three - **only in the repo / Ship's PC** |
| `corpus/` | Derived text + `_manifest.json` + `_last_run.log` - local only, git-ignored (copyrighted source) |
| `design/MANUALS_RAG_SPEC.md` | Spec v1 (2026-09-22) for a Pi deployment - **superseded in host and stack** by D-054 / the 10-03 build; kept for its reasoning |
| `CHECKPOINT.md` | Resume file (the laptop copy is behind the repo copy - see Roadmap) |
| SwallowAutomation `docs/Ships-PC-Setup.md` (laptop: `code/your-pi-hostname/docs/`) | Dated log of the Ship's PC build (10-03 / 10-04 entries) |
