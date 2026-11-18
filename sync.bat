@echo off
chcp 65001 >nul
rem Bấm đúp file này: tự add + commit + push mọi thay đổi lên GitHub (thay cho thao tác trong VS Code).
cd /d "%~dp0"
git pull --rebase --autostash
git add -A
git commit -m "update %date% %time%" 2>nul || echo (khong co thay doi moi)
git push
echo.
echo Xong. Doi 1-2 phut de trang web cap nhat.
pause
