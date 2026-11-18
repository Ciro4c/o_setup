@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo === osetup: kéo thư viện và build osetup.exe ===

where python >nul 2>nul
if errorlevel 1 (
  echo Chua co Python, dang cai qua winget...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  echo Da cai Python. HAY DONG CUA SO NAY, MO LAI VA CHAY build.bat LAN NUA.
  pause
  exit /b 1
)

python -m pip install --upgrade pip pyinstaller || goto :err
python -m unittest discover -s tests || goto :err

python -m PyInstaller --noconfirm --clean --onefile --uac-admin --name osetup ^
  --add-data "osetup\data;osetup\data" ^
  --collect-submodules osetup --hidden-import tkinter ^
  osetup_main.py || goto :err

if exist dist\osetup.exe (
  echo.
  echo XONG: %~dp0dist\osetup.exe
  echo Nhap dup de mo GUI, hoac chay: osetup.exe install student office -y
  echo Dat file custom.json canh osetup.exe de them phan mem rieng.
) else (
  goto :err
)
pause
exit /b 0

:err
echo.
echo BUILD LOI - xem thong bao phia tren.
pause
exit /b 1
