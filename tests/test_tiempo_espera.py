"""
Tests de la métrica de tiempo de espera.

El tiempo de espera es la suma de los minutos que el vehículo permanece
inactivo en los clientes por haber llegado antes de que abriera su ventana
de tiempo. Es la cuarta métrica del criterio de evaluación de Solomon.
"""

import pytest

from algoritmo.optimizador import optimizar
from algoritmo.restricciones import simular_ruta
from tests.conftest import cliente, construir_matriz, matriz_uniforme

TECHO_AMPLIO_MIN = 20 * 60


class TestTiempoEsperaEnUnaRuta:
    """Cálculo de la espera en `simular_ruta`."""

    def test_es_cero_si_todas_las_llegadas_caen_dentro_de_la_ventana(self):
        """
        Ventanas abiertas de par en par: el vehículo nunca tiene que esperar.
        """
        depot_local = cliente(0)
        depot_local.es_depot = True
        clientes = [
            cliente(1, hora_inicio=0, hora_fin=2000, tiempo_servicio=10),
            cliente(2, hora_inicio=0, hora_fin=2000, tiempo_servicio=10),
        ]
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=30)

        resultado = simular_ruta(
            depot_local,
            clientes,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=0,
        )

        assert resultado.factible
        assert resultado.tiempo_espera_min == pytest.approx(0.0)

    def test_es_positiva_si_alguna_llegada_es_temprana(self, depot):
        """
        Llega al cliente a las 08:10 pero su ventana abre a las 10:00, así que
        espera exactamente 110 minutos.
        """
        matriz = construir_matriz({(0, 1): 10, (1, 0): 10})

        resultado = simular_ruta(
            depot,
            [cliente(1, hora_inicio=10 * 60, hora_fin=12 * 60)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert resultado.factible
        assert resultado.tiempo_espera_min == pytest.approx(110.0)

    def test_acumula_la_espera_de_varios_clientes(self, depot):
        """La espera de la ruta es la suma de las esperas de cada parada."""
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=10)
        clientes = [
            # Llega a las 08:10, abre a las 09:00 -> espera 50 min.
            cliente(1, hora_inicio=9 * 60, hora_fin=18 * 60, tiempo_servicio=0),
            # Sale a las 09:00, llega a las 09:10, abre a las 11:00 -> 110 min.
            cliente(2, hora_inicio=11 * 60, hora_fin=18 * 60, tiempo_servicio=0),
        ]

        resultado = simular_ruta(
            depot,
            clientes,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert resultado.factible
        assert resultado.tiempo_espera_min == pytest.approx(50.0 + 110.0)

    def test_la_espera_esta_incluida_en_el_tiempo_total(self, depot):
        """El tiempo total de la ruta debe cubrir desplazamiento y espera."""
        matriz = construir_matriz({(0, 1): 10, (1, 0): 10})

        resultado = simular_ruta(
            depot,
            [cliente(1, hora_inicio=10 * 60, hora_fin=12 * 60, tiempo_servicio=15)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        # 10 ida + 110 espera + 15 servicio + 10 vuelta = 145 min.
        assert resultado.tiempo_espera_min == pytest.approx(110.0)
        assert resultado.tiempo_total_min == pytest.approx(145.0)


class TestTiempoEsperaAgregado:
    """Agregación de la espera en el resultado de la optimización."""

    def test_el_agregado_es_la_suma_de_las_rutas(self, depot):
        clientes = [
            cliente(1, hora_inicio=10 * 60, hora_fin=18 * 60, tiempo_servicio=10),
            cliente(2, hora_inicio=11 * 60, hora_fin=18 * 60, tiempo_servicio=10),
            cliente(3, hora_inicio=12 * 60, hora_fin=18 * 60, tiempo_servicio=10),
        ]
        matriz = matriz_uniforme([0, 1, 2, 3], minutos_entre_nodos=20)

        resultado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=None,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert resultado.tiempo_espera_total_min == pytest.approx(
            sum(ruta.tiempo_espera_min for ruta in resultado.rutas)
        )
        assert resultado.tiempo_espera_total_min > 0

    def test_la_ruta_conserva_la_espera_tras_todas_las_fases(self, depot):
        """
        La métrica debe sobrevivir a la mejora local y a la reinserción, que
        reescriben las métricas de cada ruta.
        """
        clientes = [
            cliente(i, hora_inicio=11 * 60, hora_fin=18 * 60, tiempo_servicio=5)
            for i in range(1, 5)
        ]
        matriz = matriz_uniforme([0, 1, 2, 3, 4], minutos_entre_nodos=15)

        resultado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=None,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        for ruta in resultado.rutas:
            # Se recalcula la ruta final y debe coincidir con lo almacenado.
            recalculo = simular_ruta(
                depot,
                ruta.paradas,
                100,
                TECHO_AMPLIO_MIN,
                matriz,
                8 * 60,
            )
            assert ruta.tiempo_espera_min == pytest.approx(recalculo.tiempo_espera_min)


class TestToggleReinsercion:
    """El interruptor de la fase de reinserción."""

    def test_desactivada_no_recupera_ningun_cliente(self, depot):
        clientes = [cliente(i) for i in range(1, 4)]
        matriz = construir_matriz(
            {
                (0, 1): 140, (0, 2): 140, (0, 3): 140,
                (1, 2): 100, (1, 3): 100, (2, 3): 100,
            }
        )
        argumentos = dict(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=300,
            matriz=matriz,
        )

        sin_reinsercion = optimizar(**argumentos, usar_reinsercion=False)

        assert sin_reinsercion.reinsercion_aplicada is False
        assert not sin_reinsercion.recuperados

    def test_activada_por_defecto(self, depot):
        clientes = [cliente(1)]
        matriz = matriz_uniforme([0, 1], minutos_entre_nodos=10)

        resultado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        assert resultado.reinsercion_aplicada is True
