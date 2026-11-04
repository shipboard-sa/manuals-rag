<!--
Purpose: manuals-rag decision log - each decision with why and what was rejected, including the superseded Pi
  design from spec v1.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass (spec v1 D1-D11, CHECKPOINT, Ship's
  Automation OQ-078 / D-054 / D-072, Ships-PC-Setup.md 10-03 entries, code headers).
Scope: PRODUCTION-candidate - documentation for manuals-rag.
Architecture: code/manuals-rag/wiki/. Local ids MD-n; spec v1 ids D1-D11 kept where a row maps to one. Add rows,
  never rewrite old ones - mark superseded.
Invocation: n/a (reference doc)
-->

# Design decisions

| # | Decision | Why | Rejected / superseded | Source |
|---|---|---|---|---|
| MD-1 | **Retrieval-augmented generation over the boat's own manuals**, answers cite manual + page | the owner pages through PDFs by hand today; answers must be verifiable against the source | A model answering from its own knowledge | spec s.1 (2026-09-22) |
| MD-2 | **No cloud model anywhere at runtime, including Claude**; Claude Code is a build tool only (spec D2) | Must work offshore with no connectivity | API models, cloud fallback | spec D2; the owner |
| MD-3 | **PDFs stay plain files in a folder the owner controls** (spec D3) | Colin's manual store was hard for the owner to add to - the friction that started this | Colin's manual store | spec D3 |
| MD-4 | **Host = the Ship's PC** (MSI Cubi, 32 GB), not the Pi | Independence from Colin's stack (D-000); the Pi is the alarm host and must not be starved; 32 GB makes a 7-8B model realistic | **Spec v1 D1** (new Docker stack on the Pi, Syncthing `boat-manuals` folder D4, Traefik route `manuals.your-pi-hostname...` D7, Colin's Ansible D10, sequencing D11) - all superseded; Colin's votes no longer needed. The Pi's manuals nginx copy was DROPPED (D-072). | OQ-078 -> D-054 (the owner 2026-09-29); D-072 |
| MD-5 | **Stage one = a page-marked plain-text corpus** with a manifest, built before any LLM | Useful immediately (Claude greps with file + page), and the same corpus feeds the index | Embedding straight from PDFs | CHECKPOINT v2 (2026-09-30) |
| MD-6 | **PyMuPDF**, each PDF in a killable child process with a timeout | Fast and license-friendly; one pathological PDF must not stop the run | pypdf (spec offered both) | extract_corpus.py v1 |
| MD-7 | **Citations use PDF page indexes** | That is what a viewer's "go to page" and `#page=N` links use; printed numbers are unreliable | Printed page numbers | extract/README |
| MD-8 | **Duplicates moved out, not deleted** (`Manuals_DUPLICATES`, `MOVED.csv`) | the owner decides deletions; the CSV makes it reversible | Deleting in place | 2026-09-30 |
| MD-9 | **`Previous versions/` never extracted** | Superseded copies are never truth | Indexing with a flag | the owner 2026-10-02; extract_corpus.py v2 |
| MD-10 | **`_ARCHIVE_prev-boat/` out of the LLM index and OCR** (still greppable) | The previous boat's manuals must never answer a Hylas question | Including with a label | owner, Oct 2026, "definitely!!!!" |
| MD-11 | **Folders named `old` out of the LLM index** | Superseded manuals (MultiPlus 3k vs the installed MultiPlus-II) gave wrong answers; after the change the MultiPlus question found the MultiPlus-II manual | Keeping them | owner, Oct 2026, "old is out"; ingest.py v2 |
| MD-12 | **OCR with Tesseract 5 at 300 dpi** for image-only manuals | The Yanmar operation manual and OPM were unsearchable; spec s.5 step 3 | ocrmypdf (not used) | ocr_corpus.py v1, 10-03 |
| MD-13 | **Vector store = sqlite-vec in one SQLite file, plus FTS5** | Zero daemon, single file, rebuildable; matches the SQLite-friendly pattern (spec D6 offered Chroma or sqlite-vec) | Chroma (another daemon) | CHECKPOINT 10-03 |
| MD-14 | **Page-sized chunks (1,500 chars, 200 overlap)** | Every chunk cites exactly one page | Fixed sliding windows across pages | spec s.5 step 4; ingest.py |
| MD-15 | **nomic-embed-text via Ollama, with task prefixes and the file stem in the document text** | Local, small, 768-d; the stem tells the model which device a page belongs to | bge-small (spec alternative) | ingest.py v1 |
| MD-16 | **Hybrid retrieval: vector + bm25, reciprocal-rank fusion, top 6** | Exact tokens (part numbers, torque values, codes) are missed by embeddings alone | Vector only | app.py v1 |
| MD-17 | **Answer model qwen3:8b on the Intel iGPU via Ollama Vulkan** | Measured: CPU 100-125 s to first word vs iGPU ~25-30 s; facts + citations good | qwen3:4b (ignores think:false, rambles: 3,593 tokens / 7.5 min); spec D8's 3-4B default was sized for the Pi | bench 10-03 |
| MD-18 | **Strict grounding prompt, temperature 0.2, think off, numbered `[n]` citations** | the owner wants real facts, verifiable (memory `feedback-verify-against-sources.md`) | Free-form answers | app.py v1 |
| MD-19 | **No auth; LAN / tailnet trust, firewall Private profile only** | Same boundary as the other boat services | Login | spec s.2 |
| MD-20 | **Starts at logon (Task Scheduler), not as a boot service** | Lee: "yes on sign in"; the tray Ollama is per-user anyway | Windows service | 10-04 |
| MD-21 | **Index and corpus are derived and not backed up** (spec D9) | Rebuildable from the manuals, which are backed up elsewhere | Separate backup job | spec D9 |
| MD-22 | **Code in a private repo `hutchel/manuals-rag`, code only** | Corpus / index are copyrighted-derived; the repo carries no Colin content | Public repo; including data | 10-03 |
