"""
Cálculo de distancias geográficas mediante la fórmula de Haversine.

Este módulo contiene funciones auxiliares para calcular distancias entre
coordenadas geográficas (latitud/longitud) expresadas en grados decimales.
"""

import math

# Radio medio de la Tierra en kilómetros
RADIO_TIERRA_KM = 6371.0

# Velocidad media asumida para el vehículo de reparto (km/h).
# Se utiliza para traducir distancias en kilómetros a tiempos de conducción
# en minutos. Es una simplificación razonable para un entorno urbano/
# interurbano como el de la provincia de Valencia.
VELOCIDAD_MEDIA_KMH = 45.0


def distancia_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en kilómetros entre dos puntos geográficos
    utilizando la fórmula de Haversine.

    Args:
        lat1: Latitud del primer punto en grados decimales.
        lon1: Longitud del primer punto en grados decimales.
        lat2: Latitud del segundo punto en grados decimales.
        lon2: Longitud del segundo punto en grados decimales.

    Returns:
        Distancia entre ambos puntos en kilómetros.
    """
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return RADIO_TIERRA_KM * c


def tiempo_viaje_minutos(distancia_km: float, velocidad_kmh: float = VELOCIDAD_MEDIA_KMH) -> float:
    """
    Convierte una distancia en kilómetros a un tiempo de conducción en minutos,
    asumiendo una velocidad media constante.

    Args:
        distancia_km: Distancia a recorrer en kilómetros.
        velocidad_kmh: Velocidad media asumida en km/h.

    Returns:
        Tiempo de conducción estimado en minutos.
    """
    if velocidad_kmh <= 0:
        raise ValueError("La velocidad media debe ser un valor positivo")
    return (distancia_km / velocidad_kmh) * 60.0


def matriz_distancias(coordenadas: list[tuple[float, float]]) -> list[list[float]]:
    """
    Construye la matriz simétrica de distancias Haversine entre todos los
    puntos de una lista de coordenadas.

    Args:
        coordenadas: Lista de tuplas (lat, lon).

    Returns:
        Matriz de distancias donde matriz[i][j] es la distancia en km entre
        el punto i y el punto j.
    """
    n = len(coordenadas)
    matriz = [[0.0] * n for _ in range(n)]
    for i in range(n):
        lat_i, lon_i = coordenadas[i]
        for j in range(i + 1, n):
            lat_j, lon_j = coordenadas[j]
            d = distancia_haversine(lat_i, lon_i, lat_j, lon_j)
            matriz[i][j] = d
            matriz[j][i] = d
    return matriz
