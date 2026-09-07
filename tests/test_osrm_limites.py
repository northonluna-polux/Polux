"""
Tests de las salvaguardas de `utils/osrm.py`.

No se realiza ninguna petición de red: se comprueban únicamente los límites
que se validan antes de construir la petición y la gestión del caché.
"""

import pytest

from datos.modelos import Nodo
from utils import osrm
from utils.osrm import (
    MAX_ENTRADAS_CACHE,
    MAX_NODOS_OSRM,
    ErrorEnrutamiento,
    MatrizDistancias,
    obtener_matriz_distancias,
)


def _nodos(cantidad: int) -> list[Nodo]:
    """Genera nodos ficticios con coordenadas distintas entre sí."""
    return [
        Nodo(id=i, nombre=f"Nodo {i}", lat=39.0 + i * 0.001, lon=-0.3 - i * 0.001)
        for i in range(cantidad)
    ]


class TestLimiteDeNodos:
    def test_supera_el_limite_lanza_error_sin_tocar_la_red(self):
        nodos = _nodos(MAX_NODOS_OSRM + 1)

        with pytest.raises(ErrorEnrutamiento) as excepcion:
            obtener_matriz_distancias(nodos)

        mensaje = str(excepcion.value)
        assert str(MAX_NODOS_OSRM) in mensaje
        assert "OSRM" in mensaje

    def test_el_limite_exacto_no_se_rechaza_por_tamano(self, monkeypatch):
        """
        Con exactamente el máximo permitido no debe saltar el error de
        tamaño (la petición se intentaría; aquí se corta la red a propósito).
        """
        nodos = _nodos(MAX_NODOS_OSRM)

        def falla_la_red(*_args, **_kwargs):
            raise osrm.requests.exceptions.RequestException("sin red")

        monkeypatch.setattr(osrm.requests, "get", falla_la_red)

        with pytest.raises(ErrorEnrutamiento) as excepcion:
            obtener_matriz_distancias(nodos)

        # El error debe ser de conexión, no del límite de tamaño.
        assert str(MAX_NODOS_OSRM) not in str(excepcion.value)


class TestCacheAcotado:
    def test_el_cache_no_crece_por_encima_del_maximo(self, monkeypatch):
        cache_falso: dict = {}
        monkeypatch.setattr(osrm, "_cache_matrices", cache_falso)

        # Se rellena el caché por encima del límite usando la misma lógica de
        # desalojo que aplica `obtener_matriz_distancias`.
        for indice in range(MAX_ENTRADAS_CACHE + 5):
            while len(cache_falso) >= MAX_ENTRADAS_CACHE:
                cache_falso.pop(next(iter(cache_falso)))
            cache_falso[(indice,)] = MatrizDistancias()

        assert len(cache_falso) <= MAX_ENTRADAS_CACHE

    def test_desaloja_la_entrada_mas_antigua(self):
        cache: dict = {}
        for indice in range(MAX_ENTRADAS_CACHE):
            cache[(indice,)] = MatrizDistancias()

        # Al insertar una más, la primera insertada debe desaparecer.
        while len(cache) >= MAX_ENTRADAS_CACHE:
            cache.pop(next(iter(cache)))
        cache[("nueva",)] = MatrizDistancias()

        assert (0,) not in cache
        assert ("nueva",) in cache
