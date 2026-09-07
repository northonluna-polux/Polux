"""
Fase 2 de mejora local: heurística 2-opt.

Para cada ruta construida por Clarke-Wright, se prueban todos los
intercambios 2-opt posibles (invertir un segmento de la secuencia de
clientes) y se acepta el intercambio si reduce la distancia total de la
ruta y esta sigue siendo factible. Se repite hasta que no se encuentra
ninguna mejora adicional.
"""

from datos.modelos import Nodo, Ruta
from algoritmo.restricciones import (
    HORA_INICIO_JORNADA_MIN,
    actualizar_metricas_ruta,
    simular_ruta,
)
from utils.osrm import MatrizDistancias

TOLERANCIA_MEJORA_KM = 1e-9


def aplicar_2opt(
    depot: Nodo,
    rutas: list[Ruta],
    capacidad_vehiculo: float,
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    aplicar_reglamento: bool = True,
    incluir_regreso: bool = True,
) -> list[Ruta]:
    """
    Aplica la heurística 2-opt a cada una de las rutas recibidas, buscando
    reducir su distancia total sin violar ninguna restricción.

    Args:
        depot: Nodo del depósito.
        rutas: Rutas construidas en la fase de ahorros de Clarke-Wright.
        capacidad_vehiculo: Capacidad máxima de carga de cada vehículo.
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
        matriz: Matriz de distancias/tiempos reales por carretera (OSRM),
            precalculada para el depósito y todos los clientes.
        hora_inicio_jornada: Hora de salida del depósito, en minutos desde
            medianoche.
        aplicar_reglamento: Si es False se desactivan las restricciones del
            Reglamento (CE) nº 561/2006 (modo evaluación).
        incluir_regreso: Si la ruta debe contemplar el regreso al depósito.

    Returns:
        La misma lista de rutas, con la secuencia de paradas y las métricas
        actualizadas tras la mejora local.
    """
    for ruta in rutas:
        secuencia_mejorada = _mejorar_ruta_2opt(
            depot,
            ruta.paradas,
            capacidad_vehiculo,
            techo_diario_min,
            matriz,
            hora_inicio_jornada,
            aplicar_reglamento,
            incluir_regreso,
        )
        resultado = simular_ruta(
            depot,
            secuencia_mejorada,
            capacidad_vehiculo,
            techo_diario_min,
            matriz,
            hora_inicio_jornada,
            aplicar_reglamento,
            incluir_regreso,
        )
        actualizar_metricas_ruta(ruta, secuencia_mejorada, resultado)

    return rutas


def _mejorar_ruta_2opt(
    depot: Nodo,
    paradas: list[Nodo],
    capacidad_vehiculo: float,
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int,
    aplicar_reglamento: bool,
    incluir_regreso: bool,
) -> list[Nodo]:
    """
    Busca de forma iterativa el mejor intercambio 2-opt para una única
    ruta, aceptando la primera mejora encontrada en cada pasada, hasta
    alcanzar un óptimo local.
    """
    if len(paradas) < 3:
        # Con uno o dos clientes no existe ningún intercambio 2-opt posible
        return list(paradas)

    mejor_secuencia = list(paradas)
    resultado_mejor = simular_ruta(
        depot,
        mejor_secuencia,
        capacidad_vehiculo,
        techo_diario_min,
        matriz,
        hora_inicio_jornada,
        aplicar_reglamento,
        incluir_regreso,
    )

    hay_mejora = True
    while hay_mejora:
        hay_mejora = False
        num_paradas = len(mejor_secuencia)

        for i in range(num_paradas - 1):
            for j in range(i + 1, num_paradas):
                candidata = (
                    mejor_secuencia[:i]
                    + mejor_secuencia[i : j + 1][::-1]
                    + mejor_secuencia[j + 1 :]
                )
                resultado_candidata = simular_ruta(
                    depot,
                    candidata,
                    capacidad_vehiculo,
                    techo_diario_min,
                    matriz,
                    hora_inicio_jornada,
                    aplicar_reglamento,
                    incluir_regreso,
                )
                if (
                    resultado_candidata.factible
                    and resultado_candidata.distancia_total_km
                    < resultado_mejor.distancia_total_km - TOLERANCIA_MEJORA_KM
                ):
                    mejor_secuencia = candidata
                    resultado_mejor = resultado_candidata
                    hay_mejora = True
                    break
            if hay_mejora:
                break

    return mejor_secuencia
