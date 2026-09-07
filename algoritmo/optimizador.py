"""
Punto de entrada único del proceso de optimización.

Encadena las tres fases del algoritmo (construcción con Clarke-Wright,
mejora local con 2-opt y reinserción de clientes no asignados) y devuelve
un objeto con las rutas resultantes y las métricas agregadas.

Se define aquí, sin ninguna dependencia de la interfaz gráfica, para que
tanto la aplicación de escritorio como los scripts de evaluación con
instancias de referencia ejecuten exactamente el mismo proceso.
"""

from dataclasses import dataclass, field
from typing import Optional

from algoritmo.clarke_wright import ejecutar_clarke_wright
from algoritmo.reinsercion import reinsertar_no_asignados
from algoritmo.restricciones import HORA_INICIO_JORNADA_MIN
from algoritmo.two_opt import aplicar_2opt
from datos.modelos import ClienteNoAsignado, Nodo, Ruta
from utils.osrm import MatrizDistancias


@dataclass
class ResultadoOptimizacion:
    """
    Resultado completo de una optimización, con las rutas obtenidas y las
    métricas agregadas del criterio de evaluación estándar.
    """

    rutas: list[Ruta] = field(default_factory=list)
    no_asignados: list[ClienteNoAsignado] = field(default_factory=list)
    recuperados: list[Nodo] = field(default_factory=list)
    #: False cuando la optimización se ha ejecutado en modo evaluación, es
    #: decir, sin aplicar el Reglamento (CE) nº 561/2006.
    reglamento_aplicado: bool = True
    #: False cuando la fase de reinserción se ha desactivado expresamente.
    reinsercion_aplicada: bool = True
    #: False cuando las rutas no contemplan el regreso al depósito.
    incluye_regreso: bool = True

    @property
    def num_vehiculos_utilizados(self) -> int:
        """Número de rutas no vacías, es decir, de vehículos realmente usados."""
        return len([ruta for ruta in self.rutas if ruta.paradas])

    @property
    def distancia_total_km(self) -> float:
        """Distancia total recorrida por todas las rutas."""
        return sum(ruta.distancia_total_km for ruta in self.rutas)

    @property
    def tiempo_total_programacion_min(self) -> float:
        """
        Tiempo total de programación: suma de la duración de todas las rutas
        (desplazamiento + espera + servicio, más las pausas si se aplica el
        Reglamento).
        """
        return sum(ruta.tiempo_total_min for ruta in self.rutas)

    @property
    def tiempo_espera_total_min(self) -> float:
        """Tiempo total de espera acumulado en todas las rutas."""
        return sum(ruta.tiempo_espera_min for ruta in self.rutas)

    @property
    def tiempo_conduccion_total_min(self) -> float:
        """Tiempo total de conducción acumulado en todas las rutas."""
        return sum(ruta.tiempo_conduccion_min for ruta in self.rutas)

    @property
    def clientes_servidos(self) -> int:
        """
        Número de clientes incluidos en alguna ruta.

        Se cuenta con `Ruta.clientes()`, que excluye el depósito, para que la
        métrica sea correcta con independencia de si la secuencia de paradas
        llegara a contener el nodo del depósito, y para dejar explícito qué
        se está midiendo. Este valor alimenta las tablas de resultados
        experimentales.
        """
        return sum(len(ruta.clientes()) for ruta in self.rutas)


def optimizar(
    depot: Nodo,
    clientes: list[Nodo],
    capacidad_vehiculo: float,
    num_vehiculos: Optional[int],
    techo_diario_min: float,
    matriz: MatrizDistancias,
    hora_inicio_jornada: int = HORA_INICIO_JORNADA_MIN,
    aplicar_reglamento: bool = True,
    usar_reinsercion: bool = True,
    incluir_regreso: bool = True,
) -> ResultadoOptimizacion:
    """
    Ejecuta el proceso completo de optimización sobre un conjunto de clientes.

    Args:
        depot: Nodo del depósito.
        clientes: Clientes a repartir entre las rutas.
        capacidad_vehiculo: Capacidad máxima de carga de cada vehículo.
        num_vehiculos: Número máximo de vehículos, o None para flota
            ilimitada (ningún cliente se descarta por motivo FLOTA).
        techo_diario_min: Techo de conducción diaria disponible, en minutos.
            Se ignora si `aplicar_reglamento` es False.
        matriz: Matriz de distancias/tiempos entre el depósito y los clientes.
        hora_inicio_jornada: Hora de salida del depósito, en minutos desde
            medianoche (0 en las instancias de referencia).
        aplicar_reglamento: Si es False se desactivan las restricciones del
            Reglamento (CE) nº 561/2006. Solo debe usarse en modo evaluación.
        usar_reinsercion: Si es False se omite la tercera fase (reinserción),
            para poder medir su aportación de forma aislada.
        incluir_regreso: Si es True (habitual) las rutas terminan regresando
            al depósito y ese trayecto cuenta para distancia, tiempo y
            límites de conducción. Si es False la jornada acaba en el último
            cliente (variante de ruta abierta).

    Returns:
        Un ResultadoOptimizacion con las rutas y las métricas agregadas.
    """
    rutas, no_asignados = ejecutar_clarke_wright(
        depot=depot,
        clientes=clientes,
        capacidad_vehiculo=capacidad_vehiculo,
        num_vehiculos=num_vehiculos,
        techo_diario_min=techo_diario_min,
        matriz=matriz,
        hora_inicio_jornada=hora_inicio_jornada,
        aplicar_reglamento=aplicar_reglamento,
        incluir_regreso=incluir_regreso,
    )

    rutas = aplicar_2opt(
        depot=depot,
        rutas=rutas,
        capacidad_vehiculo=capacidad_vehiculo,
        techo_diario_min=techo_diario_min,
        matriz=matriz,
        hora_inicio_jornada=hora_inicio_jornada,
        aplicar_reglamento=aplicar_reglamento,
        incluir_regreso=incluir_regreso,
    )

    rutas, no_asignados, recuperados = reinsertar_no_asignados(
        depot=depot,
        rutas=rutas,
        no_asignados=no_asignados,
        capacidad_vehiculo=capacidad_vehiculo,
        techo_diario_min=techo_diario_min,
        matriz=matriz,
        hora_inicio_jornada=hora_inicio_jornada,
        aplicar_reglamento=aplicar_reglamento,
        incluir_regreso=incluir_regreso,
        habilitada=usar_reinsercion,
    )

    return ResultadoOptimizacion(
        rutas=rutas,
        no_asignados=no_asignados,
        recuperados=recuperados,
        reglamento_aplicado=aplicar_reglamento,
        reinsercion_aplicada=usar_reinsercion,
        incluye_regreso=incluir_regreso,
    )
