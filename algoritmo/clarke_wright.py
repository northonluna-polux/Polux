"""
Fase 1 de construcción de rutas: algoritmo de ahorros de Clarke y Wright.

Dado un depósito y un conjunto de clientes, este módulo construye un
conjunto inicial de rutas fusionando progresivamente rutas individuales
según el ahorro que suponga visitarlas de forma conjunta, siempre que la
ruta resultante siga siendo factible (capacidad del vehículo, ventanas de
tiempo y límites de conducción del Reglamento 561/2006).
"""

from typing import Optional

from datos.modelos import (
    MOTIVO_CAPACIDAD,
    MOTIVO_FLOTA,
    MOTIVO_VENTANA,
    ClienteNoAsignado,
    Nodo,
    Ruta,
    Vehiculo,
)
from algoritmo.restricciones import (
    HORA_INICIO_JORNADA_MIN,
    ResultadoSimulacion,
    simular_ruta,
)
from utils.osrm import MatrizDistancias


def ejecutar_clarke_wright(
    depot: Nodo,
    clientes: list[Nodo],
    capacidad_vehiculo: float,
    num_vehiculos: Optional[int],
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    aplicar_reglamento: bool = True,
    incluir_regreso: bool = True,
) -> tuple[list[Ruta], list[ClienteNoAsignado]]:
    """
    Construye las rutas iniciales mediante el algoritmo de ahorros de
    Clarke-Wright.

    Args:
        depot: Nodo del depósito.
        clientes: Lista de clientes a repartir en rutas.
        capacidad_vehiculo: Capacidad máxima de carga de cada vehículo.
        num_vehiculos: Número máximo de vehículos disponibles, o None para
            flota ilimitada. Con flota ilimitada se usan tantas rutas como
            haga falta y ningún cliente se descarta por motivo FLOTA, que es
            la convención del VRPTW estándar (donde el número de vehículos es
            una variable a minimizar, no un dato de entrada).
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
        matriz: Matriz de distancias/tiempos reales por carretera (OSRM),
            precalculada para el depósito y todos los clientes.
        hora_inicio_jornada: Hora de salida del depósito, en minutos desde
            medianoche.
        aplicar_reglamento: Si es False se desactivan las restricciones del
            Reglamento (CE) nº 561/2006 (modo evaluación).
        incluir_regreso: Si la ruta debe contemplar el regreso al depósito.

    Returns:
        Una tupla (rutas, no_asignados) con las rutas construidas y la lista
        de clientes que no pudieron incluirse en ninguna ruta factible.
    """
    no_asignados: list[ClienteNoAsignado] = []
    clientes_factibles: list[Nodo] = []

    # Descartar de entrada los clientes que ni siquiera son alcanzables en
    # solitario (depósito -> cliente -> depósito).
    for cliente in clientes:
        resultado = simular_ruta(
            depot,
            [cliente],
            capacidad_vehiculo,
            techo_diario_min,
            matriz,
            hora_inicio_jornada,
            aplicar_reglamento,
            incluir_regreso,
        )
        if resultado.factible:
            clientes_factibles.append(cliente)
        else:
            no_asignados.append(
                ClienteNoAsignado(
                    nodo=cliente,
                    motivo=resultado.motivo,
                    detalle=_detalle_motivo(resultado, cliente),
                )
            )

    if not clientes_factibles:
        return [], no_asignados

    rutas_activas: list[list[Nodo]] = [[cliente] for cliente in clientes_factibles]
    cliente_a_ruta: dict[int, list[Nodo]] = {
        cliente.id: ruta for ruta, cliente in zip(rutas_activas, clientes_factibles)
    }

    ahorros = _calcular_ahorros(depot, clientes_factibles, matriz)

    for nodo_i, nodo_j, _ahorro in ahorros:
        ruta_i = cliente_a_ruta[nodo_i.id]
        ruta_j = cliente_a_ruta[nodo_j.id]
        if ruta_i is ruta_j:
            continue

        # Se evalúan todas las fusiones posibles y se conserva la factible de
        # menor distancia total, en lugar de aceptar la primera que resulte
        # factible: ambas orientaciones de la unión pueden ser válidas y no
        # tienen por qué costar lo mismo.
        mejor_fusion = None
        mejor_distancia = None
        for candidato in _candidatos_fusion(ruta_i, ruta_j, nodo_i, nodo_j):
            resultado = simular_ruta(
                depot,
                candidato,
                capacidad_vehiculo,
                techo_diario_min,
                matriz,
                hora_inicio_jornada,
                aplicar_reglamento,
                incluir_regreso,
            )
            if not resultado.factible:
                continue
            if mejor_distancia is None or resultado.distancia_total_km < mejor_distancia:
                mejor_fusion = candidato
                mejor_distancia = resultado.distancia_total_km

        if mejor_fusion is None:
            continue

        rutas_activas.remove(ruta_i)
        rutas_activas.remove(ruta_j)
        rutas_activas.append(mejor_fusion)
        for cliente in mejor_fusion:
            cliente_a_ruta[cliente.id] = mejor_fusion

    if num_vehiculos is None:
        # Flota ilimitada: se conservan todas las rutas construidas y ningún
        # cliente se descarta por falta de vehículos.
        rutas_utilizables = rutas_activas
        rutas_excedentes: list[list[Nodo]] = []
    else:
        # Priorizar las rutas con más clientes si sobran rutas respecto a los
        # vehículos disponibles; el resto queda sin asignar.
        rutas_activas.sort(key=len, reverse=True)
        rutas_utilizables = rutas_activas[:num_vehiculos]
        rutas_excedentes = rutas_activas[num_vehiculos:]

    for ruta in rutas_excedentes:
        for cliente in ruta:
            no_asignados.append(
                ClienteNoAsignado(
                    nodo=cliente,
                    motivo=MOTIVO_FLOTA,
                    detalle="No hay vehículos suficientes disponibles para atender a este cliente hoy",
                )
            )

    rutas_finales: list[Ruta] = []
    for indice, paradas in enumerate(rutas_utilizables, start=1):
        vehiculo = Vehiculo(id=indice, capacidad=capacidad_vehiculo)
        resultado = simular_ruta(
            depot,
            paradas,
            capacidad_vehiculo,
            techo_diario_min,
            matriz,
            hora_inicio_jornada,
            aplicar_reglamento,
            incluir_regreso,
        )
        rutas_finales.append(
            _construir_ruta(vehiculo, paradas, resultado, incluir_regreso)
        )

    return rutas_finales, no_asignados


