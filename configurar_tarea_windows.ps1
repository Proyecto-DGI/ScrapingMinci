# ============================================================
# configurar_tarea_windows.ps1
# Crea la tarea programada en Windows automáticamente.
# Ejecutar UNA sola vez como Administrador.
# ============================================================
#
# Para ejecutar:
#   1. Click derecho en este archivo → "Ejecutar con PowerShell como administrador"
#   O desde PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\configurar_tarea_windows.ps1
# ============================================================

# CAMBIAR esta ruta a donde está tu proyecto
$rutaProyecto = "C:\ScraperDGI\ScrapingMinci"
$rutaBat = "$rutaProyecto\ejecutar_scraper.bat"

# Crear carpeta de logs si no existe
New-Item -ItemType Directory -Force -Path "$rutaProyecto\logs" | Out-Null

# Configuración de la tarea
$nombreTarea   = "ScienTI_Scraper_UPB"
$descripcion   = "Actualización automática de datos de investigación desde MinCiencias"
$intervalo     = 14   # días entre ejecuciones

# Crear el trigger (cada 14 días, a las 2:00 AM para no interferir con trabajo)
$trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Days $intervalo) `
    -At "2:00AM" `
    -Once `
    -RepetitionDuration ([System.TimeSpan]::MaxValue)

# Acción a ejecutar
$accion = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$rutaBat`"" `
    -WorkingDirectory $rutaProyecto

# Configuración: correr aunque el usuario no esté logueado
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable   # Si el PC estaba apagado, corre cuando vuelva

# Registrar la tarea
Register-ScheduledTask `
    -TaskName $nombreTarea `
    -Description $descripcion `
    -Trigger $trigger `
    -Action $accion `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "✅ Tarea '$nombreTarea' creada exitosamente" -ForegroundColor Green
Write-Host "   Frecuencia: cada $intervalo días a las 2:00 AM"
Write-Host "   Logs en: $rutaProyecto\logs\"
Write-Host ""
Write-Host "Para verificar: Busca 'Programador de tareas' en Windows"
Write-Host "Para probar ahora: click derecho en la tarea → Ejecutar"
