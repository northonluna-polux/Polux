# -*- mode: python ; coding: utf-8 -*-
"""
Configuración de PyInstaller para generar el ejecutable de Polux.

Se usa un archivo .spec en lugar de opciones de línea de órdenes para que
la compilación sea reproducible: todo lo que necesita el paquete queda
declarado aquí y versionado en el repositorio.

Compilar con:

    pyinstaller --clean --noconfirm polux.spec

Está pensado para Windows (ejecutable de un solo archivo, sin consola),
pero funciona en cualquier plataforma. PyInstaller **no** compila para
otras plataformas: para obtener el .exe de Windows hay que compilar en
Windows, que es lo que hace el flujo de trabajo de GitHub Actions.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

sys.path.insert(0, os.path.abspath("."))
from version import DESCRIPCION, NOMBRE_APLICACION, VERSION  # noqa: E402

# --- Recursos que la aplicación necesita en tiempo de ejecución ---------------

# El CSV de clientes de ejemplo se empaqueta para que la aplicación sea
# utilizable nada más instalarla, sin tener que buscar datos por internet.
datos_aplicacion = [
    ("datos/clientes_ejemplo.csv", "datos"),
    ("datos/clientes_interurbano.csv", "datos"),
]

# --- Dependencias que PyInstaller no detecta por sí solo ---------------------
#
# Las tres bibliotecas siguientes fallan de formas distintas al empaquetar,
# porque cargan archivos que no son módulos de Python y que por tanto no
# aparecen en el análisis estático de importaciones.

# tkinterweb: el visor HTML es un binario nativo de Tkhtml que vive en el
# paquete aparte `tkinterweb_tkhtml` y se carga desde Tcl con `load`, no
# desde Python. Sin estos datos la aplicación arranca pero el mapa queda
# en blanco o lanza un error de Tcl al crear el HtmlFrame.
datos_tkinterweb = collect_data_files("tkinterweb")
datos_tkinterweb += collect_data_files("tkinterweb_tkhtml")
binarios_tkinterweb = collect_dynamic_libs("tkinterweb_tkhtml")

# folium y branca: las plantillas Jinja2 y los archivos JavaScript con los
# que se construye el mapa son datos del paquete. Sin ellos, generar el
# mapa falla con un TemplateNotFound.
datos_folium = collect_data_files("folium")
datos_branca = collect_data_files("branca")

# reportlab: las fuentes Type1 (.pfb/.afm) y TrueType con las que compone
# los PDF son datos del paquete. Sin ellas, generar una hoja de ruta falla
# al resolver la fuente Helvetica.
datos_reportlab = collect_data_files("reportlab")
importaciones_reportlab = collect_submodules("reportlab.graphics.barcode")

# pymupdf: usado para rasterizar la previsualización. Lleva bibliotecas
# nativas propias.
binarios_pymupdf = collect_dynamic_libs("pymupdf")

datos_completos = (
    datos_aplicacion
    + datos_tkinterweb
    + datos_folium
    + datos_branca
    + datos_reportlab
)

binarios_completos = binarios_tkinterweb + binarios_pymupdf

importaciones_ocultas = (
    [
        # tkinterweb carga su binario a través de este paquete.
        "tkinterweb",
        "tkinterweb_tkhtml",
        # folium construye el HTML con Jinja2 y branca.
        "jinja2",
        "branca",
        "branca.colormap",
        "branca.element",
        # pymupdf mantiene el alias histórico `fitz`.
        "pymupdf",
        # Módulos de la biblioteca estándar que se importan de forma
        # indirecta y que PyInstaller a veces no arrastra.
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
    ]
    + importaciones_reportlab
)

# --- Icono opcional -----------------------------------------------------------
# Si existe `recursos/polux.ico` se usa como icono del ejecutable. Es
# opcional: sin él la compilación funciona igual y Windows muestra el icono
# genérico. Para añadirlo, basta con colocar el archivo en esa ruta.
RUTA_ICONO = os.path.join("recursos", "polux.ico")
icono = RUTA_ICONO if os.path.isfile(RUTA_ICONO) else None

# --- Recurso de versión de Windows -------------------------------------------
# Solo se aplica en Windows; en otras plataformas PyInstaller lo ignora.
RUTA_VERSION_WINDOWS = os.path.join("scripts", "version_windows.txt")
version_windows = (
    RUTA_VERSION_WINDOWS
    if sys.platform == "win32" and os.path.isfile(RUTA_VERSION_WINDOWS)
    else None
)


analisis = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=binarios_completos,
    datas=datos_completos,
    hiddenimports=importaciones_ocultas,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Se excluyen bibliotecas pesadas que no usa la aplicación, para no
    # inflar el ejecutable si están presentes en el entorno.
    excludes=[
        "matplotlib",
        "scipy",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "notebook",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analisis.pure)

exe = EXE(
    pyz,
    analisis.scripts,
    analisis.binaries,
    analisis.datas,
    [],
    name=f"{NOMBRE_APLICACION}-{VERSION}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Un único archivo, sin ventana de consola: es una aplicación gráfica.
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icono,
    version=version_windows,
)
