"""
Lector de instancias de referencia de Solomon (VRPTW).

Las instancias de Solomon son el conjunto de pruebas estándar para el
VRPTW y se usan aquí para la validación experimental del algoritmo. Su
formato es el siguiente:

    C101

    VEHICLE
    NUMBER     CAPACITY
      25         200

    CUSTOMER
    CUST NO.  XCOORD.  YCOORD.  DEMAND  READY TIME  DUE DATE  SERVICE TIME
        0      40       50         0        0         1236         0
        1      45       68        10      912          967        90

Diferencias importantes respecto al modo normal de la aplicación:

* Las coordenadas XCOORD/YCOORD son cartesianas y adimensionales, no
  geográficas: se guardan tal cual en `Nodo.lat`/`Nodo.lon` como valores
  nominales y **no se geocodifican**. El mapa de la aplicación no está
  pensado para representarlas.
* Las distancias son **euclídeas** y el tiempo de viaje es numéricamente
  igual a la distancia, tal y como define Solomon. Por tanto no se consulta
  OSRM ni ningún otro servicio de red.
* Los tiempos ya vienen en unidades numéricas coherentes entre sí y se
  conservan como están, sin convertirlos a horas del día. El depósito abre
  en el instante 0.
* El Reglamento (CE) nº 561/2006 **no es aplicable** a estas instancias,
  porque no tienen noción de jornada ni de horas del día. Quien las utilice
  debe llamar al optimizador con `aplicar_reglamento=False`; la constante
  `APLICAR_REGLAMENTO_EN_SOLOMON` documenta esa decisión de forma explícita.
"""

import math
import os
from dataclasses import dataclass

from datos.modelos import Nodo
from utils.osrm import MatrizDistancias

#: Las instancias de Solomon no modelan jornadas laborales, así que el
#: Reglamento (CE) nº 561/2006 nunca debe aplicarse al resolverlas. Se
#: expone como constante para que el modo evaluación quede explícito en el
#: código que la consume y en los informes de resultados.
APLICAR_REGLAMENTO_EN_SOLOMON = False

#: Instante de apertura del depósito en las instancias de Solomon.
HORA_INICIO_SOLOMON = 0

#: Identificador del depósito dentro del archivo de instancia.
ID_DEPOT_SOLOMON = 0


class ErrorCargaSolomon(Exception):
    """Excepción lanzada cuando un archivo de instancia de Solomon es inválido."""


@dataclass
class InstanciaSolomon:
    """
    Instancia de referencia de Solomon ya interpretada y lista para resolver.

    Atributos:
        nombre: Nombre de la instancia (p. ej. "C101").
        num_vehiculos: Número de vehículos que declara el archivo. Se
            conserva a título informativo: en la evaluación estándar la
            flota se considera ilimitada y el número de vehículos es la
            magnitud a minimizar.
        capacidad_vehiculo: Capacidad de cada vehículo.
        depot: Nodo del depósito (cliente 0 del archivo).
        clientes: Resto de nodos, en el orden del archivo.
        matriz: Matriz de distancias euclídeas, con tiempo igual a distancia.
    """

    nombre: str
    num_vehiculos: int
    capacidad_vehiculo: float
    depot: Nodo
    clientes: list[Nodo]
    matriz: MatrizDistancias

    @property
    def clase(self) -> str:
        """
        Clase de la instancia según la nomenclatura de Solomon: C1, C2, R1,
        R2, RC1 o RC2, deducida del prefijo del nombre.
        """
        return clase_de_instancia(self.nombre)


def clase_de_instancia(nombre: str) -> str:
    """
    Deduce la clase de una instancia de Solomon a partir de su nombre.

    Las clases son C1/C2 (clientes agrupados), R1/R2 (clientes aleatorios) y
    RC1/RC2 (mixtas). El dígito indica el subtipo: las series 1 tienen
    ventanas de tiempo estrechas y horizonte corto, y las series 2 ventanas
    amplias y horizonte largo.

    Args:
        nombre: Nombre de la instancia, p. ej. "C101" o "RC205".

    Returns:
        La clase en mayúsculas, o "DESCONOCIDA" si el nombre no encaja.
    """
    nombre_normalizado = os.path.splitext(os.path.basename(nombre))[0].strip().upper()

    for prefijo in ("RC", "C", "R"):
        if nombre_normalizado.startswith(prefijo):
            resto = nombre_normalizado[len(prefijo) :]
            if resto and resto[0] in ("1", "2"):
                return f"{prefijo}{resto[0]}"
    return "DESCONOCIDA"


