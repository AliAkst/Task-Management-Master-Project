<#
.SYNOPSIS
  Masaustune "Ajanda" (baslat) ve "Ajanda'yı durdur" kisayollarini olusturur.
  Bir kez calistirman yeterli: powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
#>
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function New-Shortcut($name, $script, $icon) {
    $lnk = $shell.CreateShortcut((Join-Path $desktop "$name.lnk"))
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot $script)`""
    $lnk.WorkingDirectory = Split-Path -Parent $PSScriptRoot
    $lnk.IconLocation = $icon
    $lnk.Save()
    Write-Host "Olusturuldu: $(Join-Path $desktop "$name.lnk")"
}

New-Shortcut "Ajanda" "start-app.ps1" "$env:SystemRoot\System32\shell32.dll,165"
New-Shortcut "Ajanda - Durdur" "stop-app.ps1" "$env:SystemRoot\System32\shell32.dll,27"

