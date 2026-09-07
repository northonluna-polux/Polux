"""
Carga y validación de los datos de clientes desde un archivo CSV.

El archivo debe contener las columnas:
    id, nombre, demanda, hora_inicio, hora_fin, tiempo_servicio

Y, para la ubicación de cada cliente, al menos una de estas dos opciones:
    - `lat` y `lon` (coordenadas geográficas), o
    - `direccion` (dirección de texto libre, que se geocodifica mediante
      Nominatim/OpenStreetMap).

Si una fila incluye tanto `lat`/`lon` como `direccion`, las coordenadas
tienen prioridad y no se geocodifica. `hora_inicio` y `hora_fin` son
cadenas con formato HH:MM y `tiempo_servicio` está expresado en minutos.
"""

from typing import Callable, Optional

import pandas as pd

from datos.modelos import ClienteNoAsignado, MOTIVO_GEOCODIFICACION, Nodo, hhmm_a_minutos
from utils.geocodificacion import ErrorGeocodificacion, geocodificar_direccion

#: Id reservado para el nodo del depósito; ningún cliente puede usarlo
#: (evita colisiones al indexar la matriz de distancias por id de nodo).
ID_DEPOT_RESERVADO = 0

#: Columnas obligatorias en cualquier CSV de clientes (además de la
#: ubicación, resuelta por separado mediante `lat`/`lon` o `direccion`).
COLUMNAS_BASE_REQUERIDAS = [
    "id",
    "nombre",
    "demanda",
    "hora_inicio",
    "hora_fin",
    "tiempo_servicio",
]

#: Firma del callback de progreso: (geocodificados_hasta_ahora, total_a_geocodificar, texto)
CallbackProgreso = Callable[[int, int, str], None]


class ErrorCargaDatos(Exception):
    """Excepción lanzada cuando el archivo CSV de clientes es inválido."""


def _valor_presente(valor) -> bool:
    """Indica si una celda del CSV tiene un valor no vacío."""
    if valor is None:
        return False
    if isinstance(valor, float) and pd.isna(valor):
        return False
    texto = str(valor).strip()
    return texto != "" and texto.lower() != "nan"


