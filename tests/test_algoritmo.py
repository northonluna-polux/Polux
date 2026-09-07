"""
Tests del algoritmo de optimización: construcción (Clarke-Wright), mejora
local (2-opt) y reinserción de clientes no asignados.
"""

from algoritmo.clarke_wright import ejecutar_clarke_wright
from algoritmo.reinsercion import reinsertar_no_asignados
from algoritmo.restricciones import (
    CONDUCCION_CONTINUA_MAX_MIN,
    actualizar_metricas_ruta,
    simular_ruta,
)
from algoritmo.two_opt import aplicar_2opt
from datos.modelos import (
    MOTIVO_CAPACIDAD,
    MOTIVO_FLOTA,
    ClienteNoAsignado,
    Ruta,
    Vehiculo,
)
from tests.conftest import cliente, construir_matriz, matriz_uniforme

TECHO_AMPLIO_MIN = 9 * 60


def _matriz_en_linea() -> tuple:
    """
    Cuatro clientes dispuestos de forma que el orden 1-2-3-4 no es el más
    corto, para que 2-opt tenga margen de mejora.
    """
    tiempos = {
        (0, 1): 10, (0, 2): 20, (0, 3): 30, (0, 4): 40,
        (1, 2): 10, (1, 3): 20, (1, 4): 30,
        (2, 3): 10, (2, 4): 20,
        (3, 4): 10,
    }
    return construir_matriz(tiempos)


class TestClarkeWright:
    """Fase de construcción."""

    def test_falta_de_vehiculos_se_reporta_como_flota(self, depot):
        """
        Escenario donde cada cliente es atendible en solitario pero ninguna
        pareja cabe en la jornada: quedan más rutas que vehículos, y el
        exceso debe reportarse como FLOTA (no como TIEMPO).
        """
        clientes = [cliente(i) for i in range(1, 4)]
        # Ida y vuelta a un cliente: 280 min (cabe en el techo de 300).
        # Cualquier pareja: 140 + 100 + 140 = 380 min (no cabe).
        tiempos = {
            (0, 1): 140, (0, 2): 140, (0, 3): 140,
            (1, 2): 100, (1, 3): 100, (2, 3): 100,
        }
        matriz = construir_matriz(tiempos)

        rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=300,
            matriz=matriz,
        )

        assert len(rutas) == 1
        assert no_asignados, "se esperaban clientes sin asignar por falta de vehículos"
        assert all(na.motivo == MOTIVO_FLOTA for na in no_asignados)

    def test_cliente_que_excede_la_capacidad_se_reporta_como_capacidad(self, depot):
        clientes = [cliente(1, demanda=5), cliente(2, demanda=500)]
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=10)

        _rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=10,
            num_vehiculos=3,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        motivos_por_cliente = {na.nodo.id: na.motivo for na in no_asignados}
        assert motivos_por_cliente.get(2) == MOTIVO_CAPACIDAD

    def test_todos_los_clientes_factibles_se_asignan_si_hay_vehiculos(self, depot):
        clientes = [cliente(i) for i in range(1, 5)]
        matriz = _matriz_en_linea()

        rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=4,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        asignados = {parada.id for ruta in rutas for parada in ruta.paradas}
        assert not no_asignados
        assert asignados == {1, 2, 3, 4}


