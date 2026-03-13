@echo off
REM ============================================================================
REM  ComfyUI-FFMPEGA — Install ALL Optional Dependencies (Windows)
REM ============================================================================
REM
REM  Usage (from ComfyUI root, with venv activated):
REM    custom_nodes\ComfyUI-FFMPEGA\install-all-deps.bat
REM
REM  Or double-click this file if your ComfyUI venv Python is on PATH.
REM
REM ============================================================================

setlocal enabledelayedexpansion

REM --- Detect Python ---
if defined PYTHON (
    set "PY=%PYTHON%"
) else if exist "%~dp0..\..\python_embeded\python.exe" (
    REM ComfyUI portable/standalone embed
    set "PY=%~dp0..\..\python_embeded\python.exe"
) else if exist "%~dp0..\..\venv\Scripts\python.exe" (
    REM Standard venv
    set "PY=%~dp0..\..\venv\Scripts\python.exe"
) else (
    set "PY=python"
)

set "PIP=%PY% -m pip install --quiet"
set "SCRIPT_DIR=%~dp0"

echo ============================================
echo   FFMPEGA — Installing ALL optional deps
echo ============================================
for /f "tokens=*" %%i in ('%PY% --version 2^>^&1') do echo Python: %%i
echo.

REM --- Step 1: Git packages (--no-deps) ---
echo [1/3] Installing git packages (--no-deps)...

echo   -^> SAM3...
%PIP% --no-deps git+https://github.com/facebookresearch/sam3.git >nul 2>&1 && (
    echo   √ SAM3
) || (
    echo   X SAM3 failed ^(non-critical^)
)

echo   -^> MMAudio...
%PIP% --no-deps git+https://github.com/hkchengrex/MMAudio.git >nul 2>&1 && (
    echo   √ MMAudio
) || (
    echo   X MMAudio failed
)

echo   -^> AudioX...
%PIP% --no-deps git+https://github.com/ZeyueT/AudioX.git >nul 2>&1 && (
    echo   √ AudioX
) || (
    echo   X AudioX failed
)

echo   -^> SAM-Audio...
%PIP% --no-deps git+https://github.com/facebookresearch/sam-audio.git >nul 2>&1 && (
    echo   √ SAM-Audio
) || (
    echo   X SAM-Audio failed
)

echo   -^> dacvae...
%PIP% --no-deps git+https://github.com/facebookresearch/dacvae.git >nul 2>&1 && (
    echo   √ dacvae
) || (
    echo   X dacvae failed
)

echo   -^> perception_models...
%PIP% --no-deps git+https://github.com/facebookresearch/perception_models@unpin-deps >nul 2>&1 && (
    echo   √ perception_models
) || (
    echo   X perception_models failed
)

REM --- Step 2: Pip packages from requirements ---
echo.
echo [2/3] Installing pip packages...
%PIP% -r "%SCRIPT_DIR%requirements-optional.txt" && (
    echo   √ All pip packages installed
) || (
    echo   X Some pip packages failed
)

REM --- Step 3: Verify ---
echo.
echo [3/3] Verifying imports...
%PY% -c "failures = []; mods = ['sam3','simple_lama_inpainting','mmaudio','sam_audio','dacvae','torchdiffeq','xformers','torchcodec','pydub']; [(__import__(m), print(f'  + {m}')) if not failures.append(None) or True else None for m in mods if not (lambda m: (globals().update({'_ok': True}), __import__(m), print(f'  + {m}')))(m) if False else True]; print()" 2>nul
REM Simpler verification fallback
%PY% -c "ok=0; fail=0; mods=['sam3','simple_lama_inpainting','mmaudio','sam_audio','dacvae','torchdiffeq','xformers','torchcodec','pydub'];exec('for m in mods:\n try:\n  __import__(m);print(f\"  + {m}\");ok+=1\n except:print(f\"  X {m}\");fail+=1');print(f'\n  {ok} passed, {fail} failed')"

echo.
echo ============================================
echo   Done! Restart ComfyUI to use new features.
echo ============================================
echo.
pause