def cargar_clientes_desde_csv(
    ruta_csv: str, callback_progreso: Optional[CallbackProgreso] = None
) -> tuple[list[Nodo], list[ClienteNoAsignado]]:
    """
    Lee un archivo CSV de clientes y lo convierte en una lista de objetos
    Nodo, validando el formato y el contenido de cada fila. Las filas que
    solo incluyen una dirección de texto (columna `direccion`) se
    geocodifican automáticamente mediante Nominatim.

    Args:
        ruta_csv: Ruta al archivo CSV con los datos de los clientes.
        callback_progreso: Función opcional invocada por cada dirección que
            se geocodifica, como `callback_progreso(indice, total, texto)`.
            No se invoca para filas que ya traen `lat`/`lon`.

    Returns:
        Una tupla (clientes, fallidos_geocodificacion):
            - clientes: nodos válidos, con coordenadas resueltas.
            - fallidos_geocodificacion: clientes cuya dirección no se pudo
              geocodificar, con motivo MOTIVO_GEOCODIFICACION.

    Raises:
        ErrorCargaDatos: Si el archivo no existe, le faltan columnas o
            contiene valores inválidos.
        ErrorGeocodificacion: Si el servicio de geocodificación no está
            disponible (fallo de red, no un simple "dirección no encontrada").
    """
    try:
        tabla = pd.read_csv(ruta_csv, dtype=str)
    except FileNotFoundError as error:
        raise ErrorCargaDatos(f"No se encontró el archivo: {ruta_csv}") from error
    except pd.errors.EmptyDataError as error:
        raise ErrorCargaDatos("El archivo CSV está vacío") from error

    columnas_faltantes = [c for c in COLUMNAS_BASE_REQUERIDAS if c not in tabla.columns]
    if columnas_faltantes:
        raise ErrorCargaDatos(
            "Faltan columnas obligatorias en el CSV: " + ", ".join(columnas_faltantes)
        )

    tiene_columna_coords = "lat" in tabla.columns and "lon" in tabla.columns
    tiene_columna_direccion = "direccion" in tabla.columns
    if not tiene_columna_coords and not tiene_columna_direccion:
        raise ErrorCargaDatos(
            "El CSV debe incluir 'lat' y 'lon', o bien una columna 'direccion'"
        )

    if tabla.empty:
        raise ErrorCargaDatos("El archivo CSV no contiene ningún cliente")

    total_a_geocodificar = 0
    if tiene_columna_direccion:
        for _, fila in tabla.iterrows():
            tiene_coords = tiene_columna_coords and _valor_presente(fila.get("lat")) and _valor_presente(
                fila.get("lon")
            )
            tiene_direccion = _valor_presente(fila.get("direccion"))
            if not tiene_coords and tiene_direccion:
                total_a_geocodificar += 1

    clientes: list[Nodo] = []
    fallidos_geocodificacion: list[ClienteNoAsignado] = []
    ids_vistos: set[str] = set()
    geocodificados_hasta_ahora = 0

    for numero_fila, fila in tabla.iterrows():
        linea = numero_fila + 2  # +2: cabecera + índice base 1
        try:
            id_cliente = int(fila["id"])
        except (ValueError, TypeError) as error:
            raise ErrorCargaDatos(f"Línea {linea}: 'id' debe ser un número entero") from error

        if id_cliente == ID_DEPOT_RESERVADO:
            raise ErrorCargaDatos(
                f"Línea {linea}: el id {ID_DEPOT_RESERVADO} está reservado para el depósito"
            )

        if str(fila["id"]) in ids_vistos:
            raise ErrorCargaDatos(f"Línea {linea}: el id {id_cliente} está duplicado")
        ids_vistos.add(str(fila["id"]))

        nombre = str(fila["nombre"]).strip()
        if not nombre:
            raise ErrorCargaDatos(f"Línea {linea}: el nombre del cliente no puede estar vacío")

        tiene_coords = tiene_columna_coords and _valor_presente(fila.get("lat")) and _valor_presente(
            fila.get("lon")
        )
        tiene_direccion = tiene_columna_direccion and _valor_presente(fila.get("direccion"))

        if not tiene_coords and not tiene_direccion:
            raise ErrorCargaDatos(
                f"Línea {linea}: debe indicarse 'direccion', o bien 'lat' y 'lon'"
            )

        lat: Optional[float]
        lon: Optional[float]
        # Se conserva el texto de la dirección para mostrarlo en informes
        # (p. ej. la columna "Dirección" de las hojas de ruta en PDF),
        # incluso cuando 'lat'/'lon' tienen prioridad para la geolocalización.
        direccion_original: Optional[str] = str(fila["direccion"]).strip() if tiene_direccion else None

        if tiene_coords:
            try:
                lat = float(fila["lat"])
                lon = float(fila["lon"])
            except (ValueError, TypeError) as error:
                raise ErrorCargaDatos(f"Línea {linea}: 'lat' y 'lon' deben ser numéricos") from error

            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                raise ErrorCargaDatos(f"Línea {linea}: coordenadas fuera de rango")
        else:
            geocodificados_hasta_ahora += 1
            if callback_progreso:
                callback_progreso(geocodificados_hasta_ahora, total_a_geocodificar, direccion_original)

            resultado = geocodificar_direccion(direccion_original)
            if resultado is None:
                lat = None
                lon = None
            else:
                lat, lon = resultado

        try:
            demanda = float(fila["demanda"])
        except (ValueError, TypeError) as error:
            raise ErrorCargaDatos(f"Línea {linea}: 'demanda' debe ser numérica") from error
        if demanda < 0:
            raise ErrorCargaDatos(f"Línea {linea}: 'demanda' no puede ser negativa")

        try:
            hora_inicio = hhmm_a_minutos(str(fila["hora_inicio"]))
            hora_fin = hhmm_a_minutos(str(fila["hora_fin"]))
        except (ValueError, AttributeError) as error:
            raise ErrorCargaDatos(
                f"Línea {linea}: 'hora_inicio'/'hora_fin' deben tener formato HH:MM"
            ) from error

        if hora_inicio >= hora_fin:
            raise ErrorCargaDatos(
                f"Línea {linea}: la ventana de tiempo es inválida (hora_inicio >= hora_fin)"
            )

        try:
            tiempo_servicio = int(float(fila["tiempo_servicio"]))
        except (ValueError, TypeError) as error:
            raise ErrorCargaDatos(
                f"Línea {linea}: 'tiempo_servicio' debe ser un número de minutos"
            ) from error
        if tiempo_servicio < 0:
            raise ErrorCargaDatos(f"Línea {linea}: 'tiempo_servicio' no puede ser negativo")

        nodo = Nodo(
            id=id_cliente,
            nombre=nombre,
            lat=lat,
            lon=lon,
            demanda=demanda,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            tiempo_servicio=tiempo_servicio,
            es_depot=False,
            direccion_original=direccion_original,
        )

        if nodo.tiene_coordenadas():
            clientes.append(nodo)
        else:
            fallidos_geocodificacion.append(
                ClienteNoAsignado(
                    nodo=nodo,
                    motivo=MOTIVO_GEOCODIFICACION,
                    detalle=f"Dirección no encontrada: {direccion_original}",
                )
            )

    return clientes, fallidos_geocodificacion
