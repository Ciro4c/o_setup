@echo off
chcp 65001 >nul
rem Bam dup file nay: add + commit + pull + push len GitHub (thay cho VS Code).
rem Bot tren GitHub tu cap nhat docs/index.html, top.json, stars_cache.json; neu trung thi uu tien ban cua bot
rem (bot se tu dung lai trang sau khi push).
cd /d "%~dp0"
git add -A
git commit -m "update %date% %time%" 2>nul || echo (khong co thay doi moi)
git pull --no-rebase --no-edit -X theirs
git push
echo.
echo Xong. Doi 1-2 phut de trang web cap nhat.
pause
