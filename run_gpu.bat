@echo off
rem Comic Translate launcher with GPU support.
rem torch cu130 bundles the CUDA 13 DLLs (cublasLt64_13.dll / cudnn64_9.dll)
rem that onnxruntime-gpu 1.30 needs; this script puts them on PATH.
cd /d "%~dp0"
set "PATH=%~dp0.venv\Lib\site-packages\torch\lib;%PATH%"

rem ---- Batch-merge tuning: edit the two numbers, save, relaunch ----
rem Pages per merged LLM request: higher = fewer requests (RPD/RPM divided by it)
set COMIC_TRANSLATE_BATCH_PAGES=6
rem Max text blocks per merged request: guards against overlong output
set COMIC_TRANSLATE_BATCH_BLOCKS=100

"%~dp0.venv\Scripts\python.exe" "%~dp0comic.py" %*