class TestDosOpt:
    """Fase de mejora local."""

    def test_la_distancia_no_empeora_nunca(self, depot):
        clientes = [cliente(i) for i in range(1, 5)]
        matriz = _matriz_en_linea()

        rutas, _ = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=2,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        distancias_antes = [ruta.distancia_total_km for ruta in rutas]

        rutas = aplicar_2opt(
            depot=depot,
            rutas=rutas,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        distancias_despues = [ruta.distancia_total_km for ruta in rutas]

        for antes, despues in zip(distancias_antes, distancias_despues):
            assert despues <= antes + 1e-9

    def test_las_rutas_devueltas_siguen_siendo_factibles(self, depot):
        """2-opt no puede convertir una ruta legal en ilegal."""
        clientes = [
            cliente(1, hora_inicio=8 * 60, hora_fin=12 * 60, tiempo_servicio=10),
            cliente(2, hora_inicio=9 * 60, hora_fin=13 * 60, tiempo_servicio=10),
            cliente(3, hora_inicio=10 * 60, hora_fin=14 * 60, tiempo_servicio=10),
            cliente(4, hora_inicio=11 * 60, hora_fin=16 * 60, tiempo_servicio=10),
        ]
        matriz = _matriz_en_linea()

        rutas, _ = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=2,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        rutas = aplicar_2opt(
            depot=depot,
            rutas=rutas,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        for ruta in rutas:
            resultado = simular_ruta(
                depot, ruta.paradas, 100, TECHO_AMPLIO_MIN, matriz
            )
            assert resultado.factible, f"2-opt devolvió una ruta infactible: {ruta.paradas}"
            assert resultado.tiempo_conduccion_min <= TECHO_AMPLIO_MIN

    def test_conduccion_continua_respetada_tras_la_mejora(self, depot):
        """Ninguna ruta mejorada puede exigir más conducción continua que el máximo."""
        clientes = [cliente(i) for i in range(1, 5)]
        matriz = matriz_uniforme([0, 1, 2, 3, 4], minutos_entre_nodos=60)

        rutas, _ = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=2,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        rutas = aplicar_2opt(
            depot=depot,
            rutas=rutas,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        for ruta in rutas:
            secuencia = [depot] + ruta.paradas + [depot]
            for anterior, actual in zip(secuencia, secuencia[1:]):
                # Ningún tramo individual queda sin posibilidad de pausa: el
                # simulador la inserta incluso dentro del tramo.
                tiempo_tramo = matriz.tiempo(anterior.id, actual.id)
                pausas_necesarias = int(tiempo_tramo // CONDUCCION_CONTINUA_MAX_MIN)
                assert pausas_necesarias <= ruta.numero_pausas or tiempo_tramo <= (
                    CONDUCCION_CONTINUA_MAX_MIN
                )


class TestReinsercion:
    """Fase de reinserción de clientes no asignados."""

    def test_no_intenta_reinsertar_motivos_irrecuperables(self, depot):
        """Un cliente cuya demanda excede la capacidad nunca debe recuperarse."""
        clientes = [cliente(1, demanda=5), cliente(2, demanda=500)]
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=10)

        rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=10,
            num_vehiculos=3,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        _rutas, restantes, recuperados = reinsertar_no_asignados(
            depot=depot,
            rutas=rutas,
            no_asignados=no_asignados,
            capacidad_vehiculo=10,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        assert not recuperados
        assert any(na.nodo.id == 2 and na.motivo == MOTIVO_CAPACIDAD for na in restantes)

    def test_recupera_un_cliente_cuando_hay_holgura(self, depot):
        """
        Un cliente descartado por falta de vehículos debe recuperarse si cabe
        en una ruta existente que dispone de holgura.
        """
        cliente_en_ruta = cliente(1)
        cliente_excluido = cliente(2)
        matriz = matriz_uniforme([0, 1, 2], minutos_entre_nodos=15)

        ruta = Ruta(vehiculo=Vehiculo(id=1, capacidad=100), paradas=[cliente_en_ruta])
        resultado = simular_ruta(depot, ruta.paradas, 100, TECHO_AMPLIO_MIN, matriz)
        actualizar_metricas_ruta(ruta, ruta.paradas, resultado)

        no_asignados = [
            ClienteNoAsignado(
                nodo=cliente_excluido, motivo=MOTIVO_FLOTA, detalle="Sin vehículos disponibles"
            )
        ]

        rutas, restantes, recuperados = reinsertar_no_asignados(
            depot=depot,
            rutas=[ruta],
            no_asignados=no_asignados,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        assert [nodo.id for nodo in recuperados] == [2]
        assert not restantes
        assert {parada.id for parada in rutas[0].paradas} == {1, 2}

    def test_elige_la_insercion_mas_barata(self, depot):
        """
        Con dos rutas disponibles, el cliente debe acabar en la que menos
        distancia adicional supone.
        """
        matriz = construir_matriz(
            {
                (0, 1): 10, (0, 2): 10, (0, 3): 10,
                (1, 2): 500, (1, 3): 1,  # el cliente 3 está pegado al cliente 1
                (2, 3): 500,
            }
        )
        cliente_ruta_a = cliente(1)
        cliente_ruta_b = cliente(2)
        cliente_excluido = cliente(3)

        rutas = []
        for indice, parada in enumerate([cliente_ruta_a, cliente_ruta_b], start=1):
            ruta = Ruta(vehiculo=Vehiculo(id=indice, capacidad=100), paradas=[parada])
            resultado = simular_ruta(depot, ruta.paradas, 100, 20 * 60, matriz)
            actualizar_metricas_ruta(ruta, ruta.paradas, resultado)
            rutas.append(ruta)

        rutas, _restantes, recuperados = reinsertar_no_asignados(
            depot=depot,
            rutas=rutas,
            no_asignados=[
                ClienteNoAsignado(nodo=cliente_excluido, motivo=MOTIVO_FLOTA, detalle="")
            ],
            capacidad_vehiculo=100,
            techo_diario_min=20 * 60,
            matriz=matriz,
        )

        assert [nodo.id for nodo in recuperados] == [3]
        # Debe haber entrado en la ruta del cliente 1, no en la del cliente 2.
        assert 3 in {parada.id for parada in rutas[0].paradas}
        assert 3 not in {parada.id for parada in rutas[1].paradas}

    def test_las_rutas_siguen_siendo_factibles_tras_reinsertar(self, depot):
        clientes = [cliente(i, demanda=1) for i in range(1, 6)]
        matriz = matriz_uniforme([0, 1, 2, 3, 4, 5], minutos_entre_nodos=15)

        rutas, no_asignados = ejecutar_clarke_wright(
            depot=depot,
            clientes=clientes,
            capacidad_vehiculo=100,
            num_vehiculos=1,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )
        rutas, _restantes, _recuperados = reinsertar_no_asignados(
            depot=depot,
            rutas=rutas,
            no_asignados=no_asignados,
            capacidad_vehiculo=100,
            techo_diario_min=TECHO_AMPLIO_MIN,
            matriz=matriz,
        )

        for ruta in rutas:
            resultado = simular_ruta(depot, ruta.paradas, 100, TECHO_AMPLIO_MIN, matriz)
            assert resultado.factible
