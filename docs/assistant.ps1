# osetup - cai TRO LY chay ngam (Windows). Khong can quyen admin.
# Go: Settings > Apps > "osetup - Tro ly cai phan mem" (hoac nut "Go tro ly" tren trang web).
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = if ($env:OSETUP_REPO) { $env:OSETUP_REPO } else { "Ciro4c/o_setup-phan_mem_ban_dau-" }
$root = Join-Path $env:LOCALAPPDATA "osetup-assistant"
$app  = Join-Path $root "app"

function Get-Repo([string]$dest) {
    # HEAD = nhanh mac dinh, khong phu thuoc ten nhanh. Thu lan luot cac dia chi.
    $urls = @(
        "https://github.com/$repo/archive/HEAD.zip",
        "https://codeload.github.com/$repo/zip/HEAD",
        "https://github.com/$repo/archive/refs/heads/main.zip",
        "https://github.com/$repo/archive/refs/heads/master.zip"
    )
    foreach ($u in $urls) {
        try {
            Invoke-WebRequest $u -OutFile $dest -UseBasicParsing
            return
        } catch {
            Write-Host "  khong tai duoc: $u -> $($_.Exception.Message)"
        }
    }
    throw "Khong tai duoc ma nguon tu github.com/$repo. Kiem tra: repo phai o che do Public va da co file osetup_main.py o thu muc goc."
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Chua co Python, dang cai qua winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Khong tim thay Python. Cai Python 3 roi chay lai."; return }

# dung ban cu (neu co) de ghi de
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:47890/uninstall-stop" -Body "{}" -TimeoutSec 3 | Out-Null } catch {}
Start-Sleep -Seconds 1

Write-Host "Dang tai osetup tu github.com/$repo ..."
$zip = Join-Path $env:TEMP "osetup-assistant.zip"
$tmp = Join-Path $env:TEMP "osetup-assistant-src"
Get-Repo $zip
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip -DestinationPath $tmp -Force
$src = Get-ChildItem $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName "osetup_main.py") } | Select-Object -First 1
if (-not $src) { throw "Goi tai ve khong co osetup_main.py - repo chua duoc day du len GitHub?" }
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
New-Item -ItemType Directory -Path $root -Force | Out-Null
Move-Item $src.FullName $app
Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
# cho phep trang web (noi ban bam nut cai) dieu khien tro ly: origin trang + github.io cua repo
$origins = @("https://" + $repo.Split("/")[0].ToLower() + ".github.io")
if ($env:OSETUP_ORIGIN) { $origins += $env:OSETUP_ORIGIN }
$oa = @(); foreach ($o in $origins) { $oa += @("--origin", $o) }
python (Join-Path $app "osetup_main.py") assistant install @oa
Write-Host "Xong. Quay lai trang web: trang thai se hien 'Tro ly dang chay'."
