"""
Tests de las restricciones VRPTW y del Reglamento (CE) nº 561/2006.
"""

import pytest

from algoritmo.restricciones import (
    CONDUCCION_CONTINUA_MAX_MIN,
    CONDUCCION_DIARIA_EXTENDIDA_MIN,
    CONDUCCION_DIARIA_NORMAL_MIN,
    PAUSA_OBLIGATORIA_MIN,
    calcular_techo_diario_minutos,
    simular_ruta,
)
from datos.modelos import MOTIVO_CAPACIDAD, MOTIVO_VENTANA, Nodo
from tests.conftest import cliente, construir_matriz, matriz_uniforme

TECHO_AMPLIO_MIN = 10 * 60


class TestTechoDiario:
    """Cálculo del techo de conducción diaria disponible."""

    def test_semana_completa_agota_el_techo(self):
        assert calcular_techo_diario_minutos(56, permitir_extendido=False) == 0

    def test_semana_por_encima_del_limite_no_da_techo_negativo(self):
        assert calcular_techo_diario_minutos(60, permitir_extendido=False) == 0
        assert calcular_techo_diario_minutos(60, permitir_extendido=True) == 0

    def test_jornada_normal_se_limita_a_nueve_horas(self):
        assert calcular_techo_diario_minutos(0, permitir_extendido=False) == (
            CONDUCCION_DIARIA_NORMAL_MIN
        )

    def test_jornada_extendida_se_limita_a_diez_horas(self):
        assert calcular_techo_diario_minutos(0, permitir_extendido=True) == (
            CONDUCCION_DIARIA_EXTENDIDA_MIN
        )

    def test_remanente_semanal_manda_cuando_es_menor_que_el_diario(self):
        # 52 h ya conducidas dejan 4 h de remanente semanal, por debajo del
        # límite diario de 9 h.
        assert calcular_techo_diario_minutos(52, permitir_extendido=False) == 4 * 60


