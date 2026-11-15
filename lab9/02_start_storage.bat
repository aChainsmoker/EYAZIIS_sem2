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

docker info >nul 2>&1
if errorlevel 1 (
    echo Install and start Docker Desktop, then run this script again.
    goto failed
)

echo Starting PostgreSQL and MinIO using the project configuration...
".venv\Scripts\python.exe" run_storage.py
if errorlevel 1 goto failed

echo Containers started. Wait for PostgreSQL and MinIO to become ready, then run 03_start_indexer.bat.
popd
pause
exit /b 0

:failed
echo Storage startup failed. See the error above.
popd
pause
exit /b 1
