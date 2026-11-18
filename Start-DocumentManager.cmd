@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Document Manager's virtual environment is missing. Follow the Windows setup in README.md.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m document_manager %*
