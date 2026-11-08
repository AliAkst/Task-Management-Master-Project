<#
.SYNOPSIS
  Ajanda'yi gunluk kullanim icin baslatir: servisleri arka planda (pencere
  acmadan) calistirir, hazir olunca uygulamayi tarayicida acar.

.DESCRIPTION
  - Zaten calisan servis (port dolu) tekrar baslatilmaz; ikinci tiklama sadece
    tarayiciyi acar.
  - Ollama kapaliysa baslatir (local modeller icin).
  - Kayitlar: scripts/logs/*.log. Durdurmak icin: scripts/stop-app.ps1
  - Masaustu kisayolu: scripts/install-shortcut.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:APPDATA\Python\Python313\Scripts\uv.exe",
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    throw "uv bulunamadi. Kurulum: py -m pip install --user uv"
}

function Test-Port([int]$port) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { $c.Connect("127.0.0.1", $port); return $true } catch { return $false } finally { $c.Dispose() }
}

function Invoke-Migration($name, $dir) {
    # Ayri surec: alembic bilgi mesajlarini stderr'e yazar, PS 5.1 bunu hata sayar
    $p = Start-Process -Wait -PassThru -WindowStyle Hidden -FilePath $uv `
        -ArgumentList @("run", "alembic", "upgrade", "head") -WorkingDirectory $dir `
        -RedirectStandardOutput (Join-Path $logs "migrate-$name.log") -RedirectStandardError (Join-Path $logs "migrate-$name.err.log")
    if ($p.ExitCode -ne 0) { throw "$name migration basarisiz: scripts\logs\migrate-$name.err.log" }
}

function Start-Hidden($name, $exe, $arguments, $dir) {
    Start-Process -WindowStyle Hidden -FilePath $exe -ArgumentList $arguments -WorkingDirectory $dir `
        -RedirectStandardOutput (Join-Path $logs "$name.log") -RedirectStandardError (Join-Path $logs "$name.err.log") | Out-Null
}

$uv = Find-Uv
# task-api ve asistan varsayilan olarak kendi SQLite dosyalarini kullanir

# Ollama (local modeller)
if (-not (Test-Port 11434)) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollama) { Start-Process -WindowStyle Hidden -FilePath $ollama.Source -ArgumentList "serve" | Out-Null }
}

$taskApi = Join-Path $root "services/task-api"
$assistant = Join-Path $root "services/assistant-service"
$web = Join-Path $root "apps/web"

if (-not (Test-Port 8000)) {
    Invoke-Migration "task-api" $taskApi
    Start-Hidden "task-api" $uv @("run", "uvicorn", "app.main:app", "--port", "8000") $taskApi
}
if (-not (Test-Port 8100)) {
    Invoke-Migration "assistant" $assistant
    Start-Hidden "assistant" $uv @("run", "uvicorn", "app.main:app", "--port", "8100") $assistant
}
if (-not (Test-Port 5173)) {
    if (-not (Test-Path (Join-Path $web "node_modules"))) {
        Start-Process -Wait -WindowStyle Hidden -FilePath "npm.cmd" -ArgumentList "install" -WorkingDirectory $web | Out-Null
    }
    Start-Hidden "web" "npm.cmd" @("run", "dev", "--", "--port", "5173", "--strictPort") $web
}

# Hazir olana kadar bekle (en fazla ~60 sn), sonra tarayicida ac
foreach ($p in 8000, 8100, 5173) {
    for ($i = 0; $i -lt 60 -and -not (Test-Port $p); $i++) { Start-Sleep -Seconds 1 }
}
Start-Process "http://localhost:5173"