class TestPausaObligatoria:
    """Inserción de la pausa de 45 minutos exigida por el Reglamento."""

    def test_tramo_de_seis_horas_genera_al_menos_una_pausa(self, depot):
        # Un único desplazamiento de 6 h supera el máximo de conducción
        # continua (4,5 h), por lo que debe forzar una pausa dentro del tramo.
        matriz = construir_matriz({(0, 1): 6 * 60, (1, 0): 1})
        resultado = simular_ruta(
            depot, [cliente(1)], capacidad_vehiculo=10, techo_diario_min=TECHO_AMPLIO_MIN, matriz=matriz
        )

        assert resultado.factible
        assert resultado.numero_pausas >= 1

    def test_tramo_muy_largo_genera_varias_pausas(self, depot):
        # 12 h de conducción continua requieren una pausa cada 4,5 h.
        matriz = construir_matriz({(0, 1): 12 * 60, (1, 0): 1})
        resultado = simular_ruta(
            depot, [cliente(1)], capacidad_vehiculo=10, techo_diario_min=20 * 60, matriz=matriz
        )

        assert resultado.factible
        assert resultado.numero_pausas >= 2

    @pytest.mark.parametrize(
        "minutos_tramo, pausas_esperadas",
        [
            (4 * 60, 0),      # por debajo del máximo continuo: sin pausa
            (6 * 60, 1),      # una pausa a las 4,5 h
            (9 * 60, 2),      # pausas a las 4,5 h y a las 9 h
            (12 * 60, 2),     # dos pausas cubren 12 h de conducción
        ],
    )
    def test_numero_exacto_de_pausas_por_duracion_del_tramo(
        self, depot, minutos_tramo, pausas_esperadas
    ):
        """
        Fija el número de pausas esperado según la duración del tramo. Es la
        regresión que protege el arreglo del cálculo de pausas dentro de un
        mismo tramo: la implementación anterior insertaba como máximo una
        pausa por tramo, sin importar lo largo que fuera.
        """
        cliente_sin_restricciones = Nodo(
            id=1, nombre="Cliente 1", lat=39.47, lon=-0.38, demanda=1, hora_inicio=0, hora_fin=5000
        )
        matriz = construir_matriz({(0, 1): minutos_tramo, (1, 0): 0.0001})

        resultado = simular_ruta(
            depot,
            [cliente_sin_restricciones],
            capacidad_vehiculo=10,
            techo_diario_min=60 * 60,
            matriz=matriz,
            hora_inicio_jornada=0,
        )

        assert resultado.factible
        assert resultado.numero_pausas == pausas_esperadas

    def test_la_pausa_se_refleja_en_el_horario_de_llegada(self, depot):
        """La llegada debe retrasarse al menos la duración de la pausa."""
        minutos_tramo = 6 * 60
        matriz = construir_matriz({(0, 1): minutos_tramo, (1, 0): 1})
        hora_salida = 6 * 60

        resultado = simular_ruta(
            depot,
            [cliente(1)],
            capacidad_vehiculo=10,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=hora_salida,
        )

        assert resultado.factible
        llegada = resultado.horarios_llegada[0]
        assert llegada >= hora_salida + minutos_tramo + PAUSA_OBLIGATORIA_MIN

    def test_conduccion_continua_nunca_supera_el_maximo(self, depot):
        """
        Recorre la ruta reproduciendo la conducción continua y comprueba que
        en ningún momento se superan las 4,5 h sin pausa.
        """
        clientes = [cliente(i) for i in range(1, 5)]
        # Cada tramo dura 2 h: acumulando, se cruza el límite varias veces.
        matriz = matriz_uniforme([0, 1, 2, 3, 4], minutos_entre_nodos=2 * 60)

        resultado = simular_ruta(
            depot, clientes, capacidad_vehiculo=100, techo_diario_min=30 * 60, matriz=matriz
        )
        assert resultado.factible

        # Se reproduce la acumulación tramo a tramo aplicando la misma regla
        # de pausa que el simulador, y se verifica que el máximo se respeta.
        secuencia = [depot] + clientes + [depot]
        conduccion_continua = 0.0
        pausas_reproducidas = 0
        for anterior, actual in zip(secuencia, secuencia[1:]):
            restante = matriz.tiempo(anterior.id, actual.id)
            while restante > 1e-9:
                margen = CONDUCCION_CONTINUA_MAX_MIN - conduccion_continua
                if margen <= 1e-9:
                    conduccion_continua = 0.0
                    pausas_reproducidas += 1
                    margen = CONDUCCION_CONTINUA_MAX_MIN
                porcion = min(restante, margen)
                conduccion_continua += porcion
                restante -= porcion
                assert conduccion_continua <= CONDUCCION_CONTINUA_MAX_MIN + 1e-6

        assert resultado.numero_pausas == pausas_reproducidas


class TestRestriccionesVRPTW:
    """Capacidad y ventanas de tiempo."""

    def test_demanda_superior_a_la_capacidad_se_rechaza_por_capacidad(self, depot):
        matriz = matriz_uniforme([0, 1], minutos_entre_nodos=10)
        resultado = simular_ruta(
            depot,
            [cliente(1, demanda=50)],
            capacidad_vehiculo=10,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        assert not resultado.factible
        assert resultado.motivo == MOTIVO_CAPACIDAD

    def test_ventana_inalcanzable_se_rechaza_por_ventana(self, depot):
        # Salida a las 08:00 y 3 h de viaje: no se puede llegar antes de las 09:00.
        matriz = construir_matriz({(0, 1): 3 * 60, (1, 0): 10})
        cliente_temprano = cliente(1, hora_inicio=7 * 60, hora_fin=9 * 60)

        resultado = simular_ruta(
            depot,
            [cliente_temprano],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert not resultado.factible
        assert resultado.motivo == MOTIVO_VENTANA
        assert resultado.nodo_conflicto is cliente_temprano

    def test_llegada_temprana_espera_a_la_apertura_de_la_ventana(self, depot):
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
        # Llega a las 08:10 pero no puede ser atendido hasta las 10:00.
        assert resultado.horarios_llegada[0] == 10 * 60

    def test_hora_de_salida_configurable_desplaza_las_llegadas(self, depot):
        matriz = construir_matriz({(0, 1): 30, (1, 0): 30})
        argumentos = dict(
            depot=depot,
            paradas=[cliente(1)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        temprano = simular_ruta(**argumentos, hora_inicio_jornada=6 * 60)
        tarde = simular_ruta(**argumentos, hora_inicio_jornada=9 * 60)

        assert temprano.horarios_llegada[0] == 6 * 60 + 30
        assert tarde.horarios_llegada[0] == 9 * 60 + 30
