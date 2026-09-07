"""
Verificación de restricciones VRPTW y del Reglamento (CE) nº 561/2006.

Este módulo centraliza:
    - Las constantes de conducción y descanso del Reglamento europeo.
    - El cálculo del techo de conducción diario real, en función de las
      horas ya conducidas esta semana.
    - La simulación completa de una ruta (depósito -> clientes -> depósito),
      que verifica capacidad, ventanas de tiempo y límites de conducción
      usando distancias y tiempos reales por carretera (ver utils/osrm.py).
    - La estimación rápida de factibilidad usada en el resumen
      pre-optimización, basada en distancia en línea recta (Haversine) por
      ser una aproximación instantánea que no requiere conexión a internet.

Simplificación de modelado: se asume que únicamente una pausa dedicada de
45 minutos reinicia el contador de conducción continua; el tiempo de
servicio en cada cliente no se considera una pausa válida a efectos del
Reglamento, lo que resulta en una estimación conservadora (más segura) de
la jornada.
"""

from dataclasses import dataclass, field
from typing import Optional

from datos.modelos import (
    MOTIVO_CAPACIDAD,
    MOTIVO_TIEMPO,
    MOTIVO_VENTANA,
    Nodo,
    PausaReglamentaria,
    Ruta,
    minutos_a_hhmm,
)
from utils.distancia import VELOCIDAD_MEDIA_KMH, distancia_haversine, tiempo_viaje_minutos
from utils.osrm import MatrizDistancias

# --- Constantes del Reglamento (CE) nº 561/2006 ---

#: Conducción continua máxima antes de exigir una pausa (4 horas y 30 min)
CONDUCCION_CONTINUA_MAX_MIN = 4.5 * 60

#: Duración de la pausa obligatoria tras la conducción continua máxima
PAUSA_OBLIGATORIA_MIN = 45

#: Conducción diaria normal máxima (9 horas)
CONDUCCION_DIARIA_NORMAL_MIN = 9 * 60

#: Conducción diaria extendida máxima, permitida hasta 2 veces por semana (10 horas)
CONDUCCION_DIARIA_EXTENDIDA_MIN = 10 * 60

#: Conducción semanal máxima acumulada (56 horas)
CONDUCCION_SEMANAL_MAX_MIN = 56 * 60

#: Número máximo de jornadas extendidas (10h) permitidas por semana
EXTENSIONES_SEMANALES_MAX = 2

#: Umbral por debajo del cual el techo diario se considera críticamente bajo
UMBRAL_TECHO_CRITICO_MIN = 2 * 60

#: Hora de inicio de la jornada de reparto por defecto (08:00), en minutos.
#: Es configurable por el usuario desde el panel de configuración.
HORA_INICIO_JORNADA_MIN = 8 * 60

#: Hora límite de regreso al depósito por defecto (18:00), en minutos.
#: Acota la duración de la jornada, algo que el Reglamento 561/2006 no hace:
#: este limita las horas de conducción, no las horas transcurridas.
HORA_LIMITE_REGRESO_MIN = 18 * 60

#: Tolerancia en minutos usada al comparar acumulados de tiempo en coma
#: flotante, para evitar bucles o pausas espurias por errores de redondeo.
TOLERANCIA_MINUTOS = 1e-9


def calcular_techo_diario_minutos(horas_semana_conducidas: float, permitir_extendido: bool) -> float:
    """
    Calcula el techo real de conducción disponible para la jornada de hoy,
    combinando el límite diario del Reglamento con el remanente semanal.

    techo_diario = min(9h [o 10h si se permite jornada extendida],
                        56h - horas ya conducidas esta semana)

    Args:
        horas_semana_conducidas: Horas ya conducidas esta semana antes de hoy.
        permitir_extendido: Si se permite ampliar la jornada a 10 horas.

    Returns:
        Techo de conducción diaria disponible, en minutos. Nunca negativo.
    """
    restante_semanal_min = CONDUCCION_SEMANAL_MAX_MIN - horas_semana_conducidas * 60
    techo_diario_base_min = (
        CONDUCCION_DIARIA_EXTENDIDA_MIN if permitir_extendido else CONDUCCION_DIARIA_NORMAL_MIN
    )
    return max(0.0, min(techo_diario_base_min, restante_semanal_min))


