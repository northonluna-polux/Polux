"""
Tests del regreso opcional al depósito y del registro detallado de las
pausas obligatorias.
"""

import pytest

from algoritmo.clarke_wright import ejecutar_clarke_wright
from algoritmo.optimizador import optimizar
from algoritmo.restricciones import (
    CONDUCCION_CONTINUA_MAX_MIN,
    PAUSA_OBLIGATORIA_MIN,
    simular_ruta,
)
from datos.modelos import MOTIVO_TIEMPO, MOTIVO_VENTANA, Nodo
from tests.conftest import cliente, construir_matriz, matriz_uniforme
from utils.google_maps import generar_enlace_google_maps

TECHO_AMPLIO_MIN = 40 * 60


def _cliente_sin_restricciones(id_cliente: int) -> Nodo:
    """Cliente con ventana abierta todo el horizonte y sin tiempo de servicio."""
    return Nodo(
        id=id_cliente,
        nombre=f"Cliente {id_cliente}",
        lat=39.47,
        lon=-0.38,
        demanda=1,
        hora_inicio=0,
        hora_fin=100000,
        tiempo_servicio=0,
    )


class TestRegresoAlDeposito:
    """El trayecto de vuelta solo cuenta cuando se pide."""

    def test_sin_regreso_la_distancia_es_menor(self, depot):
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=30)
        paradas = [cliente(1), cliente(2)]
        argumentos = dict(
            depot=depot,
            paradas=paradas,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        con_regreso = simular_ruta(**argumentos, incluir_regreso=True)
        sin_regreso = simular_ruta(**argumentos, incluir_regreso=False)

        assert con_regreso.factible and sin_regreso.factible
        # Se ahorra exactamente el último tramo (cliente 2 -> depósito).
        tramo_vuelta = matriz.distancia(2, 0)
        assert con_regreso.distancia_total_km - sin_regreso.distancia_total_km == pytest.approx(
            tramo_vuelta
        )

    def test_sin_regreso_el_tiempo_de_conduccion_es_menor(self, depot):
        matriz = matriz_uniforme([0, 1], minutos_entre_nodos=45)

        con_regreso = simular_ruta(
            depot, [cliente(1)], 100, TECHO_AMPLIO_MIN, matriz, 8 * 60, incluir_regreso=True
        )
        sin_regreso = simular_ruta(
            depot, [cliente(1)], 100, TECHO_AMPLIO_MIN, matriz, 8 * 60, incluir_regreso=False
        )

        assert con_regreso.tiempo_conduccion_min == pytest.approx(90.0)
        assert sin_regreso.tiempo_conduccion_min == pytest.approx(45.0)

    def test_una_ruta_infactible_con_regreso_puede_ser_factible_sin_el(self, depot):
        """
        Con un techo de 300 min, la ida y vuelta (400 min) no cabe pero la
        ida sola (200 min) sí.
        """
        matriz = construir_matriz({(0, 1): 200, (1, 0): 200})

        con_regreso = simular_ruta(
            depot, [cliente(1)], 100, 300, matriz, 8 * 60, incluir_regreso=True
        )
        sin_regreso = simular_ruta(
            depot, [cliente(1)], 100, 300, matriz, 8 * 60, incluir_regreso=False
        )

        assert not con_regreso.factible
        assert con_regreso.motivo == MOTIVO_TIEMPO
        assert sin_regreso.factible

    def test_el_horizonte_del_deposito_no_se_comprueba_sin_regreso(self, depot):
        """Sin vuelta a la base no hay llegada al depósito que validar."""
        depot_que_cierra_pronto = Nodo(
            id=0, nombre="Depósito", lat=39.47, lon=-0.38, es_depot=True, hora_fin=9 * 60
        )
        matriz = construir_matriz({(0, 1): 120, (1, 0): 120})

        con_regreso = simular_ruta(
            depot_que_cierra_pronto, [cliente(1)], 100, TECHO_AMPLIO_MIN, matriz, 8 * 60,
            incluir_regreso=True,
        )
        sin_regreso = simular_ruta(
            depot_que_cierra_pronto, [cliente(1)], 100, TECHO_AMPLIO_MIN, matriz, 8 * 60,
            incluir_regreso=False,
        )

        # Regresaría a las 12:00, después del cierre del depósito (09:00).
        assert not con_regreso.factible
        assert sin_regreso.factible

    def test_la_bandera_se_propaga_a_las_rutas_y_al_resultado(self, depot):
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=20)
        clientes = [cliente(1), cliente(2)]

        for valor in (True, False):
            resultado = optimizar(
                depot=depot,
                clientes=clientes,
                capacidad_vehiculo=100,
                num_vehiculos=None,
                techo_diario_min=TECHO_AMPLIO_MIN,
                matriz=matriz,
                incluir_regreso=valor,
            )
            assert resultado.incluye_regreso is valor
            assert all(ruta.incluye_regreso is valor for ruta in resultado.rutas)