def cargar_instancia_solomon(ruta_archivo: str) -> InstanciaSolomon:
    """
    Lee un archivo de instancia de Solomon y lo convierte en una
    InstanciaSolomon lista para resolver.

    Args:
        ruta_archivo: Ruta al archivo de la instancia.

    Returns:
        La instancia interpretada, con su depósito, clientes y matriz de
        distancias euclídeas ya construida.

    Raises:
        ErrorCargaSolomon: Si el archivo no existe o su formato no es válido.
    """
    try:
        with open(ruta_archivo, "r", encoding="utf-8") as archivo:
            lineas = archivo.read().splitlines()
    except FileNotFoundError as error:
        raise ErrorCargaSolomon(f"No se encontró el archivo: {ruta_archivo}") from error
    except OSError as error:
        raise ErrorCargaSolomon(f"No se pudo leer el archivo: {ruta_archivo}") from error

    lineas_utiles = [linea for linea in lineas if linea.strip()]
    if not lineas_utiles:
        raise ErrorCargaSolomon(f"El archivo de instancia está vacío: {ruta_archivo}")

    nombre = lineas_utiles[0].strip()
    num_vehiculos, capacidad_vehiculo = _leer_seccion_vehiculos(lineas_utiles, ruta_archivo)
    nodos = _leer_seccion_clientes(lineas_utiles, ruta_archivo)

    depot = next((nodo for nodo in nodos if nodo.id == ID_DEPOT_SOLOMON), None)
    if depot is None:
        raise ErrorCargaSolomon(
            f"La instancia {nombre} no define el cliente 0 (depósito)"
        )
    depot.es_depot = True
    depot.nombre = "Depósito"

    clientes = [nodo for nodo in nodos if nodo.id != ID_DEPOT_SOLOMON]
    if not clientes:
        raise ErrorCargaSolomon(f"La instancia {nombre} no contiene ningún cliente")

    return InstanciaSolomon(
        nombre=nombre,
        num_vehiculos=num_vehiculos,
        capacidad_vehiculo=capacidad_vehiculo,
        depot=depot,
        clientes=clientes,
        matriz=construir_matriz_euclidea([depot] + clientes),
    )


def construir_matriz_euclidea(nodos: list[Nodo]) -> MatrizDistancias:
    """
    Construye la matriz de distancias euclídeas entre todos los nodos, con
    el tiempo de viaje numéricamente igual a la distancia.

    Es la convención de las instancias de Solomon, y sustituye por completo
    a la consulta de distancias reales por carretera: esta función no accede
    a la red.

    Args:
        nodos: Nodos a incluir (depósito y clientes).

    Returns:
        La matriz simétrica de distancias/tiempos.
    """
    matriz = MatrizDistancias()

    for origen in nodos:
        for destino in nodos:
            if origen.id == destino.id:
                continue
            distancia = math.hypot(destino.lat - origen.lat, destino.lon - origen.lon)
            matriz.distancias_km[(origen.id, destino.id)] = distancia
            matriz.tiempos_min[(origen.id, destino.id)] = distancia

    return matriz


def _leer_seccion_vehiculos(lineas: list[str], ruta_archivo: str) -> tuple[int, float]:
    """Extrae el número de vehículos y la capacidad de la sección VEHICLE."""
    for indice, linea in enumerate(lineas):
        if linea.strip().upper().startswith("VEHICLE"):
            # La cabecera "NUMBER  CAPACITY" ocupa la línea siguiente y los
            # valores la posterior.
            for linea_valores in lineas[indice + 1 : indice + 4]:
                partes = linea_valores.split()
                if len(partes) >= 2 and all(_es_numero(parte) for parte in partes[:2]):
                    return int(float(partes[0])), float(partes[1])
            break

    raise ErrorCargaSolomon(
        f"No se pudo interpretar la sección VEHICLE de la instancia: {ruta_archivo}"
    )


def _leer_seccion_clientes(lineas: list[str], ruta_archivo: str) -> list[Nodo]:
    """Extrae los nodos de la sección CUSTOMER."""
    indice_seccion = None
    for indice, linea in enumerate(lineas):
        if linea.strip().upper().startswith("CUSTOMER"):
            indice_seccion = indice
            break

    if indice_seccion is None:
        raise ErrorCargaSolomon(
            f"La instancia no contiene una sección CUSTOMER: {ruta_archivo}"
        )

    nodos: list[Nodo] = []
    for linea in lineas[indice_seccion + 1 :]:
        partes = linea.split()
        # Se ignoran las líneas de cabecera ("CUST NO.  XCOORD. ...") y
        # cualquier línea que no tenga los siete campos numéricos esperados.
        if len(partes) < 7 or not all(_es_numero(parte) for parte in partes[:7]):
            continue

        identificador = int(float(partes[0]))
        coordenada_x = float(partes[1])
        coordenada_y = float(partes[2])
        demanda = float(partes[3])
        instante_apertura = int(float(partes[4]))
        instante_cierre = int(float(partes[5]))
        tiempo_servicio = int(float(partes[6]))

        nodos.append(
            Nodo(
                id=identificador,
                nombre=f"Cliente {identificador}",
                # Coordenadas cartesianas de la instancia, no geográficas.
                lat=coordenada_x,
                lon=coordenada_y,
                demanda=demanda,
                hora_inicio=instante_apertura,
                hora_fin=instante_cierre,
                tiempo_servicio=tiempo_servicio,
                es_depot=False,
            )
        )

    if not nodos:
        raise ErrorCargaSolomon(
            f"No se ha podido interpretar ningún cliente en la instancia: {ruta_archivo}"
        )

    return nodos


def _es_numero(texto: str) -> bool:
    """Indica si una cadena puede interpretarse como número."""
    try:
        float(texto)
    except ValueError:
        return False
    return True
