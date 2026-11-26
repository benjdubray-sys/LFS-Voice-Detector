@echo off
setlocal
cd /d "%~dp0"

echo === 1/3  Environnement Python 3.12 ===
py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 est introuvable. Installe-le : winget install Python.Python.3.12
  exit /b 1
)
if not exist .venv py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt "pyinstaller>=6"
if errorlevel 1 exit /b 1

echo === 2/3  Application (PyInstaller) ===
pyinstaller --noconfirm --clean lfsvoice.spec
if errorlevel 1 exit /b 1
rem Le dossier build\ contient un LFSVoice.exe INCOMPLET (fichiers intermediaires) : on le supprime.
if exist build rmdir /s /q build
echo Application prete : %cd%\dist\LFSVoice\LFSVoice.exe

echo === 3/3  Installateur (Inno Setup) ===
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo Inno Setup 6 introuvable. Installe-le : winget install JRSoftware.InnoSetup
  echo L'application seule est prete dans dist\LFSVoice\LFSVoice.exe
  exit /b 1
)
"%ISCC%" installer.iss
if errorlevel 1 exit /b 1

echo.
echo Termine. Installateur : installer_output\LFSVoice-Setup.exe
endlocal