class TestHoraLimiteDeRegreso:
    """
    La jornada debe terminar antes del cierre del depósito, que se modela
    como la ventana de tiempo del propio nodo del depósito.
    """

    @staticmethod
    def _depot_con_limite(hora_limite_min: int) -> Nodo:
        """Depósito que abre a las 08:00 y cierra a la hora indicada."""
        return Nodo(
            id=0,
            nombre="Depósito",
            lat=39.47,
            lon=-0.38,
            hora_inicio=8 * 60,
            hora_fin=hora_limite_min,
            es_depot=True,
        )

    #: Ida y vuelta de 120 min cada tramo: saliendo a las 08:00 se regresa
    #: a las 12:00.
    _MATRIZ_IDA_Y_VUELTA = {(0, 1): 120, (1, 0): 120}

    def test_se_rechaza_si_el_regreso_supera_el_limite(self):
        depot_local = self._depot_con_limite(11 * 60)  # cierra a las 11:00
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        resultado = simular_ruta(
            depot_local,
            [_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert not resultado.factible
        assert resultado.motivo == MOTIVO_VENTANA
        # No es un problema de la ventana de un cliente, sino de la jornada.
        assert resultado.nodo_conflicto is None

    def test_se_acepta_con_un_limite_mas_tardio(self):
        depot_local = self._depot_con_limite(13 * 60)  # cierra a las 13:00
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        resultado = simular_ruta(
            depot_local,
            [_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert resultado.factible
        assert resultado.tiempo_total_min == pytest.approx(240.0)

    def test_sin_regreso_se_acepta_sea_cual_sea_el_limite(self):
        """Si la jornada acaba en el último cliente, el cierre no aplica."""
        depot_local = self._depot_con_limite(9 * 60)  # cierra a las 09:00
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        resultado = simular_ruta(
            depot_local,
            [_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
            incluir_regreso=False,
        )

        assert resultado.factible

    def test_el_limite_se_aplica_tambien_sin_reglamento(self):
        """
        En modo evaluación el Reglamento se desactiva, pero el cierre del
        depósito sigue acotando la duración de la ruta.
        """
        depot_local = self._depot_con_limite(11 * 60)
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        resultado = simular_ruta(
            depot_local,
            [_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            techo_diario_min=float("inf"),
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
            aplicar_reglamento=False,
        )

        assert not resultado.factible
        assert resultado.motivo == MOTIVO_VENTANA

    def test_una_espera_larga_puede_agotar_la_jornada_sin_agotar_la_conduccion(self):
        """
        Caso que motiva esta restricción: pocas horas de conducción pero una
        espera enorme que estira la jornada más allá del límite.
        """
        depot_local = self._depot_con_limite(18 * 60)
        matriz = construir_matriz({(0, 1): 30, (1, 0): 30})
        # Ventana que no abre hasta las 17:30: llega a las 08:30 y espera.
        cliente_tardio = Nodo(
            id=1,
            nombre="Cliente 1",
            lat=39.47,
            lon=-0.38,
            demanda=1,
            hora_inicio=17 * 60 + 30,
            hora_fin=23 * 60,
            tiempo_servicio=30,
        )

        resultado = simular_ruta(
            depot_local,
            [cliente_tardio],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        # Solo 1 h de conducción, muy por debajo del techo diario...
        assert resultado.tiempo_conduccion_min == pytest.approx(60.0)
        # ...pero el regreso caería a las 18:30, pasado el límite de 18:00.
        assert not resultado.factible
        assert resultado.motivo == MOTIVO_VENTANA

    def test_el_detalle_explica_que_es_un_problema_de_jornada(self):
        """
        El mensaje debe hablar de la jornada y dar la hora estimada de
        regreso, no insinuar que falló la ventana de un cliente.
        """
        depot_local = self._depot_con_limite(11 * 60)
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        resultado = simular_ruta(
            depot_local,
            [_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert "jornada" in resultado.detalle.lower()
        assert "12:00" in resultado.detalle  # hora estimada de regreso
        assert "11:00" in resultado.detalle  # hora límite configurada

    def test_el_detalle_llega_al_cliente_no_asignado(self):
        """
        Un cliente descartado por este motivo debe explicar el problema de
        jornada en el panel de resultados, no el de ventana de cliente.
        """
        depot_local = self._depot_con_limite(11 * 60)
        matriz = construir_matriz(self._MATRIZ_IDA_Y_VUELTA)

        _rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot_local,
            clientes=[_cliente_sin_restricciones(1)],
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )

        assert len(no_asignados) == 1
        detalle = no_asignados[0].detalle.lower()
        assert "jornada" in detalle
        assert "ventana" not in detalle


class TestEnlaceGoogleMaps:
    """El itinerario que ve el conductor debe reflejar si hay vuelta."""

    def test_con_regreso_el_destino_es_el_deposito(self, depot):
        paradas = [cliente(1), cliente(2)]

        enlace = generar_enlace_google_maps(depot, paradas, incluir_regreso=True)

        assert f"destination={depot.lat},{depot.lon}" in enlace
        # Todos los clientes pasan a ser puntos intermedios.
        assert enlace.count("|") == len(paradas) - 1

    def test_sin_regreso_el_destino_es_el_ultimo_cliente(self, depot):
        paradas = [cliente(1), cliente(2)]

        enlace = generar_enlace_google_maps(depot, paradas, incluir_regreso=False)

        assert f"destination={paradas[-1].lat},{paradas[-1].lon}" in enlace


class TestRegistroDePausas:
    """Cada pausa obligatoria debe quedar localizada en el itinerario."""

    def test_el_numero_de_pausas_coincide_con_el_detalle(self, depot):
        matriz = construir_matriz({(0, 1): 12 * 60, (1, 0): 1})

        resultado = simular_ruta(
            depot, [_cliente_sin_restricciones(1)], 100, TECHO_AMPLIO_MIN, matriz, 0
        )

        assert resultado.factible
        assert len(resultado.pausas) == resultado.numero_pausas
        assert resultado.numero_pausas >= 2

    def test_una_pausa_dentro_del_primer_tramo_se_ubica_antes_de_la_primera_parada(self, depot):
        """Un tramo de 6 h obliga a parar sin haber visitado a nadie todavía."""
        matriz = construir_matriz({(0, 1): 6 * 60, (1, 0): 1})

        resultado = simular_ruta(
            depot, [_cliente_sin_restricciones(1)], 100, TECHO_AMPLIO_MIN, matriz, 0
        )

        assert resultado.numero_pausas == 1
        pausa = resultado.pausas[0]
        assert pausa.indice_parada_previa == 0
        assert pausa.instante_inicio == int(CONDUCCION_CONTINUA_MAX_MIN)
        assert pausa.duracion_min == int(PAUSA_OBLIGATORIA_MIN)
        assert pausa.origen == depot.nombre
        assert pausa.destino == "Cliente 1"

    def test_una_pausa_posterior_se_ubica_tras_la_parada_correcta(self, depot):
        """
        Dos tramos de 200 min: la pausa cae en el segundo, cuando ya se ha
        atendido a un cliente.
        """
        matriz = construir_matriz(
            {(0, 1): 200, (1, 2): 200, (2, 0): 1, (0, 2): 200, (1, 0): 200, (2, 1): 200}
        )
        clientes = [_cliente_sin_restricciones(1), _cliente_sin_restricciones(2)]

        resultado = simular_ruta(depot, clientes, 100, TECHO_AMPLIO_MIN, matriz, 0)

        assert resultado.numero_pausas >= 1
        primera_pausa = resultado.pausas[0]
        assert primera_pausa.indice_parada_previa == 1
        assert primera_pausa.origen == "Cliente 1"
        assert primera_pausa.destino == "Cliente 2"

    def test_sin_reglamento_no_se_registra_ninguna_pausa(self, depot):
        matriz = construir_matriz({(0, 1): 12 * 60, (1, 0): 1})

        resultado = simular_ruta(
            depot,
            [_cliente_sin_restricciones(1)],
            100,
            TECHO_AMPLIO_MIN,
            matriz,
            0,
            aplicar_reglamento=False,
        )

        assert resultado.factible
        assert resultado.numero_pausas == 0
        assert resultado.pausas == []

    def test_las_pausas_sobreviven_a_las_fases_posteriores(self, depot):
        """2-opt y la reinserción reescriben las métricas de cada ruta."""
        matriz = matriz_uniforme([0, 1, 2, 3], minutos_entre_nodos=120)
        clientes = [_cliente_sin_restricciones(i) for i in range(1, 4)]

        resultado = optimizar(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=None,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
            hora_inicio_jornada=0,
        )

        for ruta in resultado.rutas:
            assert len(ruta.pausas) == ruta.numero_pausas
            recalculo = simular_ruta(
                depot, ruta.paradas, 100, TECHO_AMPLIO_MIN, matriz, 0
            )
            assert len(ruta.pausas) == len(recalculo.pausas)
