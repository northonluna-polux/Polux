"""
Geocodificación de direcciones mediante la API de Nominatim (OpenStreetMap).

Convierte una dirección de texto libre (p. ej. "Calle Gran Vía 10, Valencia")
en coordenadas (lat, lon). Los resultados se guardan en un caché en disco
(`datos/geocache.json`) para no volver a geocodificar la misma dirección, y
las peticiones respetan la política de uso de Nominatim: como máximo una
petición por segundo y un cabecera `User-Agent` identificable.
"""

import json
import os
import time
from typing import Optional

import requests

from utils.rutas_app import ruta_cache_geocodificacion

#: Instancia pública de Nominatim (OpenStreetMap)
NOMINATIM_URL_BASE = "https://nominatim.openstreetmap.org/search"

#: Cabecera User-Agent exigida por la política de uso de Nominatim
USER_AGENT_NOMINATIM = "Polux-TFM/1.0"

#: Tiempo máximo de espera para las peticiones HTTP, en segundos
TIMEOUT_PETICION_SEGUNDOS = 15

#: Intervalo mínimo entre peticiones consecutivas a Nominatim, en segundos
INTERVALO_MINIMO_SEGUNDOS = 1.0

#: Ruta del archivo de caché de direcciones ya geocodificadas.
#: Vive en la carpeta de datos del usuario (``%LOCALAPPDATA%\\Polux`` en
#: Windows, ``~/.polux`` en el resto), nunca dentro del paquete: en un
#: ejecutable empaquetado ese directorio es de solo lectura.
RUTA_CACHE_GEOCODIFICACION = ruta_cache_geocodificacion()

_ultima_peticion_ts = 0.0


class ErrorGeocodificacion(Exception):
    """Excepción lanzada cuando el servicio de geocodificación falla o no está disponible."""


def _cargar_cache() -> dict:
    if not os.path.exists(RUTA_CACHE_GEOCODIFICACION):
        return {}
    try:
        with open(RUTA_CACHE_GEOCODIFICACION, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return {}


def _guardar_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(RUTA_CACHE_GEOCODIFICACION), exist_ok=True)
        with open(RUTA_CACHE_GEOCODIFICACION, "w", encoding="utf-8") as archivo:
            json.dump(cache, archivo, ensure_ascii=False, indent=2)
    except OSError:
        pass  # El caché es una optimización; su fallo no debe interrumpir la carga


_cache_geocodificacion = _cargar_cache()


def _esperar_limite_tasa() -> None:
    """Respeta el límite de una petición por segundo exigido por Nominatim."""
    global _ultima_peticion_ts
    transcurrido = time.time() - _ultima_peticion_ts
    if transcurrido < INTERVALO_MINIMO_SEGUNDOS:
        time.sleep(INTERVALO_MINIMO_SEGUNDOS - transcurrido)
    _ultima_peticion_ts = time.time()


def geocodificar_direccion(direccion: str) -> Optional[tuple[float, float]]:
    """
    Resuelve una dirección de texto libre a coordenadas (lat, lon) mediante
    Nominatim. Los resultados exitosos se guardan en caché en disco para no
    repetir la misma petición en el futuro.

    Args:
        direccion: Dirección a geocodificar (p. ej. "Calle Gran Vía 10, Valencia").

    Returns:
        Una tupla (lat, lon), o None si la dirección no se ha encontrado.

    Raises:
        ErrorGeocodificacion: Si el servicio de geocodificación no está
            disponible o responde con un error.
    """
    clave_cache = direccion.strip().lower()
    if clave_cache in _cache_geocodificacion:
        lat, lon = _cache_geocodificacion[clave_cache]
        return lat, lon

    _esperar_limite_tasa()

    try:
        respuesta = requests.get(
            NOMINATIM_URL_BASE,
            params={"q": direccion, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT_NOMINATIM},
            timeout=TIMEOUT_PETICION_SEGUNDOS,
        )
    except requests.exceptions.RequestException as error:
        raise ErrorGeocodificacion(
            "No se pudo conectar con el servicio de geocodificación (Nominatim). "
            "Comprueba tu conexión a internet e inténtalo de nuevo."
        ) from error

    if respuesta.status_code != 200:
        raise ErrorGeocodificacion(
            f"El servicio de geocodificación respondió con un error HTTP {respuesta.status_code}."
        )

    try:
        resultados = respuesta.json()
    except ValueError as error:
        raise ErrorGeocodificacion(
            "La respuesta del servicio de geocodificación no es un JSON válido."
        ) from error

    if not resultados:
        return None

    lat = float(resultados[0]["lat"])
    lon = float(resultados[0]["lon"])
    _cache_geocodificacion[clave_cache] = [lat, lon]
    _guardar_cache(_cache_geocodificacion)
    return lat, lon
