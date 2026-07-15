@echo off
setlocal
echo Building modkit.exe...
cd /d "%~dp0"
set "LOCAL_BIN=%USERPROFILE%\.local\bin"
uv run --with pyinstaller pyinstaller modkit.spec --noconfirm
if errorlevel 1 (
    echo Build failed!
    exit /b 1
)
if exist modkit.exe del /Q modkit.exe
if exist _internal rmdir /S /Q _internal
move /Y dist\modkit\modkit.exe .
move /Y dist\modkit\_internal .
if not exist "%LOCAL_BIN%" mkdir "%LOCAL_BIN%"
copy /Y modkit.exe "%LOCAL_BIN%\modkit.exe"
if exist "%LOCAL_BIN%\_internal" rmdir /S /Q "%LOCAL_BIN%\_internal"
xcopy /E /I /Y _internal "%LOCAL_BIN%\_internal" >NUL
echo Done: modkit.exe + _internal\ promoted to repo root and %LOCAL_BIN%
