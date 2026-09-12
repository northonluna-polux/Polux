@echo off
REM ============================================================================
REM  Compilacion del ejecutable de Polux para Windows.
REM
REM  Reproduce manualmente lo que hace el flujo de GitHub Actions
REM  (.github/workflows/build.yml). Ejecutar desde la raiz del proyecto:
REM
REM      scripts\construir_ejecutable.bat
REM
REM  Requiere Python 3.12 instalado y accesible en el PATH.
REM  El resultado queda en dist\Polux-<version>.exe
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo === Polux: compilacion del ejecutable para Windows ===
echo Directorio de trabajo: %CD%
echo.

REM --- Comprobar que Python esta disponible ---------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: no se encuentra Python en el PATH.
    echo Instala Python 3.12 desde https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version') do echo Python detectado: %%v

REM --- Entorno virtual aislado ----------------------------------------------
if not exist ".venv-build" (
    echo.
    echo Creando entorno virtual .venv-build ...
    python -m venv .venv-build
    if errorlevel 1 (
        echo ERROR: no se pudo crear el entorno virtual.
        exit /b 1
    )
)

call .venv-build\Scripts\activate.bat

REM --- Dependencias ----------------------------------------------------------
echo.
echo Instalando dependencias ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: fallo la instalacion de las dependencias.
    exit /b 1
)

python -m pip install pyinstaller==6.22.2
if errorlevel 1 (
    echo ERROR: fallo la instalacion de PyInstaller.
    exit /b 1
)

REM --- Compilacion -----------------------------------------------------------
echo.
echo Compilando con polux.spec ...
pyinstaller --clean --noconfirm polux.spec
if errorlevel 1 (
    echo ERROR: fallo la compilacion.
    exit /b 1
)

REM --- Resultado -------------------------------------------------------------
echo.
echo === Resultado ===
if exist "dist\*.exe" (
    dir /b dist\*.exe
    for %%f in (dist\*.exe) do echo Tamano: %%~zf bytes
    echo.
    echo Ejecutable generado correctamente en la carpeta dist\
) else (
    echo ERROR: no se ha generado ningun .exe en dist\
    exit /b 1
)

endlocal
