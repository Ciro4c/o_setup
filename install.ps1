# Bootstrap cho Windows: cài Python nếu thiếu rồi chạy osetup. Dùng: .\install.ps1 [lệnh osetup...]
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Chưa có Python, đang cài qua winget..."
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
python -m osetup @args
