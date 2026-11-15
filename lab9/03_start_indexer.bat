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

echo Starting the indexer. Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -u -m src.indexer
if errorlevel 1 goto failed

popd
pause
exit /b 0

:failed
echo Indexer startup or execution failed. See the error above.
popd
pause
exit /b 1
