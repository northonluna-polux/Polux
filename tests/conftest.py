"""
Configuración y utilidades compartidas por los tests.

Los tests no acceden a la red: en lugar de consultar OSRM, construyen a mano
objetos `MatrizDistancias` con distancias y tiempos conocidos, lo que además
permite comprobar los límites del Reglamento 561/2006 con valores exactos.
"""

import os
import sys

import pytest

# Permite importar los paquetes del proyecto (algoritmo, datos, utils) al
# ejecutar pytest desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datos.modelos import Nodo  # noqa: E402
from utils.osrm import MatrizDistancias  # noqa: E402


def construir_matriz(tiempos_min: dict, velocidad_km_por_min: float = 1.0) -> MatrizDistancias:
    """
    Construye una `MatrizDistancias` a partir de un diccionario de tiempos
    entre pares de nodos, derivando la distancia del tiempo con una
    equivalencia fija (por defecto 1 km por minuto).

    Los pares no indicados se rellenan de forma simétrica cuando existe el
    par inverso, para que las matrices de los tests sean cómodas de escribir.

    Args:
        tiempos_min: Diccionario {(id_origen, id_destino): minutos}.
        velocidad_km_por_min: Kilómetros recorridos por minuto.

    Returns:
        La matriz de distancias/tiempos correspondiente.
    """
    matriz = MatrizDistancias()
    for (origen, destino), minutos in tiempos_min.items():
        matriz.tiempos_min[(origen, destino)] = float(minutos)
        matriz.distancias_km[(origen, destino)] = float(minutos) * velocidad_km_por_min
        # Simetría por defecto: solo si el par inverso no se ha definido.
        if (destino, origen) not in tiempos_min:
            matriz.tiempos_min[(destino, origen)] = float(minutos)
            matriz.distancias_km[(destino, origen)] = float(minutos) * velocidad_km_por_min
    return matriz


def matriz_uniforme(ids: list[int], minutos_entre_nodos: float) -> MatrizDistancias:
    """Construye una matriz donde todos los pares distintos cuestan lo mismo."""
    tiempos = {
        (origen, destino): minutos_entre_nodos
        for origen in ids
        for destino in ids
        if origen != destino
    }
    return construir_matriz(tiempos)


@pytest.fixture
def depot() -> Nodo:
    """Depósito de pruebas, con la jornada abierta todo el día."""
    return Nodo(id=0, nombre="Depósito", lat=39.47, lon=-0.38, es_depot=True)


def cliente(
    id_cliente: int,
    demanda: float = 1.0,
    hora_inicio: int = 0,
    hora_fin: int = 24 * 60,
    tiempo_servicio: int = 0,
) -> Nodo:
    """Crea un cliente de pruebas con valores por defecto permisivos."""
    return Nodo(
        id=id_cliente,
        nombre=f"Cliente {id_cliente}",
        lat=39.47,
        lon=-0.38,
        demanda=demanda,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        tiempo_servicio=tiempo_servicio,
    )
