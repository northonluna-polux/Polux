"""
Tests del lector de instancias de Solomon y del modo evaluación.

Todos los tests son locales: la matriz de distancias de las instancias de
Solomon es euclídea y se construye sin acceder a la red.
"""

import math

import pytest

from algoritmo.optimizador import optimizar
from datos.cargador_solomon import (
    APLICAR_REGLAMENTO_EN_SOLOMON,
    HORA_INICIO_SOLOMON,
    ErrorCargaSolomon,
    cargar_instancia_solomon,
    clase_de_instancia,
    construir_matriz_euclidea,
)
from datos.modelos import MOTIVO_FLOTA, Nodo

#: Instancia mínima escrita a mano, con el mismo formato que las originales.
INSTANCIA_EJEMPLO = """C101

VEHICLE
NUMBER     CAPACITY
  25         200

CUSTOMER
CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE TIME

    0      40         50          0          0       1236          0
    1      45         68         10        912        967         90
    2      45         70         30        825        870         90
    3      42         66         10         65        146         90
"""


@pytest.fixture
def archivo_instancia(tmp_path):
    """Escribe la instancia de ejemplo en un archivo temporal."""
    ruta = tmp_path / "C101.txt"
    ruta.write_text(INSTANCIA_EJEMPLO, encoding="utf-8")
    return str(ruta)


