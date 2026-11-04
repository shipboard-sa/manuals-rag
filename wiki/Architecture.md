<!--
Purpose: manuals-rag architecture - purpose, users, requirements, non-goals, the two copies, components, hosts,
  ports and what calls what.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass.
Scope: PRODUCTION-candidate - documentation for manuals-rag.
Architecture: code/manuals-rag/wiki/. Sources: spec v1 s.1-2, CHECKPOINT (repo copy, 10-03), code headers in
  hutchel/manuals-rag (rag/app.py v1, rag/ingest.py v2, extract/*.py), Ships-PC-Setup.md 10-03/10-04 entries.
Invocation: n/a (reference doc)
-->

# Architecture

## Purpose and users

- **Lee** asks plain-language questions while troubleshooting or running a "what if" underway - "what's the torque
  on the raw water pump impeller cover", "if the primary bilge pump fails, what's my backup path" - and gets an
  answer from the boat's own manuals with a citation (manual + page) he can open and verify. Spec s.1.
- **Must work with zero connectivity** (offshore). Spec s.1, D2; requirement N-02 "Offline-first" in the Ship's
  Automation spec (`spec/00-Requirements.md:88`).
- **Claude** uses stage one (`search.py`) directly, and through recall's `manuals` store, to cite manuals.
- Origin: Colin raised the idea (2026-09-22) of a one-time parse so a local LLM gives instant answers instead of
  paging through PDFs; the owner asked for a full scope. The friction it removes: Colin's existing manual store was not
  easy for the owner to drop new files into - the PDFs stay in a plain folder the owner controls (spec s.1, D3).

## Requirements

| # | Requirement | Source |
|---|---|---|
| M1 | Answers grounded in the manuals only, every fact cited as manual + page, linked to the PDF page | spec s.6; `rag/app.py` SYSTEM prompt |
| M2 | No cloud call anywhere in the running system, including Claude (Claude Code is a build tool only) | spec D2 |
| M3 | Manuals stay plain files in a folder the owner can drop into; the index is derived and rebuildable from them | spec D3, D9 |
| M4 | Incremental: only new / changed manuals are re-extracted and re-embedded | spec s.5 step 6 |
| M5 | The previous boat's manuals (`_ARCHIVE_prev-boat/`) never answer a Hylas question | owner, Oct 2026, "definitely!!!!" |
| M6 | Superseded manuals never answer: folders named `old` (owner, Oct 2026, "old is out") and `Previous versions` (the owner 10-02) are excluded | ingest.py v2; extract_corpus.py v2 |
| M7 | The corpus and index (text derived from copyrighted manuals) stay local - never committed, pushed or published | `.gitignore`; extract/README |
| M8 | Usable from the tablet / phones on the boat LAN; no login (LAN / tailnet trust boundary) | spec s.2; chat.html header |
| M9 | Runs on the Ship's PC, not on the Pi | D-054 / OQ-078 (the owner 2026-09-29) |

## Non-goals (v1)

- Reading diagrams, schematics or wiring drawings. OCR'd schematic pages are noise; the system points at the page
  to open (spec s.2).
- Integration with mx-inv (no shared UI or data). A chat panel in mx-inv is a later option, not decided.
- Authentication beyond the LAN / tailnet boundary.
- Any cloud or API model.

## Two copies (important)

| | Laptop | Ship's PC |
|---|---|---|
| Path | `D:\Documents\sailboat\code\manuals-rag` | `E:\boat\manuals-rag` (E: = external USB drive) |
| Git | not a checkout (the sailboat tree is not a repo) | clone of private `hutchel/manuals-rag`, branch `main` (last push `213b9e7`, 2026-10-03) |
| Manual library | `D:\Documents\sailboat\Manuals` (**master**, Laptop-to-ShipsPC-Checklist A5) | `E:\boat\Manuals` (USB copy 10-03: 369 files, 1,499,817,064 B) |
| Has | stage one only (`extract/`, `design/`, CHECKPOINT v3 of 09-30) | stages one-three, `bench/`, OCR'd corpus, index, CHECKPOINT updated 10-03 |
| Python | `.venv` (pymupdf 1.28.2) | `.venv`, Python 3.14.7, `requirements.txt` v2 |

The two corpora have diverged: the laptop corpus was re-extracted on 2026-10-06 (manuals added since, e.g.
Refrigeration) but has no OCR; the Ship's PC corpus has the OCR text but not the 10-06 additions. There is no sync
between the libraries today (the planned Syncthing mirror is parked until the GL router work - memory
`backup-infrastructure.md`).

## Components (Ship's PC build)

```
 E:\boat\Manuals\*.pdf|docx|html|txt  (read-only)
        |
        | extract/extract_corpus.py  (PyMuPDF, child worker per PDF, incremental by size+mtime)
        | extract/ocr_corpus.py      (Tesseract 5 via PyMuPDF, for status needs-ocr)
        v
 corpus/<rel>.txt  +  corpus/_manifest.json     <-- extract/search.py (grep; laptop: recall 'manuals' store)
        |
        | rag/ingest.py  (page chunks -> Ollama /api/embed nomic-embed-text, incremental by manifest sha1)
        v
 index/manuals.db  (SQLite: doc, chunk, chunk_fts FTS5, chunk_vec vec0 768-d cosine, meta)
        |
        | rag/app.py  FastAPI on 0.0.0.0:8200
        |   retrieve: vec top 4K + bm25 top 4K -> reciprocal-rank fusion -> top K=6
        |   answer:   Ollama /api/chat qwen3:8b, streamed, think off, num_ctx 8192, temperature 0.2
        v
 Browser (tablet / phone / PC) -> http://192.168.1.113:8200   (chat.html; PDFs at /manuals/<rel>#page=N)

 Ollama 0.35.1 on 127.0.0.1:11434 (tray app, user env OLLAMA_VULKAN=1, OLLAMA_IGPU_ENABLE=1, OLLAMA_KEEP_ALIVE=30m)
   -> Intel iGPU via Vulkan, 37/37 layers of qwen3:8b offloaded
```

| Component | Role | Called by | Calls |
|---|---|---|---|
| `extract/extract_corpus.py` | Library -> corpus + manifest | operator, by hand | PyMuPDF (in a child process) |
| `extract/ocr_corpus.py` | OCR the `needs-ocr` files into the corpus, flips them to `ok` + `ocr: true` | operator, by hand | PyMuPDF + Tesseract |
| `extract/search.py` | Grep the corpus, `file p.N: line` | Claude; recall.py (subprocess) | corpus files |
| `rag/ingest.py` | Corpus -> `index/manuals.db` | operator, by hand | Ollama `/api/embed` |
| `rag/app.py` | HTTP API + chat page + PDF serving | browsers; landing-page probe; `bench/ask_timing.py` | `index/manuals.db`, Ollama `/api/embed` + `/api/chat`, `MANUALS_ROOT` files |
| `rag/chat.html` | Single-page UI, no framework, no external files | served at `/` | `POST /api/ask` |
| `run-manuals.bat` | Launcher; refuses a second copy; sets `MANUALS_LLM=qwen3:8b` | desktop icon "Boat Manuals"; Task Scheduler "boat manuals" at logon | uvicorn |
| `bench/bench_models.py`, `bench/ask_timing.py` | One-off model speed / end-to-end timing measurements | operator | Ollama; `:8200/api/ask` |

## Hosts, ports, consumers

| Thing | Value | Source |
|---|---|---|
| Host | Ship's PC `SHIP_PC`, MSI Cubi NUC 1M (MS-B0B1), Core 5 120U, 32 GB, Windows 11 Pro, 192.168.1.113 (DHCP reservation, wired) | Ships-PC-Setup.md:2, :86; network.md:94 |
| Q&A service | TCP **8200** on 0.0.0.0, inbound firewall rule `manuals-rag chat (TCP 8200)`, Private profile | Ships-PC-Setup.md:306 |
| Ollama | 127.0.0.1:11434 only (not exposed) | rag/app.py, ingest.py |
| Landing page | Pi `192.168.1.21:8080` tile "Boat manuals" -> ships-pc:8200; health probe `/probe/manuals` proxies to `http://192.168.1.113:8200/` | code/your-pi-hostname `stacks/home/site/index.html:78`, `stacks/home/nginx.conf:26` |
| Port clash to remember | The rules engine on the Pi also uses 8200 (127.0.0.1:8200 on boat-automation). Different host; do not confuse them. | network.md:82; rules-engine compose.yml |
| Other consumer of the library | mx-inv links into the manuals folder (`MXINV_MANUALS_ROOT` / Settings "Manuals folder") | Ships-PC-Setup.md:63; Laptop-to-ShipsPC-Checklist A5 |
