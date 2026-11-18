# osetup — cài TRỢ LÝ chạy ngầm (Windows). Không cần quyền admin. Gỡ: Settings > Apps > "osetup — Trợ lý cài phần mềm".
$ErrorActionPreference = "Stop"
$repo   = "Ciro4c/o_setup-phan_mem_ban_dau-"
$branch = "main"
$root   = Join-Path $env:LOCALAPPDATA "osetup-assistant"
$app    = Join-Path $root "app"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Chưa có Python, đang cài qua winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Không tìm thấy Python. Cài Python 3 rồi chạy lại."; return }

# dừng bản cũ (nếu có) để ghi đè
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:47890/uninstall-stop" -Body "{}" -TimeoutSec 3 | Out-Null } catch {}
Start-Sleep -Seconds 1

Write-Host "Đang tải osetup từ github.com/$repo ..."
$zip = Join-Path $env:TEMP "osetup-assistant.zip"
$tmp = Join-Path $env:TEMP "osetup-assistant-src"
Invoke-WebRequest "https://github.com/$repo/archive/refs/heads/$branch.zip" -OutFile $zip -UseBasicParsing
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip -DestinationPath $tmp -Force
$src = Get-ChildItem $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName "osetup") } | Select-Object -First 1
if (-not $src) { Write-Host "Gói tải về không đúng cấu trúc."; return }
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
New-Item -ItemType Directory -Path $root -Force | Out-Null
Move-Item $src.FullName $app
python (Join-Path $app "osetup_main.py") assistant install
Write-Host "Xong. Quay lại trang web: trạng thái sẽ hiện 'Trợ lý đang chạy'."