class TestLectorSolomon:
    """Interpretación del formato de las instancias."""

    def test_lee_la_cabecera(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        assert instancia.nombre == "C101"
        assert instancia.num_vehiculos == 25
        assert instancia.capacidad_vehiculo == 200.0

    def test_el_cliente_cero_es_el_deposito(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        assert instancia.depot.id == 0
        assert instancia.depot.es_depot
        assert instancia.depot.lat == 40.0
        assert instancia.depot.lon == 50.0
        # La "due date" del depósito es el horizonte de planificación.
        assert instancia.depot.hora_fin == 1236
        assert instancia.depot.hora_inicio == HORA_INICIO_SOLOMON

    def test_lee_todos_los_clientes_sin_incluir_el_deposito(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        assert [cliente.id for cliente in instancia.clientes] == [1, 2, 3]
        assert all(not cliente.es_depot for cliente in instancia.clientes)

    def test_interpreta_los_campos_de_un_cliente(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)
        cliente_uno = instancia.clientes[0]

        assert cliente_uno.lat == 45.0
        assert cliente_uno.lon == 68.0
        assert cliente_uno.demanda == 10.0
        assert cliente_uno.hora_inicio == 912
        assert cliente_uno.hora_fin == 967
        assert cliente_uno.tiempo_servicio == 90

    def test_los_tiempos_se_conservan_sin_convertir(self, archivo_instancia):
        """
        Los instantes de la instancia se guardan tal cual, sin traducirlos a
        horas del día (912 no debe reinterpretarse como 15:12, por ejemplo).
        """
        instancia = cargar_instancia_solomon(archivo_instancia)

        assert instancia.clientes[1].hora_inicio == 825
        assert instancia.clientes[1].hora_fin == 870

    def test_no_geocodifica_ni_asigna_direccion(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        assert instancia.depot.direccion_original is None
        assert all(cliente.direccion_original is None for cliente in instancia.clientes)

    def test_archivo_inexistente_lanza_error(self):
        with pytest.raises(ErrorCargaSolomon):
            cargar_instancia_solomon("/ruta/que/no/existe/C999.txt")

    def test_archivo_sin_seccion_customer_lanza_error(self, tmp_path):
        ruta = tmp_path / "malo.txt"
        ruta.write_text("X1\n\nVEHICLE\nNUMBER CAPACITY\n 5 100\n", encoding="utf-8")

        with pytest.raises(ErrorCargaSolomon):
            cargar_instancia_solomon(str(ruta))


class TestClaseDeInstancia:
    """Deducción de la clase a partir del nombre."""

    @pytest.mark.parametrize(
        "nombre, clase_esperada",
        [
            ("C101", "C1"),
            ("C201", "C2"),
            ("R101", "R1"),
            ("R211", "R2"),
            ("RC105", "RC1"),
            ("RC201", "RC2"),
            ("rc203.txt", "RC2"),
            ("otra_cosa", "DESCONOCIDA"),
        ],
    )
    def test_deduce_la_clase(self, nombre, clase_esperada):
        assert clase_de_instancia(nombre) == clase_esperada

    def test_la_instancia_expone_su_clase(self, archivo_instancia):
        assert cargar_instancia_solomon(archivo_instancia).clase == "C1"


class TestMatrizEuclidea:
    """Propiedades de la matriz de distancias de las instancias de Solomon."""

    def _nodos(self):
        return [
            Nodo(id=0, nombre="D", lat=0.0, lon=0.0, es_depot=True),
            Nodo(id=1, nombre="A", lat=3.0, lon=4.0),
            Nodo(id=2, nombre="B", lat=-6.0, lon=8.0),
        ]

    def test_la_distancia_es_euclidea(self):
        matriz = construir_matriz_euclidea(self._nodos())

        # (0,0) -> (3,4) forma el triángulo 3-4-5.
        assert matriz.distancia(0, 1) == pytest.approx(5.0)
        # (0,0) -> (-6,8) tiene módulo 10.
        assert matriz.distancia(0, 2) == pytest.approx(10.0)
        assert matriz.distancia(1, 2) == pytest.approx(math.hypot(-9.0, 4.0))

    def test_la_matriz_es_simetrica(self):
        nodos = self._nodos()
        matriz = construir_matriz_euclidea(nodos)

        for origen in nodos:
            for destino in nodos:
                assert matriz.distancia(origen.id, destino.id) == pytest.approx(
                    matriz.distancia(destino.id, origen.id)
                )
                assert matriz.tiempo(origen.id, destino.id) == pytest.approx(
                    matriz.tiempo(destino.id, origen.id)
                )

    def test_el_tiempo_de_viaje_es_igual_a_la_distancia(self):
        nodos = self._nodos()
        matriz = construir_matriz_euclidea(nodos)

        for origen in nodos:
            for destino in nodos:
                assert matriz.tiempo(origen.id, destino.id) == pytest.approx(
                    matriz.distancia(origen.id, destino.id)
                )

    def test_la_distancia_de_un_nodo_a_si_mismo_es_cero(self):
        matriz = construir_matriz_euclidea(self._nodos())

        assert matriz.distancia(1, 1) == 0.0
        assert matriz.tiempo(1, 1) == 0.0


class TestModoEvaluacion:
    """Comportamiento del optimizador al resolver una instancia de referencia."""

    def test_el_reglamento_queda_desactivado(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        resultado = optimizar(
            depot=instancia.depot,
            clientes=instancia.clientes,
            capacidad_vehiculo=instancia.capacidad_vehiculo,
            num_vehiculos=None,
            techo_diario_min=float("inf"),
            matriz=instancia.matriz,
            hora_inicio_jornada=HORA_INICIO_SOLOMON,
            aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        )

        assert APLICAR_REGLAMENTO_EN_SOLOMON is False
        assert resultado.reglamento_aplicado is False
        # Sin Reglamento no se insertan pausas obligatorias.
        assert all(ruta.numero_pausas == 0 for ruta in resultado.rutas)

    def test_la_hora_de_salida_cero_es_valida(self, archivo_instancia):
        """El depósito de estas instancias abre en el instante 0."""
        instancia = cargar_instancia_solomon(archivo_instancia)

        resultado = optimizar(
            depot=instancia.depot,
            clientes=instancia.clientes,
            capacidad_vehiculo=instancia.capacidad_vehiculo,
            num_vehiculos=None,
            techo_diario_min=float("inf"),
            matriz=instancia.matriz,
            hora_inicio_jornada=HORA_INICIO_SOLOMON,
            aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        )

        assert resultado.clientes_servidos == len(instancia.clientes)

    def test_todos_los_clientes_se_atienden_con_flota_ilimitada(self, archivo_instancia):
        instancia = cargar_instancia_solomon(archivo_instancia)

        resultado = optimizar(
            depot=instancia.depot,
            clientes=instancia.clientes,
            capacidad_vehiculo=instancia.capacidad_vehiculo,
            num_vehiculos=None,
            techo_diario_min=float("inf"),
            matriz=instancia.matriz,
            hora_inicio_jornada=HORA_INICIO_SOLOMON,
            aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        )

        assert not resultado.no_asignados
        assert resultado.num_vehiculos_utilizados >= 1

    def test_las_rutas_respetan_el_horizonte_del_deposito(self, archivo_instancia):
        """Ninguna ruta puede regresar al depósito después de su cierre."""
        instancia = cargar_instancia_solomon(archivo_instancia)

        resultado = optimizar(
            depot=instancia.depot,
            clientes=instancia.clientes,
            capacidad_vehiculo=instancia.capacidad_vehiculo,
            num_vehiculos=None,
            techo_diario_min=float("inf"),
            matriz=instancia.matriz,
            hora_inicio_jornada=HORA_INICIO_SOLOMON,
            aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        )

        for ruta in resultado.rutas:
            instante_regreso = HORA_INICIO_SOLOMON + ruta.tiempo_total_min
            assert instante_regreso <= instancia.depot.hora_fin


class TestFlotaIlimitada:
    """La flota ilimitada nunca debe descartar clientes por falta de vehículos."""

    def test_nunca_produce_motivo_flota(self, depot):
        from tests.conftest import cliente, construir_matriz

        # Escenario que con flota acotada sí genera FLOTA: cada cliente cabe
        # en solitario, pero ninguna pareja cabe en la jornada.
        clientes = [cliente(i) for i in range(1, 4)]
        matriz = construir_matriz(
            {
                (0, 1): 140, (0, 2): 140, (0, 3): 140,
                (1, 2): 100, (1, 3): 100, (2, 3): 100,
            }
        )

        acotado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=300,
            matriz=matriz,
        )
        assert any(na.motivo == MOTIVO_FLOTA for na in acotado.no_asignados), (
            "el escenario de control debe producir FLOTA con flota acotada"
        )

        ilimitado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=None,
            techo_diario_min=300,
            matriz=matriz,
        )

        assert not any(na.motivo == MOTIVO_FLOTA for na in ilimitado.no_asignados)
        assert ilimitado.num_vehiculos_utilizados == 3
        assert ilimitado.clientes_servidos == 3
