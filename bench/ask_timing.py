"""
Purpose: Time real end-to-end answers from the running manuals service (time to sources, first word, full answer) and
  print the answer + sources, for the model choice and the quality verdict.
Version: v1 (2026-10-03)
Scope: STANDALONE UTILITY - manuals-rag/bench.
Architecture: POST http://127.0.0.1:8200/api/ask (NDJSON stream from rag/app.py).
Invocation: .venv\\Scripts\\python bench\\ask_timing.py "question" ["question" ...]
"""
import json
import sys
import time
import urllib.request

for q in sys.argv[1:]:
    t0 = time.time(); first = None; srcs = []; ans = []; done = {}
    req = urllib.request.Request("http://127.0.0.1:8200/api/ask", json.dumps({"question": q}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            m = json.loads(line)
            if "sources" in m:
                srcs = m["sources"]; t_src = time.time() - t0
            if "token" in m:
                first = first or time.time() - t0; ans.append(m["token"])
            if m.get("done"):
                done = m
    print(f"\n=== {q}\nsources {t_src:.1f}s | first word {first or 0:.0f}s | total {time.time() - t0:.0f}s | "
          f"{done.get('answer_tokens')} tokens ({done.get('model')})")
    for i, s in enumerate(srcs, 1):
        print(f"  [{i}] {s['manual']} p.{s['page']}")
    print("".join(ans).strip())
