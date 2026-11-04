<!--
Purpose: The manuals LLM host (the Ship's PC) - hardware, software stack, configuration, and a from-blank rebuild
  procedure.
Version: v1 (2026-10-07) - v1: created in the rebuild-from-spec wiki pass from Ship's Automation
  docs/Ships-PC-Setup.md (10-03 / 10-04 / 10-05 entries, read-only), network.md and the manuals-rag repo.
Scope: PRODUCTION-candidate - documentation for manuals-rag (D-054: runs on the Ship's PC).
Architecture: code/manuals-rag/wiki/. The Ship's PC as a whole (backups, mx-inv, Docker bench, shares) is
  documented in Ships-PC-Setup.md; this page covers only what manuals-rag needs.
Invocation: n/a (reference doc)
-->

# LLM host - the Ship's PC

## Hardware and status

| Item | Value | Source |
|---|---|---|
| Machine | MSI Cubi NUC 1M (MS-B0B1), Intel Core 5 120U (10 cores), 32 GB RAM, Windows 11 Pro, hostname `SHIP_PC` | Ships-PC-Setup.md:2, :86; mx-inv item #665 |
| GPU used | Intel integrated graphics ("Intel(R) Graphics") through Ollama's Vulkan backend - no discrete GPU | Ships-PC-Setup.md:262, :310 |
| Network | 192.168.1.113, wired, DHCP reservation; its USB Wi-Fi also appears as .208 (to be disabled) | network.md:94 |
| Storage | internal SSD (ADATA LEGEND 800) = Windows; **E:** = external Seagate Portable 5 TB (serial NT36Y2YC, label Data) holding `E:\boat\...` | Ships-PC-Setup.md:728, :342; memory `vessel-ops-multiuser-hosting.md` |
| Power | 24 -> 19 V buck converter off the ship's DC system (a larger replacement, mx-inv item #1569, is planned because the old one, #1194, is too small for the 120 W adapter / 55 W turbo) | memory `vessel-specs.md`; mx-inv item #1569 |
| Physical location | **ASSUMED - ask Lee** (not found in the stores; Ships-PC-Setup.md:86 notes the Pi is mounted above the PC's USB hub). the owner's as-built PPT slides 16-17 describe its role (GUI host, media store, on-board backup). | recall `--store ppt` |
| Status 2026-11-02 | **Running.** Back from MSI RMA, rebuilt. manuals-rag v4 live on :8200. | |

## Software stack (as built 2026-10-03)

| Piece | Version / setting |
|---|---|
| Python | 3.14.7 (`py -3.14`), venv `E:\boat\manuals-rag\.venv` |
| Python packages | `requirements.txt` v2: pymupdf 1.28.2, sqlite-vec 0.1.9, fastapi 0.141.1, uvicorn[standard] 0.52.4 |
| Ollama | 0.35.1, Windows tray app, API on 127.0.0.1:11434 |
| Models | `qwen3:8b` (answers), `nomic-embed-text` (embeddings); `qwen3:4b` was pulled for the benchmark and rejected |
| Ollama user env vars | `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1` (GPU offload), `OLLAMA_KEEP_ALIVE=30m` (models stay loaded 30 min) |
| Tesseract | 5.4 (UB-Mannheim build) at `C:\Program Files\Tesseract-OCR`, tessdata beside it - only for `ocr_corpus.py` |
| Firewall | inbound rule `manuals-rag chat (TCP 8200)`, Private profile |
| Auto-start | Task Scheduler task **"boat manuals"** -> `E:\boat\manuals-rag\run-manuals.bat`, at logon of user hutch, minimized console (close = stop). Created by SwallowAutomation `deploy/shipspc/native-apps.ps1` (called by `deploy.ps1` v7). |
| Desktop icon | "Boat Manuals" -> `run-manuals.bat` (manual restart) |

| `BRAVE_API_KEY` | (none) | the owner sets | Brave Search API key (enables `/api/web` web search proxy) |

No other secrets are used by manuals-rag.

## Rebuild from blank

Prerequisites: the PC on the boat LAN at 192.168.1.113 with Windows set up and the user signed in; E: attached
(or the project re-copied); internet for the downloads (Starlink: "residential - unlimited", owner, Oct 2026).

1. **Python 3.14** - install, then in `E:\boat\manuals-rag`:
   `py -3.14 -m venv .venv` and `.venv\Scripts\python -m pip install -r requirements.txt`.
   (If E: is lost: `git clone` private `hutchel/manuals-rag` to `E:\boat\manuals-rag` and copy the library to
   `E:\boat\Manuals` from the laptop master.)
2. **Ollama** - install the Windows app. Do **not** run plain `ollama` in a terminal: in 0.35.1 it opens a launcher
   that installed the Claude Code CLI and offered cloud models (Ships-PC-Setup.md:254; cloud models break spec D2).
   Pull explicitly: `ollama pull qwen3:8b` and `ollama pull nomic-embed-text`.
3. **GPU env vars** - set as **user** environment variables (System Properties, not an elevated shell):
   `OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, `OLLAMA_KEEP_ALIVE=30m`. Then quit the tray Ollama, restart
   Windows Explorer (Task Manager) or sign out/in, and start Ollama again - values saved from an elevated shell did
   not reach the running desktop session on 10-03. Verify in Ollama's `server.log`: the iGPU is listed via Vulkan,
   keep-alive 30m, and on the first answer "37/37 layers offloaded".
4. **Tesseract** (only if OCR must be redone): UB-Mannheim 5.x installer to `C:\Program Files\Tesseract-OCR`
   (UAC prompt - the owner approves).
5. **Corpus** - if `corpus\` survived on E:, skip. Otherwise: `extract\extract_corpus.py --root E:\boat\Manuals`,
   then `extract\ocr_corpus.py --root E:\boat\Manuals` (the 16 image-only manuals; the Yanmar 454-page book takes
   the longest).
6. **Index** - if `index\manuals.db` survived, run `rag\ingest.py` anyway (incremental, cheap). Otherwise
   `rag\ingest.py --force`. Expect ~255 documents / ~10,100 chunks (more if manuals were added).
7. **Firewall** (Lee, admin): inbound TCP 8200, Private profile, named `manuals-rag chat (TCP 8200)`. Check the
   network profile is **Private** - the 10-07 router swap flipped the laptop to Public and blocked the LAN
   (memory `vessel-ops-multiuser-hosting.md`).
8. **Auto-start** - rerun SwallowAutomation `deploy/shipspc/native-apps.ps1` (creates "boat manuals" and "boat mx-inv"),
   or create the task by hand: at logon of hutch, action `E:\boat\manuals-rag\run-manuals.bat`. Add the desktop
   icon.
9. **Verify** - `http://localhost:8200/api/health` shows the document / chunk counts and `"llm":"qwen3:8b"`; ask one
   question at `http://192.168.1.113:8200` from the tablet (expect ~100 s cold, ~1 min warm); the landing page
   tile "Boat manuals" turns green.

## Load and safety notes

- A question pins CPU + iGPU for about a minute. The PC died during such a load on 10-05; the RMA returned it
  without a diagnosis. No load limits added.
- Idle `llama-server` runners can linger (~1.5 GB seen 10-03); ending them is safe, Ollama reloads on demand.
- The PC also hosts mx-inv, the Docker bench, backups; the WSL2 memory cap (`%USERPROFILE%\.wslconfig`
  `memory=6GB`) keeps Docker from starving Ollama (Ships-PC-Setup.md, 10-03 memory tidy).
