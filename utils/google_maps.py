"""
Generación de enlaces de Google Maps para las rutas optimizadas.

Construye una URL de Google Maps con el itinerario completo de una ruta
(depósito -> paradas -> última parada como destino), lista para abrirse
directamente en el navegador o en la aplicación de Google Maps del móvil
del conductor.
"""

from urllib.parse import urlencode

from datos.modelos import Nodo

URL_BASE_GOOGLE_MAPS = "https://www.google.com/maps/dir/"


def generar_enlace_google_maps(
    depot: Nodo, paradas: list[Nodo], incluir_regreso: bool = True
) -> str:
    """
    Genera la URL de Google Maps para una ruta completa: origen en el
    depósito y el resto de paradas en el mismo orden de la ruta optimizada.

    Args:
        depot: Nodo del depósito (origen de la ruta).
        paradas: Secuencia ordenada de clientes a visitar.
        incluir_regreso: Si es True el destino es el propio depósito y todos
            los clientes son puntos intermedios, de modo que el itinerario
            que ve el conductor incluye la vuelta a la base. Si es False el
            destino es el último cliente.

    Returns:
        La URL completa de Google Maps para abrir la ruta.

    Raises:
        ValueError: Si la ruta no tiene ninguna parada.
    """
    if not paradas:
        raise ValueError("La ruta no contiene ninguna parada")

    if incluir_regreso:
        destino = depot
        puntos_intermedios = paradas
    else:
        destino = paradas[-1]
        puntos_intermedios = paradas[:-1]

    parametros = {
        "api": "1",
        "origin": f"{depot.lat},{depot.lon}",
        "destination": f"{destino.lat},{destino.lon}",
    }
    if puntos_intermedios:
        parametros["waypoints"] = "|".join(f"{parada.lat},{parada.lon}" for parada in puntos_intermedios)

    return f"{URL_BASE_GOOGLE_MAPS}?{urlencode(parametros, safe='|,')}"
