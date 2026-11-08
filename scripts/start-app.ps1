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
Start-Transcript -Path (Join-Path $logs "launcher.log") -Force | Out-Null

# Pencere gizli: hata olursa sessizce kapanmasin, kullaniciya goster
trap {
    $msg = "Ajanda baslatilamadi:`n$($_.Exception.Message)`n`nAyrinti: $logs\launcher.log"
    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show($msg, "Ajanda", "OK", "Error") | Out-Null
    } catch {}
    Stop-Transcript | Out-Null
    exit 1
}

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Kisayoldan acilinca ortam degiskenleri (APPDATA, PATH) eksik gelebiliyor:
    # klasorleri Windows API'sinden bul
    $roaming = [Environment]::GetFolderPath("ApplicationData")
    $home_ = [Environment]::GetFolderPath("UserProfile")
    $candidates = @(
        (Get-ChildItem "$roaming\Python\Python3*\Scripts\uv.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName),
        "$home_\.local\bin\uv.exe",
        "$home_\.cargo\bin\uv.exe"
    ) | Where-Object { $_ }
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

function Find-Exe($name, [string[]]$candidates) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    return $null
}

$local = [Environment]::GetFolderPath("LocalApplicationData")
# Alt surecler (uv, npm) de bunlara ihtiyac duyar
if (-not $env:APPDATA) { $env:APPDATA = [Environment]::GetFolderPath("ApplicationData") }
if (-not $env:LOCALAPPDATA) { $env:LOCALAPPDATA = $local }
if (-not $env:USERPROFILE) { $env:USERPROFILE = [Environment]::GetFolderPath("UserProfile") }
$npm = Find-Exe "npm.cmd" @("$env:ProgramFiles\nodejs\npm.cmd", "C:\Program Files\nodejs\npm.cmd")
if (-not $npm) { throw "Node.js (npm) bulunamadi" }
# npm, node.exe'yi PATH'te arar
$env:Path = "$(Split-Path $npm);$env:Path"
$ollamaExe = Find-Exe "ollama" @("$local\Programs\Ollama\ollama.exe")

function Test-Port([int]$port) {
    $c = New-Object System.Net.Sockets.TcpClient
    # "localhost": Vite IPv6'yi (::1), uvicorn IPv4'u dinler; ikisini de dener
    try { $c.Connect("localhost", $port); return $true } catch { return $false } finally { $c.Dispose() }
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

function Invoke-Logged($name, $exe, [string[]]$arguments, $dir) {
    $p = Start-Process -Wait -PassThru -WindowStyle Hidden -FilePath $exe -ArgumentList $arguments `
        -WorkingDirectory $dir -RedirectStandardOutput (Join-Path $logs "$name.log") `
        -RedirectStandardError (Join-Path $logs "$name.err.log")
    return $p.ExitCode
}

# --- Ilk calistirmada kendi kendini kur ---
# Claude masaustu uygulamasi icinden kurulanlar (uv, uv'nin Python'u) paketli
# uygulamanin sanal AppData'sina yazildigi icin disaridan gorunmuyor.
$uv = Find-Uv
if (-not $uv) {
    Write-Host "uv kuruluyor (ilk calistirma)..."
    $py = Find-Exe "py" @("C:\Windows\py.exe", "$local\Programs\Python\Launcher\py.exe")
    if (-not $py) { throw "Python bulunamadi (py). python.org'dan Python 3.12+ kur." }
    if ((Invoke-Logged "install-uv" $py @("-m", "pip", "install", "--user", "uv") $root) -ne 0) {
        throw "uv kurulamadi: $logs\install-uv.err.log"
    }
    $uv = Find-Uv
    if (-not $uv) { throw "uv kuruldu ama bulunamadi" }
}

function Sync-Env($name, $dir) {
    # .venv'in Python'u bu oturumda calismiyorsa yeniden kur (gerekirse Python indirir)
    $venvPy = Join-Path $dir ".venv\Scripts\python.exe"
    $ok = $false
    if (Test-Path $venvPy) {
        $ok = (Invoke-Logged "check-$name" $venvPy @("-c", "import sys") $dir) -eq 0
    }
    if (-not $ok) {
        Write-Host "$name ortami kuruluyor..."
        if ((Invoke-Logged "sync-$name" $uv @("sync") $dir) -ne 0) {
            throw "$name ortami kurulamadi: $logs\sync-$name.err.log"
        }
    }
}
# task-api ve asistan varsayilan olarak kendi SQLite dosyalarini kullanir

# Ollama (local modeller)
if (-not (Test-Port 11434)) {
    if ($ollamaExe) { Start-Process -WindowStyle Hidden -FilePath $ollamaExe -ArgumentList "serve" | Out-Null }
}

$taskApi = Join-Path $root "services/task-api"
$assistant = Join-Path $root "services/assistant-service"
$web = Join-Path $root "apps/web"

if (-not (Test-Port 8000)) {
    Sync-Env "task-api" $taskApi
    Invoke-Migration "task-api" $taskApi
    Start-Hidden "task-api" $uv @("run", "uvicorn", "app.main:app", "--port", "8000") $taskApi
}
if (-not (Test-Port 8100)) {
    Sync-Env "assistant" $assistant
    Invoke-Migration "assistant" $assistant
    Start-Hidden "assistant" $uv @("run", "uvicorn", "app.main:app", "--port", "8100") $assistant
}
if (-not (Test-Port 5173)) {
    if (-not (Test-Path (Join-Path $web "node_modules"))) {
        Start-Process -Wait -WindowStyle Hidden -FilePath $npm -ArgumentList "install" -WorkingDirectory $web | Out-Null
    }
    Start-Hidden "web" $npm @("run", "dev", "--", "--port", "5173", "--strictPort") $web
}

# Hazir olana kadar bekle (en fazla ~90 sn), sonra tarayicida ac
foreach ($p in 8000, 8100, 5173) {
    for ($i = 0; $i -lt 90 -and -not (Test-Port $p); $i++) { Start-Sleep -Seconds 1 }
}
$down = @(8000, 8100, 5173 | Where-Object { -not (Test-Port $_) })
if ($down.Count) { throw "Su portlar acilmadi: $($down -join ', '). Kayitlar: $logs" }
Start-Process "http://localhost:5173"
Stop-Transcript | Out-Null
