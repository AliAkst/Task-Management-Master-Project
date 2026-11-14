# Ortak yardimcilar (start-app.ps1, install-tasks.ps1, restore.ps1 dot-source eder)

function Get-RepoRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Kisayoldan/gorev zamanlayicidan acilinca ortam degiskenleri (APPDATA, PATH) eksik
    # gelebiliyor: klasorleri Windows API'sinden bul
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