@dataclass
class ResultadoSimulacion:
    """Resultado de simular la ejecución completa de una ruta candidata."""

    factible: bool
    motivo: str = ""
    nodo_conflicto: Nodo | None = None
    #: Explicación en español del incumplimiento, cuando el motivo por sí
    #: solo resulta ambiguo. Se usa para distinguir un rechazo por la
    #: ventana de un cliente de uno por la hora límite de regreso: ambos
    #: comparten el código MOTIVO_VENTANA pero son problemas distintos.
    detalle: str = ""
    distancia_total_km: float = 0.0
    tiempo_total_min: float = 0.0
    tiempo_conduccion_min: float = 0.0
    #: Suma de los minutos que el vehículo permanece inactivo en los clientes
    #: por haber llegado antes de que se abriera su ventana de tiempo. Es la
    #: cuarta métrica del criterio de evaluación estándar de Solomon.
    tiempo_espera_min: float = 0.0
    horarios_llegada: list[int] = field(default_factory=list)
    numero_pausas: int = 0
    #: Detalle de cada pausa obligatoria insertada durante la ruta.
    pausas: list[PausaReglamentaria] = field(default_factory=list)
    carga_total: float = 0.0


def simular_ruta(
    depot: Nodo,
    paradas: list[Nodo],
    capacidad_vehiculo: float,
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    aplicar_reglamento: bool = True,
    incluir_regreso: bool = True,
) -> ResultadoSimulacion:
    """
    Simula la ejecución de una ruta depósito -> paradas -> depósito,
    comprobando en orden: capacidad del vehículo, límite de conducción diaria
    (insertando pausas obligatorias cuando corresponda) y ventanas de tiempo
    de cada cliente.

    Args:
        depot: Nodo que representa el depósito (origen y destino de la ruta).
        paradas: Secuencia ordenada de clientes a visitar.
        capacidad_vehiculo: Capacidad máxima de carga del vehículo.
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
            Se ignora si `aplicar_reglamento` es False.
        matriz: Matriz de distancias/tiempos reales por carretera (OSRM),
            precalculada para el depósito y todos los clientes.
        hora_inicio_jornada: Instante de salida del depósito, en minutos
            desde medianoche (0 en las instancias de referencia).
        aplicar_reglamento: Si es False se desactivan las restricciones del
            Reglamento (CE) nº 561/2006 (pausas obligatorias y techo de
            conducción diaria). Solo debe usarse en modo evaluación con
            instancias de referencia como las de Solomon, que no tienen
            noción de horas del día. Ver `datos/cargador_solomon.py`.
        incluir_regreso: Si es True (comportamiento habitual) la ruta termina
            regresando al depósito, y ese trayecto cuenta para la distancia,
            el tiempo y los límites de conducción. Si es False la jornada
            acaba en el último cliente (variante de ruta abierta), útil
            cuando el vehículo no necesita volver a la base.

    Returns:
        Un ResultadoSimulacion indicando si la ruta es factible y, en caso
        contrario, el motivo y el nodo donde se produce el incumplimiento.
    """
    carga_total = sum(parada.demanda for parada in paradas)
    if carga_total > capacidad_vehiculo:
        return ResultadoSimulacion(factible=False, motivo=MOTIVO_CAPACIDAD, carga_total=carga_total)

    if aplicar_reglamento and techo_diario_min <= 0:
        return ResultadoSimulacion(factible=False, motivo=MOTIVO_TIEMPO, carga_total=carga_total)

    tiempo_actual = float(hora_inicio_jornada)
    conduccion_continua = 0.0
    conduccion_total = 0.0
    distancia_total = 0.0
    espera_total = 0.0
    horarios_llegada: list[int] = []
    numero_pausas = 0
    pausas: list[PausaReglamentaria] = []
    paradas_completadas = 0

    secuencia = [depot] + list(paradas)
    if incluir_regreso:
        secuencia.append(depot)

    for nodo_anterior, nodo_actual in zip(secuencia, secuencia[1:]):
        distancia_tramo = matriz.distancia(nodo_anterior.id, nodo_actual.id)
        tiempo_tramo = matriz.tiempo(nodo_anterior.id, nodo_actual.id)
        distancia_total += distancia_tramo

        if not aplicar_reglamento:
            # Modo evaluación (p. ej. instancias de Solomon): no existe la
            # noción de jornada laboral, así que no se insertan pausas ni se
            # comprueba el techo de conducción diaria.
            tiempo_actual += tiempo_tramo
            conduccion_total += tiempo_tramo
        else:
            # El tramo se consume por porciones: un único desplazamiento puede
            # ser más largo que el máximo de conducción continua (habitual en
            # rutas interurbanas), por lo que la pausa obligatoria debe poder
            # insertarse también en mitad del tramo, no solo antes de empezarlo.
            tiempo_restante_tramo = tiempo_tramo
            while tiempo_restante_tramo > TOLERANCIA_MINUTOS:
                margen_continuo = CONDUCCION_CONTINUA_MAX_MIN - conduccion_continua
                if margen_continuo <= TOLERANCIA_MINUTOS:
                    pausas.append(
                        PausaReglamentaria(
                            indice_parada_previa=paradas_completadas,
                            instante_inicio=int(tiempo_actual),
                            duracion_min=int(PAUSA_OBLIGATORIA_MIN),
                            origen=nodo_anterior.nombre,
                            destino=nodo_actual.nombre,
                        )
                    )
                    tiempo_actual += PAUSA_OBLIGATORIA_MIN
                    conduccion_continua = 0.0
                    numero_pausas += 1
                    margen_continuo = CONDUCCION_CONTINUA_MAX_MIN

                porcion = min(tiempo_restante_tramo, margen_continuo)
                tiempo_actual += porcion
                conduccion_continua += porcion
                conduccion_total += porcion
                tiempo_restante_tramo -= porcion

                if conduccion_total > techo_diario_min:
                    nodo_conflicto = nodo_actual if not nodo_actual.es_depot else None
                    return ResultadoSimulacion(
                        factible=False,
                        motivo=MOTIVO_TIEMPO,
                        nodo_conflicto=nodo_conflicto,
                        distancia_total_km=distancia_total,
                        tiempo_conduccion_min=conduccion_total,
                        tiempo_espera_min=espera_total,
                        carga_total=carga_total,
                    )

        if not nodo_actual.es_depot:
            if tiempo_actual > nodo_actual.hora_fin:
                return ResultadoSimulacion(
                    factible=False,
                    motivo=MOTIVO_VENTANA,
                    nodo_conflicto=nodo_actual,
                    distancia_total_km=distancia_total,
                    tiempo_conduccion_min=conduccion_total,
                    tiempo_espera_min=espera_total,
                    carga_total=carga_total,
                )
            if tiempo_actual < nodo_actual.hora_inicio:
                # El vehículo llega antes de que abra la ventana: el tiempo
                # que permanece inactivo se contabiliza como espera.
                espera_total += nodo_actual.hora_inicio - tiempo_actual
                tiempo_actual = float(nodo_actual.hora_inicio)

            horarios_llegada.append(int(tiempo_actual))
            tiempo_actual += nodo_actual.tiempo_servicio
            paradas_completadas += 1
        else:
            # Regreso al depósito: el vehículo debe estar de vuelta antes de
            # que este cierre, es decir, antes de la hora límite de regreso.
            #
            # La comprobación se hace al margen del Reglamento 561/2006, que
            # limita las horas *de conducción* pero no la duración de la
            # jornada: una ruta con esperas largas puede alargarse doce o
            # catorce horas sin superar las nueve de conducción. En las
            # instancias de referencia, además, este instante codifica la
            # duración máxima de la ruta.
            if tiempo_actual > nodo_actual.hora_fin:
                return ResultadoSimulacion(
                    factible=False,
                    motivo=MOTIVO_VENTANA,
                    nodo_conflicto=None,
                    detalle=(
                        f"La jornada terminaría a las {minutos_a_hhmm(int(tiempo_actual))}, "
                        f"después de la hora límite de regreso al depósito "
                        f"({minutos_a_hhmm(int(nodo_actual.hora_fin))})"
                    ),
                    distancia_total_km=distancia_total,
                    tiempo_conduccion_min=conduccion_total,
                    tiempo_espera_min=espera_total,
                    carga_total=carga_total,
                )

    return ResultadoSimulacion(
        factible=True,
        distancia_total_km=distancia_total,
        tiempo_total_min=tiempo_actual - hora_inicio_jornada,
        tiempo_conduccion_min=conduccion_total,
        tiempo_espera_min=espera_total,
        horarios_llegada=horarios_llegada,
        numero_pausas=numero_pausas,
        pausas=pausas,
        carga_total=carga_total,
    )


