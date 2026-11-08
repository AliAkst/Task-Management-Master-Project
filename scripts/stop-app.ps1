<#
.SYNOPSIS
  start-app.ps1 ile baslatilan Ajanda servislerini durdurur (8000, 8100, 5173).
  Ollama'ya dokunmaz.
#>
foreach ($port in 8000, 8100, 5173) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $owners) {
        # uv/npm ust surecleriyle birlikte kapat
        & taskkill.exe /PID $procId /T /F | Out-Null
        Write-Host "Port $port durduruldu (PID $procId)"
    }
}
