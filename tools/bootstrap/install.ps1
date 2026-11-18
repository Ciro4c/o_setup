# osetup — cài nhanh 1 dòng lệnh (Windows). Mở PowerShell bằng "Run as administrator", rồi:
#   $env:OSETUP_ARGS='install student office -y'; irm https://<user>.github.io/<repo>/install.ps1 | iex
# Không đặt OSETUP_ARGS thì mở giao diện đồ hoạ (gui). Thêm -n để chạy thử, không cài gì.
$ErrorActionPreference = "Stop"
$repo   = "Ciro4c/o_setup-phan_mem_ban_dau-"
$branch = "main"
$dir    = Join-Path $env:LOCALAPPDATA "osetup"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Chưa có Python, đang cài qua winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Không tìm thấy Python. Cài Python 3 rồi chạy lại."; return }

Write-Host "Đang tải osetup từ github.com/$repo ..."
$zip = Join-Path $env:TEMP "osetup.zip"
Invoke-WebRequest "https://github.com/$repo/archive/refs/heads/$branch.zip" -OutFile $zip -UseBasicParsing
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
Expand-Archive $zip -DestinationPath $dir -Force
$src = Get-ChildItem $dir -Directory | Where-Object { Test-Path (Join-Path $_.FullName "osetup") } | Select-Object -First 1
if (-not $src) { Write-Host "Gói tải về không đúng cấu trúc."; return }

$a = @($env:OSETUP_ARGS -split '\s+' | Where-Object { $_ })
if ($a.Count -eq 0) { $a = @("gui") }
Set-Location $src.FullName
python -m osetup @a