def actualizar_metricas_ruta(
    ruta: Ruta, paradas: list[Nodo], resultado: ResultadoSimulacion
) -> None:
    """
    Actualiza en el sitio la secuencia de paradas de una ruta y todas las
    métricas derivadas de su simulación.

    Se centraliza aquí para que la mejora local (2-opt) y la reinserción de
    clientes no asignados actualicen las rutas exactamente igual.

    Args:
        ruta: Ruta a actualizar.
        paradas: Nueva secuencia ordenada de clientes de la ruta.
        resultado: Resultado de simular esa nueva secuencia.
    """
    ruta.paradas = list(paradas)
    ruta.distancia_total_km = resultado.distancia_total_km
    ruta.tiempo_total_min = resultado.tiempo_total_min
    ruta.tiempo_conduccion_min = resultado.tiempo_conduccion_min
    ruta.tiempo_espera_min = resultado.tiempo_espera_min
    ruta.horarios_llegada = resultado.horarios_llegada
    ruta.carga_total = resultado.carga_total
    ruta.numero_pausas = resultado.numero_pausas
    ruta.pausas = list(resultado.pausas)


def alerta_proximidad_limite(resultado: ResultadoSimulacion, techo_diario_min: float) -> str | None:
    """
    Genera un mensaje de advertencia si una ruta factible se acerca al
    límite de conducción diaria (a partir del 90% del techo disponible).

    Args:
        resultado: Resultado de simular la ruta (debe ser factible).
        techo_diario_min: Techo de conducción diaria disponible, en minutos.

    Returns:
        Un mensaje de advertencia, o None si no hay riesgo de incumplimiento.
    """
    if not resultado.factible or techo_diario_min <= 0:
        return None
    proporcion_usada = resultado.tiempo_conduccion_min / techo_diario_min
    if proporcion_usada >= 0.9:
        return (
            f"Conducción al {proporcion_usada * 100:.0f}% del techo diario "
            f"({resultado.tiempo_conduccion_min:.0f} de {techo_diario_min:.0f} min)"
        )
    return None


