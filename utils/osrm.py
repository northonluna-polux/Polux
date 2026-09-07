"""
Cálculo de distancias y tiempos reales por carretera mediante la API de
OSRM (Open Source Routing Machine).

Sustituye la distancia en línea recta (Haversine) por distancias y tiempos
de conducción reales, obtenidos de la instancia pública de demostración de
OSRM (router.project-osrm.org). Se realiza una única llamada al endpoint
`table` para calcular la matriz completa de distancias/tiempos entre el
depósito y todos los clientes antes de ejecutar el algoritmo, y el
resultado se guarda en caché en memoria para no repetir la llamada
mientras el conjunto de nodos no cambie.

También se ofrece un endpoint `route` para obtener la geometría real de
una ruta (la polilínea que sigue las calles), usada únicamente para
dibujar el mapa.
"""

from dataclasses import dataclass, field

import requests

from datos.modelos import Nodo

#: Instancia pública de demostración de OSRM
OSRM_URL_BASE = "https://router.project-osrm.org"

#: Tiempo máximo de espera para las peticiones HTTP, en segundos
TIMEOUT_PETICION_SEGUNDOS = 20

#: Número máximo de coordenadas admitidas en una petición `table`. La
#: instancia pública de demostración de OSRM limita el tamaño de la matriz,
#: por lo que se comprueba antes de lanzar la petición para poder dar un
#: mensaje claro en lugar de un error HTTP genérico del servidor.
MAX_NODOS_OSRM = 100

#: Número máximo de matrices conservadas en el caché en memoria. Cada matriz
#: ocupa O(n²) entradas, así que se limita el histórico para no crecer sin
#: control durante una sesión larga con muchos archivos distintos.
MAX_ENTRADAS_CACHE = 10

# Caché en memoria de matrices ya calculadas, indexada por una clave que
# identifica de forma única al conjunto de nodos (depósito + clientes).
# Se aprovecha que los dict de Python conservan el orden de inserción para
# descartar la entrada más antigua cuando se supera el límite.
_cache_matrices: dict[tuple, "MatrizDistancias"] = {}


class ErrorEnrutamiento(Exception):
    """Excepción lanzada cuando el servicio de enrutamiento OSRM falla o no está disponible."""


@dataclass
class MatrizDistancias:
    """
    Matriz de distancias (km) y tiempos de conducción (min) reales por
    carretera entre cada par de nodos, indexada por el id de cada nodo.
    """

    distancias_km: dict[tuple[int, int], float] = field(default_factory=dict)
    tiempos_min: dict[tuple[int, int], float] = field(default_factory=dict)

    def distancia(self, id_origen: int, id_destino: int) -> float:
        """Distancia real por carretera entre dos nodos, en kilómetros."""
        if id_origen == id_destino:
            return 0.0
        return self.distancias_km[(id_origen, id_destino)]

    def tiempo(self, id_origen: int, id_destino: int) -> float:
        """Tiempo de conducción real por carretera entre dos nodos, en minutos."""
        if id_origen == id_destino:
            return 0.0
        return self.tiempos_min[(id_origen, id_destino)]


def _clave_cache(nodos: list[Nodo]) -> tuple:
    """Genera una clave de caché a partir del id y las coordenadas de cada nodo."""
    return tuple((nodo.id, round(nodo.lat, 6), round(nodo.lon, 6)) for nodo in nodos)


