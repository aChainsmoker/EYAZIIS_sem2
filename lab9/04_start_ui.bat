@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Run 01_setup.bat first.
    goto failed
)
if not exist "config.toml" (
    echo Run 01_setup.bat and review config.toml first.
    goto failed
)

echo Starting Streamlit at http://localhost:8501
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 goto failed

popd
pause
exit /b 0

:failed
echo UI startup or execution failed. See the error above.
popd
pause
exit /b 1