@dataclass
class ResumenPreOptimizacion:
    """Resumen mostrado antes de ejecutar la optimización."""

    horas_semana_conducidas: float
    techo_diario_min: float
    numero_clientes: int
    clientes_alcanzables_estimados: int
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN
    hora_limite_regreso: int = HORA_LIMITE_REGRESO_MIN
    advertencias: list[str] = field(default_factory=list)

    @property
    def techo_critico(self) -> bool:
        """Indica si el techo diario disponible es críticamente bajo."""
        return 0 < self.techo_diario_min < UMBRAL_TECHO_CRITICO_MIN

    @property
    def bloqueado(self) -> bool:
        """Indica si la optimización debe bloquearse por falta de horas disponibles."""
        return self.techo_diario_min <= 0


def estimar_clientes_alcanzables(
    depot: Nodo,
    clientes: list[Nodo],
    techo_diario_min: float,
    num_vehiculos: Optional[int],
    velocidad_kmh: float = VELOCIDAD_MEDIA_KMH,
) -> int:
    """
    Estima de forma rápida cuántos clientes son alcanzables hoy, sin ejecutar
    el algoritmo de optimización completo.

    Se calcula el tiempo medio de un viaje de ida y vuelta al depósito más el
    tiempo de servicio de cada cliente, y se divide el techo diario
    disponible (multiplicado por el número de vehículos) entre dicho tiempo
    medio. Es una estimación optimista orientativa, ya que no considera el
    reparto óptimo de clientes entre rutas.

    Args:
        depot: Nodo del depósito.
        clientes: Lista de clientes cargados.
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
        num_vehiculos: Número de vehículos disponibles, o None si la
            flota es ilimitada.
        velocidad_kmh: Velocidad media asumida.

    Returns:
        Número estimado de clientes alcanzables hoy (acotado por el total
        de clientes cargados).
    """
    if not clientes or techo_diario_min <= 0:
        return 0

    if num_vehiculos is None:
        # Flota ilimitada: el número de vehículos deja de ser el factor
        # limitante, así que la estimación no lo acota.
        return len(clientes)

    if num_vehiculos <= 0:
        return 0

    tiempos_estimados = []
    for cliente in clientes:
        distancia_ida = distancia_haversine(depot.lat, depot.lon, cliente.lat, cliente.lon)
        tiempo_ida_vuelta = 2 * tiempo_viaje_minutos(distancia_ida, velocidad_kmh)
        tiempos_estimados.append(tiempo_ida_vuelta + cliente.tiempo_servicio)

    tiempo_medio = sum(tiempos_estimados) / len(tiempos_estimados)
    if tiempo_medio <= 0:
        return len(clientes)

    capacidad_estimada_total = (techo_diario_min * num_vehiculos) / tiempo_medio
    return min(len(clientes), int(capacidad_estimada_total))


