"""
Resolución de rutas de archivos, tanto ejecutando desde el código fuente
como desde el ejecutable empaquetado con PyInstaller.

La distinción importa porque un ejecutable de un solo archivo se
descomprime en una carpeta temporal de **solo lectura** que además cambia
en cada arranque. Por tanto hay que separar dos cosas:

* Los **recursos empaquetados** (el CSV de ejemplo, iconos): viajan dentro
  del ejecutable y solo se leen. Se localizan con `ruta_recurso()`.
* Los **datos del usuario** (caché de geocodificación, hojas de ruta
  generadas): deben escribirse fuera del paquete, en una carpeta estable
  del perfil del usuario. Se localizan con `directorio_datos_usuario()`.

Ubicación de los datos del usuario:

* Windows: ``%LOCALAPPDATA%\\Polux``
* macOS y Linux: ``~/.polux``
"""

import os
import sys

from version import NOMBRE_APLICACION


def esta_empaquetado() -> bool:
    """
    Indica si la aplicación se está ejecutando desde un ejecutable
    empaquetado con PyInstaller en lugar de desde el código fuente.
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def directorio_recursos() -> str:
    """
    Devuelve la carpeta base de los recursos de solo lectura.

    Al ejecutar empaquetado es la carpeta temporal que crea PyInstaller; al
    ejecutar desde el código fuente, la raíz del proyecto.
    """
    if esta_empaquetado():
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_recurso(*partes: str) -> str:
    """
    Construye la ruta de un recurso empaquetado.

    Args:
        *partes: Componentes de la ruta relativos a la raíz de recursos,
            por ejemplo ``ruta_recurso("datos", "clientes_ejemplo.csv")``.

    Returns:
        Ruta absoluta al recurso.
    """
    return os.path.join(directorio_recursos(), *partes)


def directorio_datos_usuario() -> str:
    """
    Devuelve la carpeta donde la aplicación puede escribir datos
    persistentes, creándola si no existe.

    Nunca apunta al interior del paquete: en un ejecutable de un solo
    archivo ese directorio es de solo lectura y se borra al salir.

    Returns:
        Ruta absoluta de la carpeta de datos del usuario.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        directorio = os.path.join(base, NOMBRE_APLICACION)
    else:
        directorio = os.path.join(os.path.expanduser("~"), f".{NOMBRE_APLICACION.lower()}")

    os.makedirs(directorio, exist_ok=True)
    return directorio


def ruta_cache_geocodificacion() -> str:
    """Ruta del archivo de caché de direcciones geocodificadas."""
    return os.path.join(directorio_datos_usuario(), "geocache.json")


def directorio_hojas_de_ruta() -> str:
    """
    Carpeta propuesta por defecto para guardar las hojas de ruta en PDF,
    creándola si no existe.
    """
    directorio = os.path.join(directorio_datos_usuario(), "hojas_de_ruta")
    os.makedirs(directorio, exist_ok=True)
    return directorio


def ruta_csv_ejemplo() -> str:
    """Ruta del CSV de clientes de ejemplo que se distribuye con la aplicación."""
    return ruta_recurso("datos", "clientes_ejemplo.csv")


def directorio_inicial_para_csv() -> str:
    """
    Carpeta que se abre por defecto en el diálogo de carga de clientes.

    Se propone la carpeta de los datos de ejemplo si existe, para que el
    usuario encuentre el archivo de prueba sin buscarlo.
    """
    directorio_ejemplos = ruta_recurso("datos")
    if os.path.isdir(directorio_ejemplos):
        return directorio_ejemplos
    return os.path.expanduser("~")
