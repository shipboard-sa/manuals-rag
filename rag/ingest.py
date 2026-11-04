"""
Purpose: Build / refresh the manuals vector index (stage two of manuals-rag, D-054): corpus text -> page-sized chunks
  -> local embeddings (Ollama, nomic-embed-text) -> one SQLite file with sqlite-vec. Incremental by the corpus
  manifest's sha1; a changed or removed manual has its chunks replaced / dropped.
Version: v2 (2026-10-03) - v2: folders named "old" (any depth) are excluded too (Lee: "old is out"). v1: first.
Scope: PRODUCTION-candidate - runs on the Ship's PC (D-054); rebuildable at any time from the corpus (spec D9).
Architecture: manuals-rag/rag. Reads corpus/<rel>.txt (page markers "===== [file] page N / M =====") + corpus/
  _manifest.json; writes index/manuals.db (tables doc, chunk, chunk_fts (FTS5) and vec0 table chunk_vec). Excludes
  _ARCHIVE_prev-boat/ (owner, Oct 2026: the previous boat's manuals must never answer a Hylas question). Talks only to
  Ollama on 127.0.0.1:11434 - nothing leaves the PC. index/ is gitignored (derived from copyrighted manuals).
Invocation: .venv\\Scripts\\python rag\\ingest.py [--force] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import struct
import sys
import time
import urllib.request
from pathlib import Path

import sqlite_vec

PROJECT = Path(__file__).resolve().parent.parent
CORPUS = PROJECT / "corpus"
INDEX = PROJECT / "index" / "manuals.db"
OLLAMA = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
DIM = 768
EXCLUDE = ("_ARCHIVE_prev-boat/",)          # the previous boat's manuals (owner, Oct 2026)
EXCLUDE_DIRS = {"old"}                      # superseded manuals, e.g. Electrical/Victron/old/ (owner, Oct 2026: "old is out")


def excluded(rel: str) -> bool:
    return rel.startswith(EXCLUDE) or any(part.lower() in EXCLUDE_DIRS for part in rel.split("/")[:-1])
MAX_CHARS, OVERLAP, MIN_CHARS = 1500, 200, 60
MARK = re.compile(r"^===== \[(?P<file>.*)\] page (?P<page>\d+) / (?P<pages>\d+) =====$", re.M)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS doc (doc_id INTEGER PRIMARY KEY, rel TEXT UNIQUE NOT NULL, sha1 TEXT NOT NULL,
                                pages INTEGER, indexed_at TEXT);
CREATE TABLE IF NOT EXISTS chunk (chunk_id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL REFERENCES doc(doc_id),
                                  page INTEGER NOT NULL, part INTEGER NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chunk_doc ON chunk(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(embedding float[{DIM}] distance_metric=cosine);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, content='chunk', content_rowid='chunk_id');
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: Path = INDEX) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    c.executescript(SCHEMA)
    return c


def embed(texts: list[str], prefix: str) -> list[list[float]]:
    body = json.dumps({"model": EMBED_MODEL, "input": [prefix + t for t in texts], "truncate": True}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["embeddings"]


def pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def pages_of(text: str):
    marks = list(MARK.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        yield int(m["page"]), text[m.end():end].strip()


def split(page_text: str) -> list[str]:
    t = re.sub(r"[ \t]+", " ", page_text)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) < MIN_CHARS:
        return []
    if len(t) <= MAX_CHARS:
        return [t]
    out, start = [], 0
    while start < len(t):
        end = min(len(t), start + MAX_CHARS)
        if end < len(t):  # prefer to break at a paragraph / line / sentence
            cut = max(t.rfind("\n\n", start, end), t.rfind("\n", start + MAX_CHARS // 2, end), t.rfind(". ", start + MAX_CHARS // 2, end))
            end = cut + 1 if cut > start else end
        out.append(t[start:end].strip())
        if end >= len(t):
            break
        start = max(end - OVERLAP, start + 1)
    return [p for p in out if len(p) >= MIN_CHARS]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild every document")
    ap.add_argument("--limit", type=int, default=0, help="index at most N changed documents")
    a = ap.parse_args()
    manifest = json.loads((CORPUS / "_manifest.json").read_text(encoding="utf-8"))["files"]
    wanted = {rel: e for rel, e in manifest.items()
              if e.get("status") == "ok" and not excluded(rel) and (CORPUS / (rel + ".txt")).is_file()}
    c = connect()
    have = {rel: (doc_id, sha1) for doc_id, rel, sha1 in c.execute("SELECT doc_id, rel, sha1 FROM doc")}

    def drop(doc_id: int) -> None:
        ids = [r[0] for r in c.execute("SELECT chunk_id FROM chunk WHERE doc_id=?", (doc_id,))]
        for cid in ids:
            c.execute("DELETE FROM chunk_vec WHERE rowid=?", (cid,))
            c.execute("INSERT INTO chunk_fts(chunk_fts, rowid, text) SELECT 'delete', chunk_id, text FROM chunk WHERE chunk_id=?", (cid,))
        c.execute("DELETE FROM chunk WHERE doc_id=?", (doc_id,))
        c.execute("DELETE FROM doc WHERE doc_id=?", (doc_id,))

    for rel in [r for r in have if r not in wanted]:  # removed, excluded or no longer ok
        drop(have[rel][0]); print(f"dropped {rel}")
    todo = [rel for rel, e in sorted(wanted.items()) if a.force or rel not in have or have[rel][1] != e["sha1"]]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(wanted)} documents in scope, {len(todo)} to index")
    t0, n_chunks = time.time(), 0
    for i, rel in enumerate(todo, 1):
        if rel in have:
            drop(have[rel][0])
        text = (CORPUS / (rel + ".txt")).read_text(encoding="utf-8", errors="replace")
        rows = [(page, k, part) for page, body in pages_of(text) for k, part in enumerate(split(body))]
        cur = c.execute("INSERT INTO doc(rel, sha1, pages, indexed_at) VALUES (?,?,?,datetime('now'))",
                        (rel, wanted[rel]["sha1"], wanted[rel].get("pages")))
        doc_id = cur.lastrowid
        for b in range(0, len(rows), 32):
            batch = rows[b:b + 32]
            vecs = embed([f"{Path(rel).stem}: {p}" for _, _, p in batch], "search_document: ")
            for (page, k, part), v in zip(batch, vecs):
                cid = c.execute("INSERT INTO chunk(doc_id, page, part, text) VALUES (?,?,?,?)", (doc_id, page, k, part)).lastrowid
                c.execute("INSERT INTO chunk_vec(rowid, embedding) VALUES (?,?)", (cid, pack(v)))
                c.execute("INSERT INTO chunk_fts(rowid, text) VALUES (?,?)", (cid, part))
        c.commit()
        n_chunks += len(rows)
        print(f"[{i}/{len(todo)}] {len(rows):4d} chunks  {rel}", flush=True)
    c.execute("INSERT OR REPLACE INTO meta VALUES ('embed_model', ?), ('built', datetime('now'))", (EMBED_MODEL,))
    c.commit()
    total = c.execute("SELECT count(*) FROM chunk").fetchone()[0]
    print(f"done: {n_chunks} chunks indexed in {time.time() - t0:.0f}s; index holds {total} chunks "
          f"from {c.execute('SELECT count(*) FROM doc').fetchone()[0]} documents")


if __name__ == "__main__":
    sys.exit(main())
