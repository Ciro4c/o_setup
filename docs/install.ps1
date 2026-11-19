# osetup - cai nhanh 1 dong lenh (Windows). Mo PowerShell bang "Run as administrator", roi:
#   $env:OSETUP_ARGS='install student office -y'; irm https://<user>.github.io/<repo>/install.ps1 | iex
# Khong dat OSETUP_ARGS thi mo giao dien do hoa (gui). Them -n de chay thu, khong cai gi.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = if ($env:OSETUP_REPO) { $env:OSETUP_REPO } else { "Ciro4c/o_setup" }
$dir  = Join-Path $env:LOCALAPPDATA "osetup"

function Get-Repo([string]$dest) {
    $urls = @(
        "https://github.com/$repo/archive/HEAD.zip",
        "https://codeload.github.com/$repo/zip/HEAD",
        "https://github.com/$repo/archive/refs/heads/main.zip",
        "https://github.com/$repo/archive/refs/heads/master.zip"
    )
    foreach ($u in $urls) {
        try { Invoke-WebRequest $u -OutFile $dest -UseBasicParsing; return }
        catch { Write-Host "  khong tai duoc: $u -> $($_.Exception.Message)" }
    }
    throw "Khong tai duoc ma nguon tu github.com/$repo (repo phai Public va da co osetup_main.py o thu muc goc)."
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Chua co Python, dang cai qua winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Khong tim thay Python. Cai Python 3 roi chay lai."; return }

Write-Host "Dang tai osetup tu github.com/$repo ..."
$zip = Join-Path $env:TEMP "osetup.zip"
Get-Repo $zip
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
Expand-Archive $zip -DestinationPath $dir -Force
$src = Get-ChildItem $dir -Directory | Where-Object { Test-Path (Join-Path $_.FullName "osetup_main.py") } | Select-Object -First 1
if (-not $src) { throw "Goi tai ve khong co osetup_main.py - repo chua duoc day du len GitHub?" }

$a = @($env:OSETUP_ARGS -split '\s+' | Where-Object { $_ })
if ($a.Count -eq 0) { $a = @("gui") }
Set-Location $src.FullName
python -m osetup @a
