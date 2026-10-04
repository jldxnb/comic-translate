@echo off
rem Comic Translate launcher with GPU support.
rem torch cu130 bundles the CUDA 13 DLLs (cublasLt64_13.dll / cudnn64_9.dll)
rem that onnxruntime-gpu 1.30 needs; this script puts them on PATH.
cd /d "%~dp0"
set "PATH=%~dp0.venv\Lib\site-packages\torch\lib;%PATH%"

rem ---- 合并翻译调参（可改，改完保存重新启动即可生效）----
rem 每次合并请求包含的页数：越大越省额度（RPD/RPM 都除以它），但译文质量略降
set COMIC_TRANSLATE_BATCH_PAGES=6
rem 单次请求的文本块上限：防止输出超长被截断，一般不用动
set COMIC_TRANSLATE_BATCH_BLOCKS=100

"%~dp0.venv\Scripts\python.exe" "%~dp0comic.py" %*