def generar_resumen_preoptimizacion(
    depot: Nodo,
    clientes: list[Nodo],
    horas_semana_conducidas: float,
    permitir_extendido: bool,
    num_vehiculos: Optional[int],
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    hora_limite_regreso: int = HORA_LIMITE_REGRESO_MIN,
) -> ResumenPreOptimizacion:
    """
    Construye el resumen pre-optimización con el techo diario, el horario
    de la jornada (salida y límite de regreso), el número de clientes
    cargados, la estimación de factibilidad y las advertencias
    correspondientes.
    """
    techo_diario_min = calcular_techo_diario_minutos(horas_semana_conducidas, permitir_extendido)
    clientes_alcanzables = estimar_clientes_alcanzables(
        depot, clientes, techo_diario_min, num_vehiculos
    )

    resumen = ResumenPreOptimizacion(
        horas_semana_conducidas=horas_semana_conducidas,
        techo_diario_min=techo_diario_min,
        numero_clientes=len(clientes),
        clientes_alcanzables_estimados=clientes_alcanzables,
        hora_inicio_jornada=hora_inicio_jornada,
        hora_limite_regreso=hora_limite_regreso,
    )

    if resumen.bloqueado:
        resumen.advertencias.append(
            "No quedan horas de conducción disponibles esta semana: "
            "la optimización está bloqueada."
        )
    elif resumen.techo_critico:
        resumen.advertencias.append(
            f"Techo diario críticamente bajo: solo {techo_diario_min:.0f} minutos "
            "de conducción disponibles hoy."
        )

    if clientes and clientes_alcanzables < len(clientes):
        resumen.advertencias.append(
            f"Se estima que solo {clientes_alcanzables} de {len(clientes)} clientes "
            "serán alcanzables con el techo diario y los vehículos disponibles."
        )

    return resumen
