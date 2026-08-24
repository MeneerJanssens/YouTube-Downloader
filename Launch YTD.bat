@echo off
rem Dev launcher: make sure yt-dlp is present, then run the app.
py -m pip show yt-dlp >nul 2>&1
if errorlevel 1 (
    echo Installing yt-dlp...
    py -m pip install yt-dlp
    if errorlevel 1 (
        echo Failed to install yt-dlp. Run: py -m pip install yt-dlp
        pause
        exit /b 1
    )
)
py "%~dp0ytd.py"
