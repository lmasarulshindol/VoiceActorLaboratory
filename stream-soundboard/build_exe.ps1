# Stream Soundboard を .exe 化する
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot
py -3 -m PyInstaller --noconfirm --clean build_exe.spec

$exe = Join-Path $PSScriptRoot "dist\StreamSoundboard.exe"
if (-not (Test-Path $exe)) {
    Write-Error "ビルド失敗: $exe が見つかりません"
}
Write-Host "OK: $exe"
Get-Item $exe | Format-List FullName, Length, LastWriteTime
