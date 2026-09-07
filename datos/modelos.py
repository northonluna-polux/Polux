"""
Modelos de datos del dominio de Polux.

Define las estructuras de datos fundamentales utilizadas por el resto de la
aplicación: nodos (depósito y clientes), vehículos y rutas resultantes de
la optimización.

Todos los tiempos internos se representan en minutos transcurridos desde la
medianoche (00:00 = 0 minutos), tal y como especifica el resto del sistema.
"""

from dataclasses import dataclass, field
from typing import Optional

#: Motivos de exclusión de un cliente (usados tanto por la carga de datos
#: como por el algoritmo de optimización).
MOTIVO_CAPACIDAD = "CAPACIDAD"
MOTIVO_VENTANA = "VENTANA"
MOTIVO_TIEMPO = "TIEMPO"
MOTIVO_FLOTA = "FLOTA"
MOTIVO_GEOCODIFICACION = "GEOCODIFICACIÓN"

#: Motivos que nunca pueden resolverse reintentando la inserción del cliente
#: en una ruta existente: sin coordenadas no hay ubicación que visitar, y una
#: demanda superior a la capacidad del vehículo no cabe en ninguna ruta.
MOTIVOS_IRRECUPERABLES = (MOTIVO_GEOCODIFICACION, MOTIVO_CAPACIDAD)


@dataclass
class Nodo:
    """
    Representa un punto geográfico a visitar: puede ser el depósito o un
    cliente con su propia ventana de tiempo y demanda.

    `lat`/`lon` pueden ser None únicamente para un cliente cuya dirección no
    pudo geocodificarse: en ese caso el nodo nunca participa en el cálculo de
    rutas, solo se muestra en el listado de clientes sin asignar.
    """

    id: int
    nombre: str
    lat: Optional[float]
    lon: Optional[float]
    demanda: float = 0.0
    hora_inicio: int = 0  # minutos desde medianoche
    hora_fin: int = 24 * 60  # minutos desde medianoche
    tiempo_servicio: int = 0  # minutos
    es_depot: bool = False
    direccion_original: Optional[str] = None  # dirección de texto tal como la introdujo el usuario, si la hubo

    def ventana_como_texto(self) -> str:
        """Devuelve la ventana de tiempo del nodo en formato HH:MM-HH:MM."""
        return f"{minutos_a_hhmm(self.hora_inicio)}-{minutos_a_hhmm(self.hora_fin)}"

    def tiene_coordenadas(self) -> bool:
        """Indica si el nodo tiene coordenadas válidas (lat/lon resueltas)."""
        return self.lat is not None and self.lon is not None


@dataclass
class ClienteNoAsignado:
    """
    Representa un cliente que no pudo incluirse en ninguna ruta factible,
    junto con el motivo de exclusión.
    """

    nodo: Nodo
    # Uno de los constantes MOTIVO_* definidos arriba; nunca un literal.
    motivo: str
    detalle: str = ""


@dataclass
class Vehiculo:
    """Representa un vehículo disponible para el reparto."""

    id: int
    capacidad: float


@dataclass
class PausaReglamentaria:
    """
    Pausa obligatoria de descanso exigida por el Reglamento (CE) nº 561/2006
    al alcanzarse el máximo de conducción continua.

    Se registra dónde y cuándo debe realizarse para poder mostrarla en la
    hoja de ruta del conductor: una pausa puede caer en mitad de un
    desplazamiento, sin ningún cliente al que asociarla.
    """

    #: Número de clientes ya atendidos cuando arranca la pausa (0 = antes de
    #: la primera parada). Sirve para intercalarla en el itinerario.
    indice_parada_previa: int
    #: Instante de inicio de la pausa, en minutos desde medianoche.
    instante_inicio: int
    #: Duración de la pausa en minutos.
    duracion_min: int
    #: Nombres del tramo en el que cae la pausa.
    origen: str
    destino: str


@dataclass
class Ruta:
    """
    Representa la ruta asignada a un vehículo: la secuencia ordenada de
    clientes a visitar y las métricas resultantes de simular su ejecución.
    """

    vehiculo: Vehiculo
    paradas: list[Nodo] = field(default_factory=list)
    distancia_total_km: float = 0.0
    tiempo_total_min: float = 0.0
    tiempo_conduccion_min: float = 0.0
    #: Minutos que el vehículo permanece inactivo esperando a que abran las
    #: ventanas de tiempo de los clientes.
    tiempo_espera_min: float = 0.0
    horarios_llegada: list[int] = field(default_factory=list)
    carga_total: float = 0.0
    numero_pausas: int = 0
    #: Detalle de cada pausa obligatoria, para poder mostrarlas en la hoja
    #: de ruta además de contarlas.
    pausas: list[PausaReglamentaria] = field(default_factory=list)
    #: Indica si la ruta contempla el regreso al depósito al terminar.
    incluye_regreso: bool = True

    def clientes(self) -> list[Nodo]:
        """Devuelve las paradas que son clientes (excluye el depósito)."""
        return [nodo for nodo in self.paradas if not nodo.es_depot]


def minutos_a_hhmm(minutos: int) -> str:
    """Convierte minutos desde medianoche a una cadena con formato HH:MM."""
    horas, resto = divmod(int(minutos), 60)
    return f"{horas:02d}:{resto:02d}"


def hhmm_a_minutos(hhmm: str) -> int:
    """Convierte una cadena con formato HH:MM a minutos desde medianoche."""
    horas, minutos = hhmm.strip().split(":")
    return int(horas) * 60 + int(minutos)


def formatear_duracion_minutos(minutos: float) -> str:
    """Formatea una duración en minutos como una cadena '{horas}h {minutos}min'."""
    horas, resto = divmod(int(round(minutos)), 60)
    return f"{horas}h {resto:02d}min"
