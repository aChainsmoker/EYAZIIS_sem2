@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Creating a Python 3.11 virtual environment...
    py -3.11 -m venv .venv
    if errorlevel 1 goto failed
)

if not exist "config.toml" (
    copy /y "config.example.toml" "config.toml" >nul
    if errorlevel 1 goto failed
    echo Created config.toml. Review its settings before starting the system.
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Downloading NLTK resources...
".venv\Scripts\python.exe" -m nltk.downloader -e stopwords wordnet punkt_tab
if errorlevel 1 goto failed

echo Preparing Argos models EN-RU and RU-EN...
".venv\Scripts\python.exe" -m src.translation.prepare
if errorlevel 1 goto failed

echo Preparing the Whisper model configured in config.toml...
".venv\Scripts\python.exe" -c "import whisper; from src.config import CONFIG; whisper.load_model(CONFIG['whisper']['model'], device='cpu')"
if errorlevel 1 goto failed

echo Setup completed. Next, start Docker Desktop and run 02_start_storage.bat.
popd
pause
exit /b 0

:failed
echo Setup failed. See the error above. Python 3.11 with the py launcher and Internet access are required.
popd
pause
exit /b 1
