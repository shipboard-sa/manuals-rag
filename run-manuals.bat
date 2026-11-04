@echo off
REM ============================================================
REM  Purpose: Start the boat manuals Q&A service (manuals-rag) on the Ship's PC - http://192.168.1.113:8200
REM  Version: v1 (2026-10-03)
REM  Scope: PRODUCTION-candidate (D-054: runs on the Ship's PC).
REM  Architecture: uvicorn rag.app:app on 0.0.0.0:8200 (Private-profile firewall rule) -> index\manuals.db
REM    (sqlite-vec + FTS5) -> Ollama 127.0.0.1:11434, model qwen3:8b on the Intel iGPU (Vulkan). Needs Ollama
REM    running with OLLAMA_VULKAN=1 and OLLAMA_IGPU_ENABLE=1 (user environment variables) for GPU speed.
REM  Invocation: double-click (desktop icon "Boat Manuals"); close the window to stop.
REM ============================================================
setlocal
cd /d "%~dp0"
netstat -ano | findstr /C:":8200" | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo   The manuals service is already running: http://localhost:8200
  pause
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" ( echo ERROR: no .venv here & pause & exit /b 1 )
if "%MANUALS_LLM%"=="" set "MANUALS_LLM=qwen3:8b"
echo.
echo   Boat manuals - this PC:   http://localhost:8200
echo                  boat LAN:  http://192.168.1.113:8200
echo   Close this window to stop it.
echo.
".venv\Scripts\python.exe" -m uvicorn rag.app:app --host 0.0.0.0 --port 8200
pause