def obtener_matriz_distancias(nodos: list[Nodo]) -> MatrizDistancias:
    """
    Obtiene la matriz completa de distancias y tiempos reales por
    carretera entre todos los nodos indicados (típicamente depósito +
    clientes), consultando el endpoint `table` de OSRM en una única
    llamada. El resultado se guarda en caché: si se vuelve a solicitar la
    matriz para el mismo conjunto exacto de nodos, no se repite la
    llamada de red.

    Args:
        nodos: Lista de nodos a incluir en la matriz (el orden se
            conserva pero no afecta al resultado).

    Returns:
        La matriz de distancias/tiempos correspondiente.

    Raises:
        ErrorEnrutamiento: Si el servicio OSRM no está disponible, responde
            con un error, o no encuentra ruta por carretera entre algún par
            de nodos.
    """
    clave = _clave_cache(nodos)
    if clave in _cache_matrices:
        return _cache_matrices[clave]

    if len(nodos) > MAX_NODOS_OSRM:
        raise ErrorEnrutamiento(
            f"Se han solicitado distancias para {len(nodos)} ubicaciones (depósito + "
            f"clientes), pero el servicio público de OSRM admite como máximo "
            f"{MAX_NODOS_OSRM} por consulta. Divide la lista de clientes en varios "
            f"archivos más pequeños, o instala tu propia instancia de OSRM para "
            f"eliminar este límite."
        )

    coordenadas = ";".join(f"{nodo.lon},{nodo.lat}" for nodo in nodos)
    url = f"{OSRM_URL_BASE}/table/v1/driving/{coordenadas}"

    try:
        respuesta = requests.get(
            url, params={"annotations": "distance,duration"}, timeout=TIMEOUT_PETICION_SEGUNDOS
        )
    except requests.exceptions.RequestException as error:
        raise ErrorEnrutamiento(
            "No se pudo conectar con el servicio de rutas OSRM. "
            "Comprueba tu conexión a internet e inténtalo de nuevo."
        ) from error

    if respuesta.status_code != 200:
        raise ErrorEnrutamiento(
            f"El servicio OSRM respondió con un error HTTP {respuesta.status_code}."
        )

    try:
        datos = respuesta.json()
    except ValueError as error:
        raise ErrorEnrutamiento("La respuesta del servicio OSRM no es un JSON válido.") from error

    if datos.get("code") != "Ok":
        raise ErrorEnrutamiento(
            f"El servicio OSRM devolvió un error: {datos.get('message', datos.get('code'))}"
        )

    distancias_metros = datos.get("distances")
    duraciones_segundos = datos.get("durations")
    if distancias_metros is None or duraciones_segundos is None:
        raise ErrorEnrutamiento("La respuesta del servicio OSRM no contiene distancias/tiempos.")

    matriz = MatrizDistancias()
    n = len(nodos)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            distancia_metros = distancias_metros[i][j]
            duracion_segundos = duraciones_segundos[i][j]
            if distancia_metros is None or duracion_segundos is None:
                raise ErrorEnrutamiento(
                    f"El servicio OSRM no encontró ruta por carretera entre "
                    f"'{nodos[i].nombre}' y '{nodos[j].nombre}'."
                )
            matriz.distancias_km[(nodos[i].id, nodos[j].id)] = distancia_metros / 1000.0
            matriz.tiempos_min[(nodos[i].id, nodos[j].id)] = duracion_segundos / 60.0

    while len(_cache_matrices) >= MAX_ENTRADAS_CACHE:
        _cache_matrices.pop(next(iter(_cache_matrices)))
    _cache_matrices[clave] = matriz
    return matriz


def obtener_geometria_ruta(nodos_en_orden: list[Nodo]) -> list[tuple[float, float]]:
    """
    Obtiene la geometría real (la polilínea que sigue las calles) de una
    ruta completa, consultando el endpoint `route` de OSRM. Se utiliza
    únicamente para dibujar el mapa con más fidelidad; no interviene en el
    cálculo del algoritmo de optimización.

    Args:
        nodos_en_orden: Secuencia ordenada de nodos que forman la ruta
            (incluyendo el depósito al principio y al final).

    Returns:
        Lista de puntos (lat, lon) que describen la geometría real de la
        ruta sobre la red de carreteras.

    Raises:
        ErrorEnrutamiento: Si el servicio OSRM no está disponible o no
            encuentra una ruta por carretera para la secuencia indicada.
    """
    coordenadas = ";".join(f"{nodo.lon},{nodo.lat}" for nodo in nodos_en_orden)
    url = f"{OSRM_URL_BASE}/route/v1/driving/{coordenadas}"

    try:
        respuesta = requests.get(
            url,
            params={"geometries": "geojson", "overview": "full"},
            timeout=TIMEOUT_PETICION_SEGUNDOS,
        )
    except requests.exceptions.RequestException as error:
        raise ErrorEnrutamiento("No se pudo conectar con el servicio de rutas OSRM.") from error

    if respuesta.status_code != 200:
        raise ErrorEnrutamiento(
            f"El servicio OSRM respondió con un error HTTP {respuesta.status_code}."
        )

    try:
        datos = respuesta.json()
    except ValueError as error:
        raise ErrorEnrutamiento("La respuesta del servicio OSRM no es un JSON válido.") from error

    if datos.get("code") != "Ok" or not datos.get("routes"):
        raise ErrorEnrutamiento(
            f"El servicio OSRM no encontró una ruta por carretera: {datos.get('code')}"
        )

    coordenadas_geojson = datos["routes"][0]["geometry"]["coordinates"]
    # GeoJSON expresa cada punto como [lon, lat]; se invierte a (lat, lon).
    return [(lat, lon) for lon, lat in coordenadas_geojson]
