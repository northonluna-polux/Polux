"""
Fase 3 (opcional): reinserción de clientes no asignados.

Tras la mejora local con 2-opt las rutas son más cortas que al terminar la
construcción de Clarke-Wright, por lo que pueden haber liberado holgura
suficiente para atender a algún cliente que se descartó durante la fase de
construcción.

Este módulo intenta reinsertar esos clientes: para cada uno prueba todas las
posiciones de todas las rutas existentes, valida la ruta resultante con
`simular_ruta` y conserva la inserción factible que menos distancia añade
(criterio de "inserción más barata"). El proceso se repite mientras se
consiga colocar algún cliente, ya que cada inserción cambia la holgura
disponible para las siguientes.
"""

from datos.modelos import (
    MOTIVOS_IRRECUPERABLES,
    ClienteNoAsignado,
    Nodo,
    Ruta,
)
from algoritmo.restricciones import (
    HORA_INICIO_JORNADA_MIN,
    actualizar_metricas_ruta,
    simular_ruta,
)
from utils.osrm import MatrizDistancias


def reinsertar_no_asignados(
    depot: Nodo,
    rutas: list[Ruta],
    no_asignados: list[ClienteNoAsignado],
    capacidad_vehiculo: float,
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    aplicar_reglamento: bool = True,
    incluir_regreso: bool = True,
    habilitada: bool = True,
) -> tuple[list[Ruta], list[ClienteNoAsignado], list[Nodo]]:
    """
    Intenta reinsertar en las rutas existentes los clientes que quedaron sin
    asignar, aprovechando la holgura liberada por la mejora local.

    No se intenta reinsertar a los clientes cuyo motivo de exclusión es
    irrecuperable por definición (sin coordenadas, o con una demanda que
    supera por sí sola la capacidad del vehículo).

    Args:
        depot: Nodo del depósito.
        rutas: Rutas ya optimizadas (se modifican en el sitio si hay éxito).
        no_asignados: Clientes sin asignar tras la construcción y la mejora.
        capacidad_vehiculo: Capacidad máxima de carga de cada vehículo.
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
        matriz: Matriz de distancias/tiempos reales por carretera (OSRM).
        hora_inicio_jornada: Hora de salida del depósito, en minutos desde
            medianoche.
        aplicar_reglamento: Si es False se desactivan las restricciones del
            Reglamento (CE) nº 561/2006 (modo evaluación).
        incluir_regreso: Si la ruta debe contemplar el regreso al depósito.
        habilitada: Si es False la fase no se ejecuta y se devuelven las
            rutas y los clientes sin asignar tal cual. Permite medir la
            aportación de esta fase en los experimentos de validación.

    Returns:
        Una tupla (rutas, no_asignados_restantes, recuperados) donde
        `recuperados` son los nodos que se han conseguido colocar en alguna
        ruta y `no_asignados_restantes` conserva el resto con su motivo
        original.
    """
    if not habilitada:
        return rutas, list(no_asignados), []

    pendientes = [
        no_asignado
        for no_asignado in no_asignados
        if no_asignado.motivo not in MOTIVOS_IRRECUPERABLES
    ]
    recuperados: list[Nodo] = []

    if not rutas or not pendientes:
        return rutas, list(no_asignados), recuperados

    hubo_insercion = True
    while hubo_insercion:
        hubo_insercion = False

        for candidato in list(pendientes):
            mejor_insercion = _buscar_mejor_insercion(
                depot,
                rutas,
                candidato.nodo,
                capacidad_vehiculo,
                techo_diario_min,
                matriz,
                hora_inicio_jornada,
                aplicar_reglamento,
                incluir_regreso,
            )
            if mejor_insercion is None:
                continue

            ruta_destino, secuencia_nueva, resultado = mejor_insercion
            actualizar_metricas_ruta(ruta_destino, secuencia_nueva, resultado)
            pendientes.remove(candidato)
            recuperados.append(candidato.nodo)
            hubo_insercion = True

    ids_recuperados = {nodo.id for nodo in recuperados}
    no_asignados_restantes = [
        no_asignado for no_asignado in no_asignados if no_asignado.nodo.id not in ids_recuperados
    ]

    return rutas, no_asignados_restantes, recuperados


def _buscar_mejor_insercion(
    depot: Nodo,
    rutas: list[Ruta],
    cliente: Nodo,
    capacidad_vehiculo: float,
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int,
    aplicar_reglamento: bool,
    incluir_regreso: bool,
):
    """
    Busca la inserción factible más barata de un cliente entre todas las
    posiciones de todas las rutas.

    Returns:
        Una tupla (ruta, secuencia_nueva, resultado) con la mejor inserción
        encontrada, o None si el cliente no cabe en ninguna ruta.
    """
    mejor: tuple[float, Ruta, list[Nodo], object] | None = None

    for ruta in rutas:
        distancia_previa = ruta.distancia_total_km

        for posicion in range(len(ruta.paradas) + 1):
            secuencia_candidata = (
                ruta.paradas[:posicion] + [cliente] + ruta.paradas[posicion:]
            )
            resultado = simular_ruta(
                depot,
                secuencia_candidata,
                capacidad_vehiculo,
                techo_diario_min,
                matriz,
                hora_inicio_jornada,
                aplicar_reglamento,
                incluir_regreso,
            )
            if not resultado.factible:
                continue

            incremento_distancia = resultado.distancia_total_km - distancia_previa
            if mejor is None or incremento_distancia < mejor[0]:
                mejor = (incremento_distancia, ruta, secuencia_candidata, resultado)

    if mejor is None:
        return None

    _incremento, ruta_destino, secuencia_nueva, resultado = mejor
    return ruta_destino, secuencia_nueva, resultado
