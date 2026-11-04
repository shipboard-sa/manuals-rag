<!--
Purpose: Stages two + three of manuals-rag - the vector/FTS index schema, chunking and embedding, hybrid retrieval,
  the LLM prompt, the HTTP API contract and the chat page.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass from hutchel/manuals-rag main (213b9e7):
  rag/ingest.py v2, rag/app.py v1, rag/chat.html v1, run-manuals.bat v1, requirements.txt v2.
Scope: PRODUCTION-candidate - documentation for manuals-rag (runs on the Ship's PC, D-054).
Architecture: code/manuals-rag/wiki/. The code is NOT in the laptop folder - read it in the repo
  (gh api repos/hutchel/manuals-rag/contents/rag/app.py) or on E:\boat\manuals-rag.
Invocation: n/a (reference doc)
-->

# Index and Q&A service (stages two + three)

## Index build - rag/ingest.py (v2)

```
.venv\Scripts\python rag\ingest.py [--force] [--limit N]        # from E:\boat\manuals-rag; Ollama must be running
```

**Scope selection:** manifest entries with `status == "ok"`, whose `.txt` exists, and not excluded. Excluded: path
starts with `_ARCHIVE_prev-boat/`, or any *folder* component named `old` (case-insensitive).

**Incremental rule:** a document is (re)indexed when it is new, its manifest `sha1` differs from the stored one, or
`--force`. Documents in the index but no longer in scope (removed, excluded, or no longer `ok`) are dropped (chunks,
vectors and FTS rows deleted). `--limit N` caps how many changed documents are indexed in one run.

**Chunking (per PDF page, so every chunk cites one page):**
- page text = text between page markers; runs of spaces/tabs collapsed, 3+ newlines -> 2;
- page under **60** chars -> no chunk; page up to **1,500** chars -> one chunk;
- longer pages split into ~1,500-char windows with **200** chars overlap, cutting preferably at a blank line, else a
  newline or ". " in the second half of the window; pieces under 60 chars dropped.
- Non-PDF documents (single `(kind)` marker, no page markers) yield no chunks.

**Embedding:** Ollama `POST http://127.0.0.1:11434/api/embed`, model `nomic-embed-text` (768 dimensions),
`truncate: true`, batches of 32. Document text is embedded as `"search_document: <file stem>: <chunk>"` (the
nomic task prefix, plus the manual's file name so the model knows which device the page belongs to). Timeout 600 s.
Commit after each document.

**Result 2026-10-03:** 263 documents / 10,318 chunks; after the `old/` exclusion **255 documents / 10,100 chunks**.

## Index schema - index/manuals.db (SQLite + sqlite-vec 0.1.9)

| Table | Columns | Notes |
|---|---|---|
| `doc` | `doc_id` INTEGER PK, `rel` TEXT UNIQUE (path under the library), `sha1` TEXT, `pages` INTEGER, `indexed_at` TEXT (UTC `datetime('now')`) | one row per indexed manual |
| `chunk` | `chunk_id` INTEGER PK, `doc_id` -> doc, `page` INTEGER (PDF page index), `part` INTEGER (0-based piece within the page), `text` TEXT | index `chunk_doc(doc_id)` |
| `chunk_vec` | vec0 virtual table `embedding float[768] distance_metric=cosine`; `rowid` = `chunk_id` | float32 little-endian packed |
| `chunk_fts` | FTS5 external-content table over `chunk.text` (`content='chunk', content_rowid='chunk_id'`) | deletes via the `'delete'` command |
| `meta` | `k` TEXT PK, `v` TEXT | `embed_model`, `built` |

The index is **derived and disposable**: delete `index/` and rerun `ingest.py --force` to rebuild from the corpus
(spec D9 - no backup job). It is git-ignored (derived from copyrighted manuals).

## Q&A service - rag/app.py (v4)

Start: `run-manuals.bat` (desktop icon "Boat Manuals"; Task Scheduler "boat manuals" at logon) which runs
`.venv\Scripts\python.exe -m uvicorn rag.app:app --host 0.0.0.0 --port 8200` from the project folder.

| Env var | Default in app.py | Set by run-manuals.bat | Meaning |
|---|---|---|---|
| `MANUALS_LLM` | `qwen3:8b` | `qwen3:8b` (if unset) | Ollama chat model |
| `MANUALS_ROOT` | `E:\boat\Manuals` | - | Library served at `/manuals/...` for page links |
| `MANUALS_K` | `6` | - | Excerpts per answer |
| `BRAVE_API_KEY` | (none) | the owner sets | Brave Search API key; enables `/api/web` |

### Retrieval (hybrid)

1. Embed the question as `"search_query: <question>"` (nomic-embed-text).
2. Vector: `chunk_vec MATCH ? AND k = 4K ORDER BY distance` (cosine) -> up to 24 chunk ids.
3. Keyword: FTS5 `bm25`, query = every token of 3+ chars matching `[\w.\-/]+`, each quoted, joined with `OR`
   -> up to 24 ids. (Exact words matter: part numbers, torque values, fault codes.) An FTS syntax error -> keyword
   list empty, vector only.
4. **Reciprocal-rank fusion:** score = sum over both lists of `1 / (60 + rank)`; top K (6) chunks.
5. **Neighbor-page expansion (v4):** each hit's page-1 and page+1 from the same manual are fetched and merged, so
   multi-page procedures arrive intact. Deduplication by `(doc_id, page)`.
6. Each source returned as `{manual, page, text, link}` with `link = /manuals/<url-quoted rel>#page=<page>`.

### Answer generation

Ollama `POST /api/chat`, `stream: true`, `think: false`, options `num_ctx 12288`, `temperature 0.2`. Messages:

- system: the assistant aboard the boat answers ONLY from the numbered excerpts, cites every fact as `[n]`, quotes
  numbers / torque values / part numbers / warnings exactly, gives procedures as short numbered steps, says plainly
  when the excerpts do not contain the answer and names the closest excerpt, never guesses or uses outside
  knowledge, is concise. (Exact text: `SYSTEM` in `rag/app.py`; it names the boat "SV Your Vessel" without the 2.)
- user: `Manual excerpts:\n\n[1] <manual> (page N):\n<text>\n\n[2] ...\n\nQuestion: <question>`.

### HTTP API (port 8200, no auth)

| Method + path | Request | Response | Errors |
|---|---|---|---|
| `GET /` | - | `chat.html` (text/html) | - |
| `GET /api/health` | - | `{"status":"ok","documents":307,"chunks":12460,"llm":"qwen3:8b","embed":"nomic-embed-text","indexed":"2026-10-20...","web":true}` | a missing `index/manuals.db` is created empty and reports 0 documents; `web` = whether `BRAVE_API_KEY` is set |
| `GET /api/search?q=<text>&k=<n>` | query string; `k` default 6 | JSON list of `{manual, page, text, link}` - retrieval only, no LLM (fast), with neighbor-page expansion | 500 if Ollama (embedding) is down |
| `GET /api/web?q=<text>&count=<n>` | query string; `count` default 8, max 20 | `{"results":[{title, url, snippet},...], "error"?:str}` - Brave Search proxy | returns `error` if key unset or Brave offline |
| `POST /api/ask` | JSON `{"question": "...", "k": null}` | `application/x-ndjson` stream: first `{"sources":[{manual,page,link},...]}`, then `{"token":"..."}` pieces, then `{"done":true,"model":"qwen3:8b","answer_tokens":N,"seconds":S}` | 400 `empty question`; an Ollama failure mid-stream ends the stream without `done` |
| `GET /manuals/{rel:path}` | path under `MANUALS_ROOT` | the file (PDF opens at `#page=N` in the browser) | 404 if missing or if the resolved path escapes `MANUALS_ROOT` (path-traversal guard) |

Consumers: the chat page; the Pi landing page probe `/probe/manuals` (expects any 200 from `/`); `bench/ask_timing.py`.

### Chat page - rag/chat.html (v4)

Two tabs: **Search** (default, instant - retrieval only, no LLM) and **Ask** (LLM answer with citations). Search
fires local `/api/search` and Brave `/api/web` in parallel; results shown in separate "Your manuals" and "Web results"
sections. Web section hidden when `BRAVE_API_KEY` is unset or offline. Conversation history, new-chat button,
expandable source excerpts, status bar (document count, model, index date, web on/off), mobile layout, dark mode,
thinking animation. No framework and no external files, so it works on the tablet with no internet.

## Measured performance and quality (Ship's PC, 2026-10-03)

| Setup | Time to first word | Total |
|---|---|---|
| qwen3:8b, CPU only | 100-125 s | - |
| qwen3:8b, Intel iGPU via Vulkan, warm (37/37 layers on GPU) | ~25-30 s | ~1 min (warm 45-55 s) |
| First question after a restart (both models load cold) | - | ~100 s |
| qwen3:4b | rejected: ignores `think:false` and rambles (3,593 tokens / 7.5 min for one answer) | |

Quality v1: facts and citations good (Fireboy 175 F p.4 = Ship's Automation F-125; watermaker pickling procedure
clean; Yanmar impeller interval 1,000 h). v4 neighbor-page retrieval fixes the fragmented-procedure problem
(the impeller answer no longer mixes in fuel-bleed steps).
