@echo off
REM Builds a standalone SecureVault.exe (no Python needed on the target PC).
REM Installs the dependencies from requirements.txt (needs internet the first time).

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail

if exist securevault.ico del securevault.ico
python make_icon.py
set ICON=
if exist securevault.ico set ICON=--icon securevault.ico

python -m PyInstaller --noconsole --onefile --name SecureVault %ICON% ^
  --add-data "assets;assets" ^
  --collect-all customtkinter ^
  --hidden-import pystray._win32 ^
  --hidden-import PIL.ImageTk ^
  main.py
if errorlevel 1 goto fail

REM --- put a copy of the program on the real Desktop (works with OneDrive-redirected Desktops too)
set "DESKTOP="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%D"
if defined SV_NOPAUSE set "DESKTOP="
if defined DESKTOP copy /y "dist\SecureVault.exe" "%DESKTOP%\SecureVault.exe" >nul

echo.
echo Done. Your program is: dist\SecureVault.exe
if defined DESKTOP echo A copy was also placed on your Desktop: %DESKTOP%\SecureVault.exe
goto end

:fail
echo.
echo BUILD FAILED. Read the error above. See README.md.

:end
if not defined SV_NOPAUSE pause
