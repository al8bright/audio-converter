@echo off
echo ===================================================
echo   Audio Bitrate Converter - Build Executable
echo ===================================================
echo.

echo [1/2] Activating virtual environment...
if not exist .venv (
    echo [ERROR] .venv folder not found. Please run run_app.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo [2/2] Building single executable with PyInstaller...
echo       This may take 1-2 minutes. Please wait...
echo.

pyinstaller --noconfirm --onefile --windowed --name="AudioConverter" --icon="audio_icon.ico" --add-data ".venv\Lib\site-packages\customtkinter;customtkinter" --collect-all tkinterdnd2 gui_app.py


if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   Build Successful!
echo   Output: c:\Personal\audio_converter\dist\AudioConverter.exe
echo ===================================================
echo.
pause
