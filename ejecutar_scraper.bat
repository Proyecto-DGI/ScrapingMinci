@echo off
REM ============================================================
REM ejecutar_scraper.bat
REM Script para ejecutar el scraper automáticamente.
REM Configurar en el Programador de Tareas de Windows.
REM ============================================================

REM Ir al directorio del proyecto (CAMBIAR esta ruta)
cd /d "C:\Users\parra\Downloads\scienti_scraper\scienti_scraper"

REM Activar entorno virtual si tienes uno (opcional)
REM call venv\Scripts\activate

REM Ejecutar el scraper en modo completo
python main.py --mode both >> logs\scraper_%date:~-4,4%%date:~-7,2%%date:~0,2%.log 2>&1

REM El resultado queda en logs\scraper_YYYYMMDD.log
echo Scraper ejecutado: %date% %time% >> logs\historial.log
