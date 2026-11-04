"""
Purpose: Measure local-LLM speed on this host for manuals-rag model choice (D8 / D-054): prompt processing
  (tokens/s reading the retrieved manual text) and generation (tokens/s writing the answer), per model.
Version: v1 (2026-10-03)
Scope: STANDALONE UTILITY - one-off measurement on the Ship's PC (CPU only, no GPU).
Architecture: manuals-rag/bench. Talks to the local Ollama API (127.0.0.1:11434) only; builds a realistic RAG
  prompt from ~6,000 characters of the text corpus (current boat only - _ARCHIVE_prev-boat excluded, owner, Oct 2026).
Invocation: .venv\\Scripts\\python bench\\bench_models.py qwen3:4b qwen3:8b ...   (models must be pulled first)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
API = "http://127.0.0.1:11434/api/generate"
QUESTION = "How do I replace the raw water pump impeller, and what should I check before restarting the engine?"


def context() -> tuple[str, str]:
    for p in sorted(CORPUS.rglob("*.txt")):
        rel = p.relative_to(CORPUS).as_posix()
        if rel.startswith("_ARCHIVE_prev-boat/"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        i = t.lower().find("impeller")
        if i >= 0:
            s = max(0, i - 3000)
            return rel, t[s:s + 6000]
    raise SystemExit("no impeller text in the corpus")


def run(model: str, ctx_src: str, ctx: str) -> dict:
    prompt = (f"Answer ONLY from the manual excerpt below and cite the page marker you used.\n\n"
              f"--- manual: {ctx_src} ---\n{ctx}\n--- end ---\n\nQuestion: {QUESTION}")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "think": False,
                       "options": {"num_ctx": 8192, "temperature": 0.2, "num_predict": 300}}).encode()
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(API, body, {"Content-Type": "application/json"}), timeout=900) as r:
        j = json.loads(r.read())
    wall = time.time() - t0
    pe, pd = j.get("prompt_eval_count", 0), j.get("prompt_eval_duration", 1) / 1e9
    ge, gd = j.get("eval_count", 0), j.get("eval_duration", 1) / 1e9
    return {"model": model, "wall_s": round(wall, 1), "load_s": round(j.get("load_duration", 0) / 1e9, 1),
            "prompt_tokens": pe, "prompt_tok_s": round(pe / pd, 1) if pd else 0,
            "answer_tokens": ge, "answer_tok_s": round(ge / gd, 1) if gd else 0,
            "answer_start": j.get("response", "").strip().replace("\n", " ")[:220]}


def main() -> None:
    src, ctx = context()
    print(f"context: {src} ({len(ctx)} chars)\n")
    for m in sys.argv[1:]:
        try:
            print(json.dumps(run(m, src, ctx), indent=1))
        except Exception as e:  # keep going with the next model
            print(f"{m}: FAILED {e}")


if __name__ == "__main__":
    main()
