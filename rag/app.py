"""
Purpose: The manuals Q&A service (stage three of manuals-rag, D-054): ask a question, get an answer from the boat's own
  manuals with citations (manual + page, linked to the PDF page), entirely offline on the Ship's PC.
Version: v4 (2026-11-02) - v4: Brave Search API integration (inline web results alongside local manual hits; proxied
  through /api/web so the API key stays server-side; disabled when BRAVE_API_KEY is unset or offline).
  v3 (2026-11-02): neighbor-page retrieval, connection pool, model pre-warm, chat UI overhaul.
  v2 (2026-10-07): MANUALS_LLM default qwen3:8b. v1 (2026-10-03)
Scope: PRODUCTION-candidate - runs on the Ship's PC (D-054); not deployed to the Pi.
Architecture: manuals-rag/rag. FastAPI on :8200 (LAN via the Private-profile firewall rule; no auth = the LAN/tailnet
  trust boundary, spec s.2). Retrieval = hybrid: sqlite-vec cosine (nomic-embed-text "search_query:") + FTS5 bm25
  (exact words - part numbers, torque values), merged by reciprocal-rank fusion -> top K chunks with neighbor-page
  expansion (page-1 and page+1 from the same manual merged into each hit, so multi-page procedures arrive intact) ->
  local LLM via Ollama (127.0.0.1:11434, streamed) told to answer ONLY from the numbered excerpts and cite [n]. PDFs
  served read-only from MANUALS_ROOT for the page links. /api/web proxies Brave Search API (the only outbound call;
  requires BRAVE_API_KEY env var; gracefully disabled when missing or offline).
Invocation: .venv\\Scripts\\python -m uvicorn rag.app:app --host 0.0.0.0 --port 8200   (from E:\\boat\\manuals-rag)
  env: MANUALS_LLM (default qwen3:8b), MANUALS_ROOT (default E:\\boat\\Manuals), MANUALS_K (default 6),
       BRAVE_API_KEY (optional - enables web search; get one at api-dashboard.search.brave.com)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import struct
import threading
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from rag.ingest import EMBED_MODEL, INDEX, connect

log = logging.getLogger("manuals-rag")

LLM = os.environ.get("MANUALS_LLM", "qwen3:8b")
ROOT = Path(os.environ.get("MANUALS_ROOT", r"E:\boat\Manuals")).resolve()
K = int(os.environ.get("MANUALS_K", "6"))
OLLAMA = "http://127.0.0.1:11434"
BRAVE_KEY = os.environ.get("BRAVE_API_KEY", "")
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
HERE = Path(__file__).resolve().parent

_db_lock = threading.Lock()
_db_conn: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _db_conn
    with _db_lock:
        if _db_conn is None:
            _db_conn = connect(INDEX)
        return _db_conn


def _warm_models() -> None:
    """Pre-load the embed + LLM models into Ollama so the first real question is fast."""
    try:
        _post("/api/embed", {"model": EMBED_MODEL, "input": ["warm"]})
        _post("/api/generate", {"model": LLM, "prompt": "hi", "options": {"num_predict": 1}})
        log.info("models warmed: %s + %s", EMBED_MODEL, LLM)
    except Exception as e:
        log.warning("model warm-up failed (Ollama may not be running yet): %s", e)


@asynccontextmanager
async def lifespan(a: FastAPI):
    threading.Thread(target=_warm_models, daemon=True).start()
    yield
    with _db_lock:
        if _db_conn is not None:
            try:
                _db_conn.close()
            except sqlite3.ProgrammingError:
                pass

SYSTEM = (
    "You are the manuals assistant aboard SV Your Vessel, a Your Boat Model sailboat. Answer ONLY from the numbered "
    "manual excerpts you are given. Cite every fact with its excerpt number like [2]. Quote numbers, torque values, "
    "part numbers and warnings exactly as written. Give procedures as short numbered steps. If the excerpts do not "
    "contain the answer, say so plainly and name the excerpt that comes closest - never guess or use outside knowledge. "
    "Be concise.")

app = FastAPI(title="manuals-rag", lifespan=lifespan)


def _post(path: str, body: dict, stream: bool = False):
    req = urllib.request.Request(OLLAMA + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=900)


def _embed_query(q: str) -> bytes:
    with _post("/api/embed", {"model": EMBED_MODEL, "input": ["search_query: " + q]}) as r:
        v = json.loads(r.read())["embeddings"][0]
    return struct.pack(f"{len(v)}f", *v)


def _fts_query(q: str) -> str:
    words = [w for w in re.findall(r"[\w.\-/]+", q) if len(w) > 2]
    return " OR ".join('"' + w.replace('"', "") + '"' for w in words) or '""'


def _page_text(c: sqlite3.Connection, doc_id: int, page: int) -> str:
    rows = c.execute("SELECT text FROM chunk WHERE doc_id = ? AND page = ? ORDER BY part", (doc_id, page)).fetchall()
    return "\n\n".join(r[0] for r in rows)


def retrieve(q: str, k: int = K) -> list[dict]:
    c = _get_db()
    vec = c.execute("SELECT rowid FROM chunk_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                    (_embed_query(q), k * 4)).fetchall()
    try:
        fts = c.execute("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?",
                        (_fts_query(q), k * 4)).fetchall()
    except sqlite3.OperationalError:
        fts = []
    score: dict[int, float] = {}
    for lst in (vec, fts):  # reciprocal-rank fusion
        for rank, (cid,) in enumerate(lst):
            score[cid] = score.get(cid, 0.0) + 1.0 / (60 + rank)
    top = sorted(score, key=score.get, reverse=True)[:k]
    out = []
    seen_pages: set[tuple[int, int]] = set()
    for cid in top:
        rel, doc_id, page = c.execute(
            "SELECT d.rel, ch.doc_id, ch.page FROM chunk ch JOIN doc d USING(doc_id) "
            "WHERE ch.chunk_id = ?", (cid,)).fetchone()
        if (doc_id, page) in seen_pages:
            continue
        parts = []
        for p in (page - 1, page, page + 1):
            if p < 0 or ((doc_id, p) in seen_pages and p != page):
                continue
            t = _page_text(c, doc_id, p)
            if t:
                parts.append((p, t))
                seen_pages.add((doc_id, p))
        seen_pages.add((doc_id, page))
        text = "\n\n".join(t for _, t in sorted(parts))
        out.append({"manual": rel, "page": page, "text": text,
                    "link": f"/manuals/{urllib.parse.quote(rel)}#page={page}"})
    return out


class Ask(BaseModel):
    question: str
    k: int | None = None


@app.get("/api/health")
def health() -> dict:
    c = _get_db()
    n = c.execute("SELECT count(*) FROM chunk").fetchone()[0]
    d = c.execute("SELECT count(*) FROM doc").fetchone()[0]
    built = c.execute("SELECT v FROM meta WHERE k = 'built'").fetchone()
    return {"status": "ok", "documents": d, "chunks": n, "llm": LLM, "embed": EMBED_MODEL,
            "indexed": built[0] if built else None, "web": bool(BRAVE_KEY)}


@app.get("/api/search")
def search(q: str, k: int = K) -> list[dict]:
    """Retrieval only - fast, no LLM (which manual / page talks about this?)."""
    return retrieve(q, k)


@app.post("/api/ask")
def ask(body: Ask) -> StreamingResponse:
    """NDJSON stream: {"sources": [...]} first, then {"token": "..."} pieces, then {"done": true, ...}."""
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "empty question")
    sources = retrieve(q, body.k or K)

    def gen() -> Iterator[bytes]:
        yield (json.dumps({"sources": [{k: s[k] for k in ("manual", "page", "link")} for s in sources]}) + "\n").encode()
        excerpts = "\n\n".join(f"[{i}] {s['manual']} (page {s['page']}):\n{s['text']}" for i, s in enumerate(sources, 1))
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Manual excerpts:\n\n{excerpts}\n\nQuestion: {q}"}]
        with _post("/api/chat", {"model": LLM, "messages": msgs, "stream": True, "think": False,
                                 "options": {"num_ctx": 12288, "temperature": 0.2}}) as r:
            for line in r:
                if not line.strip():
                    continue
                j = json.loads(line)
                if j.get("message", {}).get("content"):
                    yield (json.dumps({"token": j["message"]["content"]}) + "\n").encode()
                if j.get("done"):
                    yield (json.dumps({"done": True, "model": LLM, "answer_tokens": j.get("eval_count"),
                                       "seconds": round((j.get("total_duration") or 0) / 1e9, 1)}) + "\n").encode()
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/web")
def web_search(q: str, count: int = 8) -> dict:
    """Proxy to Brave Search API. Returns {results: [...], error?: str}. Disabled when BRAVE_API_KEY is unset."""
    if not BRAVE_KEY:
        return {"results": [], "error": "web search not configured (set BRAVE_API_KEY)"}
    try:
        params = urllib.parse.urlencode({"q": q, "count": min(count, 20)})
        req = urllib.request.Request(
            f"{BRAVE_API}?{params}",
            headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                     "X-Subscription-Token": BRAVE_KEY})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            data = json.loads(raw)
        results = []
        for hit in (data.get("web", {}).get("results") or [])[:count]:
            results.append({"title": hit.get("title", ""), "url": hit.get("url", ""),
                            "snippet": hit.get("description", "")})
        return {"results": results}
    except Exception as e:
        log.warning("Brave Search failed: %s", e)
        return {"results": [], "error": str(e)}


@app.get("/manuals/{rel:path}")
def manual_file(rel: str) -> FileResponse:
    p = (ROOT / rel).resolve()
    if ROOT not in p.parents or not p.is_file():  # no path traversal outside the manuals folder
        raise HTTPException(404, "not found")
    return FileResponse(p)


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return (HERE / "chat.html").read_text(encoding="utf-8")
