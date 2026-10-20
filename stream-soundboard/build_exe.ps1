# Stream Soundboard を onedir で .exe 化する（起動高速）
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot
py -3 -m PyInstaller --noconfirm --clean build_exe.spec

$exe = Join-Path $PSScriptRoot "dist\StreamSoundboard\StreamSoundboard.exe"
if (-not (Test-Path $exe)) {
    Write-Error "ビルド失敗: $exe が見つかりません"
}
Write-Host "OK: $exe"
Get-Item $exe | Format-List FullName, Length, LastWriteTime
Get-ChildItem (Join-Path $PSScriptRoot "dist\StreamSoundboard") |
    Measure-Object -Property Length -Sum |
    ForEach-Object { Write-Host ("Folder total: {0:N1} MB" -f ($_.Sum / 1MB)) }