def _calcular_ahorros(
    depot: Nodo, clientes: list[Nodo], matriz: MatrizDistancias
) -> list[tuple[Nodo, Nodo, float]]:
    """
    Calcula el ahorro S(i,j) = d(depósito,i) + d(depósito,j) - d(i,j) para
    cada par de clientes, usando distancias reales por carretera, ordenado
    de mayor a menor ahorro.

    Nota: al usar distancias por carretera (potencialmente asimétricas por
    calles de sentido único), el ahorro se calcula en la dirección
    depósito -> cliente y cliente_i -> cliente_j, que es una aproximación
    estándar y suficiente para un algoritmo greedy como este.
    """
    ahorros = []
    for indice_i in range(len(clientes)):
        for indice_j in range(indice_i + 1, len(clientes)):
            cliente_i = clientes[indice_i]
            cliente_j = clientes[indice_j]
            distancia_depot_i = matriz.distancia(depot.id, cliente_i.id)
            distancia_depot_j = matriz.distancia(depot.id, cliente_j.id)
            distancia_ij = matriz.distancia(cliente_i.id, cliente_j.id)
            ahorro = distancia_depot_i + distancia_depot_j - distancia_ij
            ahorros.append((cliente_i, cliente_j, ahorro))

    ahorros.sort(key=lambda tupla: tupla[2], reverse=True)
    return ahorros


def _candidatos_fusion(
    ruta_i: list[Nodo], ruta_j: list[Nodo], nodo_i: Nodo, nodo_j: Nodo
) -> list[list[Nodo]]:
    """
    Determina las posibles fusiones válidas entre dos rutas según el
    criterio clásico de Clarke-Wright: solo se pueden unir rutas por sus
    extremos adyacentes al depósito, nunca por un cliente interior.
    """
    candidatos: list[list[Nodo]] = []

    if ruta_i[-1].id == nodo_i.id and ruta_j[0].id == nodo_j.id:
        candidatos.append(ruta_i + ruta_j)

    if ruta_j[-1].id == nodo_j.id and ruta_i[0].id == nodo_i.id:
        candidatos.append(ruta_j + ruta_i)

    return candidatos


def _detalle_motivo(resultado: ResultadoSimulacion, cliente: Nodo) -> str:
    """
    Genera un texto descriptivo en español para el motivo de exclusión.

    Si la simulación ya ha explicado el incumplimiento (por ejemplo un
    rechazo por la hora límite de regreso, que comparte código con las
    ventanas de cliente pero es un problema de jornada), se respeta ese
    texto en lugar de generar uno genérico.
    """
    if resultado.detalle:
        return f"{resultado.detalle} al atender a {cliente.nombre}"

    if resultado.motivo == MOTIVO_CAPACIDAD:
        return f"La demanda de {cliente.nombre} ({cliente.demanda}) supera la capacidad del vehículo"
    if resultado.motivo == MOTIVO_VENTANA:
        return f"No es posible llegar a {cliente.nombre} dentro de su ventana {cliente.ventana_como_texto()}"
    return f"El tiempo de conducción necesario para atender a {cliente.nombre} supera el techo diario disponible"


def _construir_ruta(
    vehiculo: Vehiculo,
    paradas: list[Nodo],
    resultado: ResultadoSimulacion,
    incluir_regreso: bool = True,
) -> Ruta:
    """Construye un objeto Ruta a partir del resultado de su simulación."""
    return Ruta(
        vehiculo=vehiculo,
        paradas=list(paradas),
        distancia_total_km=resultado.distancia_total_km,
        tiempo_total_min=resultado.tiempo_total_min,
        tiempo_conduccion_min=resultado.tiempo_conduccion_min,
        tiempo_espera_min=resultado.tiempo_espera_min,
        horarios_llegada=resultado.horarios_llegada,
        carga_total=resultado.carga_total,
        numero_pausas=resultado.numero_pausas,
        pausas=list(resultado.pausas),
        incluye_regreso=incluir_regreso,
    )
