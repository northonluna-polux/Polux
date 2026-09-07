"""
Verificación de la validez de los resultados del benchmark de Solomon.

Antes de dar por buenos unos resultados experimentales hay que comprobar
que el modo evaluación está correctamente cableado. Este script vuelve a
resolver cada instancia y valida, de forma independiente al simulador
(recorriendo las rutas a mano con la matriz de distancias), que:

  1. Toda instancia produce al menos una ruta factible y no vacía.
  2. Ningún cliente queda sin asignar por TIEMPO ni por FLOTA, ya que el
     Reglamento está desactivado y la flota es ilimitada.
  3. Ninguna ruta contiene pausas obligatorias.
  4. Toda ruta regresa al depósito antes de su hora de cierre.
  5. Cada cliente se visita exactamente una vez.

Además compara los resultados con las mejores soluciones conocidas
publicadas por SINTEF, si están disponibles.

Uso:

    python3 scripts/verificar_benchmark.py datos/benchmark/solomon
"""

import argparse
import csv
import os
import statistics
import sys

# Permite ejecutar el script directamente desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algoritmo.optimizador import optimizar  # noqa: E402
from datos.cargador_solomon import (  # noqa: E402
    APLICAR_REGLAMENTO_EN_SOLOMON,
    HORA_INICIO_SOLOMON,
    cargar_instancia_solomon,
)
from datos.modelos import MOTIVO_FLOTA, MOTIVO_TIEMPO  # noqa: E402
from scripts.ejecutar_benchmark import localizar_instancias  # noqa: E402

#: Ruta del CSV con las mejores soluciones conocidas.
RUTA_MEJORES_CONOCIDOS = os.path.join("datos", "benchmark", "mejores_conocidos.csv")

#: Tolerancia al comparar tiempos acumulados en coma flotante.
TOLERANCIA = 1e-6


def recorrer_ruta_a_mano(instancia, paradas) -> dict:
    """
    Recorre una ruta paso a paso usando solo la matriz de la instancia, sin
    utilizar `simular_ruta`, para validar de forma independiente lo que
    reporta el optimizador.

    Returns:
        Diccionario con el instante de regreso, la distancia, la carga, la
        espera acumulada y la lista de incumplimientos detectados.
    """
    incumplimientos: list[str] = []
    instante = float(HORA_INICIO_SOLOMON)
    distancia = 0.0
    carga = 0.0
    espera = 0.0

    secuencia = [instancia.depot] + list(paradas) + [instancia.depot]
    for anterior, actual in zip(secuencia, secuencia[1:]):
        distancia += instancia.matriz.distancia(anterior.id, actual.id)
        instante += instancia.matriz.tiempo(anterior.id, actual.id)

        if actual.es_depot:
            continue

        if instante > actual.hora_fin + TOLERANCIA:
            incumplimientos.append(
                f"llega al cliente {actual.id} en {instante:.2f} pero su ventana "
                f"cierra en {actual.hora_fin}"
            )
        if instante < actual.hora_inicio:
            espera += actual.hora_inicio - instante
            instante = float(actual.hora_inicio)

        instante += actual.tiempo_servicio
        carga += actual.demanda

    if carga > instancia.capacidad_vehiculo + TOLERANCIA:
        incumplimientos.append(
            f"carga {carga:.2f} supera la capacidad {instancia.capacidad_vehiculo}"
        )
    if instante > instancia.depot.hora_fin + TOLERANCIA:
        incumplimientos.append(
            f"regresa al depósito en {instante:.2f}, después del cierre "
            f"{instancia.depot.hora_fin}"
        )

    return {
        "instante_regreso": instante,
        "distancia": distancia,
        "carga": carga,
        "espera": espera,
        "incumplimientos": incumplimientos,
    }


def verificar_instancia(ruta_instancia: str, usar_reinsercion: bool = True) -> dict:
    """
    Resuelve una instancia en modo evaluación y comprueba todos los
    invariantes.

    Returns:
        Diccionario con las métricas y la lista de fallos detectados.
    """
    instancia = cargar_instancia_solomon(ruta_instancia)
    resultado = optimizar(
        depot=instancia.depot,
        clientes=instancia.clientes,
        capacidad_vehiculo=instancia.capacidad_vehiculo,
        num_vehiculos=None,
        techo_diario_min=float("inf"),
        matriz=instancia.matriz,
        hora_inicio_jornada=HORA_INICIO_SOLOMON,
        aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        usar_reinsercion=usar_reinsercion,
    )

    fallos: list[str] = []

    # 1. Al menos una ruta factible y no vacía.
    rutas_no_vacias = [ruta for ruta in resultado.rutas if ruta.clientes()]
    if not rutas_no_vacias:
        fallos.append("no ha producido ninguna ruta no vacía")

    # 2. Ningún cliente sin asignar por TIEMPO ni por FLOTA.
    for no_asignado in resultado.no_asignados:
        if no_asignado.motivo in (MOTIVO_TIEMPO, MOTIVO_FLOTA):
            fallos.append(
                f"cliente {no_asignado.nodo.id} sin asignar por {no_asignado.motivo}"
            )

    # 3. Sin pausas obligatorias, ya que el Reglamento está desactivado.
    total_pausas = sum(ruta.numero_pausas for ruta in resultado.rutas)
    if total_pausas:
        fallos.append(f"se han insertado {total_pausas} pausas con el Reglamento desactivado")

    # 4 y 5. Recorrido manual de cada ruta y visitas únicas.
    visitados: list[int] = []
    for ruta in resultado.rutas:
        comprobacion = recorrer_ruta_a_mano(instancia, ruta.clientes())
        for incumplimiento in comprobacion["incumplimientos"]:
            fallos.append(f"ruta {ruta.vehiculo.id}: {incumplimiento}")
        visitados.extend(nodo.id for nodo in ruta.clientes())

    ids_esperados = {cliente.id for cliente in instancia.clientes}
    duplicados = len(visitados) - len(set(visitados))
    if duplicados:
        fallos.append(f"{duplicados} cliente(s) visitados más de una vez")

    sin_visitar = ids_esperados - set(visitados)
    ids_sin_asignar = {na.nodo.id for na in resultado.no_asignados}
    if sin_visitar - ids_sin_asignar:
        fallos.append(
            f"{len(sin_visitar - ids_sin_asignar)} cliente(s) ni visitados ni "
            f"declarados sin asignar"
        )

    return {
        "instancia": instancia.nombre,
        "clase": instancia.clase,
        "num_vehiculos": resultado.num_vehiculos_utilizados,
        "tiempo_total_programacion": resultado.tiempo_total_programacion_min,
        "distancia_total": resultado.distancia_total_km,
        "tiempo_espera_total": resultado.tiempo_espera_total_min,
        "clientes_servidos": resultado.clientes_servidos,
        "clientes_no_asignados": len(resultado.no_asignados),
        "horizonte_deposito": instancia.depot.hora_fin,
        "fallos": fallos,
    }


def cargar_mejores_conocidos(ruta_csv: str) -> dict:
    """Carga las mejores soluciones conocidas indexadas por instancia."""
    if not os.path.isfile(ruta_csv):
        return {}

    mejores = {}
    with open(ruta_csv, encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            if not fila.get("num_vehiculos"):
                continue
            mejores[fila["instancia"].lower()] = {
                "num_vehiculos": int(fila["num_vehiculos"]),
                "distancia_total": float(fila["distancia_total"]),
            }
    return mejores


def main() -> None:
    """Punto de entrada del script."""
    analizador = argparse.ArgumentParser(
        description="Verifica la validez de los resultados del benchmark de Solomon."
    )
    analizador.add_argument("directorio", help="Directorio con las instancias")
    argumentos = analizador.parse_args()

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rutas = localizar_instancias(argumentos.directorio)
    print(f"Verificando {len(rutas)} instancias en modo evaluación...\n")

    resultados = [verificar_instancia(ruta) for ruta in rutas]
    con_fallos = [r for r in resultados if r["fallos"]]

    # --- Informe de las comprobaciones ---
    sin_rutas = [r for r in resultados if r["num_vehiculos"] == 0]
    motivos_prohibidos = [
        r for r in resultados if any("sin asignar por" in f for f in r["fallos"])
    ]
    con_pausas = [r for r in resultados if any("pausas" in f for f in r["fallos"])]
    fuera_horizonte = [
        r for r in resultados if any("después del cierre" in f for f in r["fallos"])
    ]
    ventanas_violadas = [
        r for r in resultados if any("su ventana" in f for f in r["fallos"])
    ]

    print("COMPROBACIONES")
    print(f"  1. Instancias con al menos una ruta no vacía: "
          f"{len(resultados) - len(sin_rutas)}/{len(resultados)}"
          f"{'  [OK]' if not sin_rutas else '  [FALLO]'}")
    print(f"  2. Instancias sin clientes descartados por TIEMPO/FLOTA: "
          f"{len(resultados) - len(motivos_prohibidos)}/{len(resultados)}"
          f"{'  [OK]' if not motivos_prohibidos else '  [FALLO]'}")
    print(f"  3. Instancias sin pausas obligatorias: "
          f"{len(resultados) - len(con_pausas)}/{len(resultados)}"
          f"{'  [OK]' if not con_pausas else '  [FALLO]'}")
    print(f"  4. Instancias cuyas rutas regresan dentro del horizonte: "
          f"{len(resultados) - len(fuera_horizonte)}/{len(resultados)}"
          f"{'  [OK]' if not fuera_horizonte else '  [FALLO]'}")
    print(f"  5. Instancias sin violaciones de ventanas de cliente: "
          f"{len(resultados) - len(ventanas_violadas)}/{len(resultados)}"
          f"{'  [OK]' if not ventanas_violadas else '  [FALLO]'}")

    total_servidos = sum(r["clientes_servidos"] for r in resultados)
    total_no_asignados = sum(r["clientes_no_asignados"] for r in resultados)
    print(f"  6. Clientes servidos en total: {total_servidos} "
          f"(sin asignar: {total_no_asignados})")

    if con_fallos:
        print(f"\nFALLOS DETALLADOS ({len(con_fallos)} instancias):")
        for resultado in con_fallos:
            print(f"  {resultado['instancia']}:")
            for fallo in resultado["fallos"][:5]:
                print(f"    - {fallo}")

    # --- C101 frente a la referencia ---
    c101 = next((r for r in resultados if r["instancia"].lower() == "c101"), None)
    if c101:
        print("\nC101 EN DETALLE")
        print(f"  Vehículos:                {c101['num_vehiculos']}")
        print(f"  Tiempo de programación:   {c101['tiempo_total_programacion']:.2f}")
        print(f"  Distancia total:          {c101['distancia_total']:.2f}")
        print(f"  Tiempo de espera:         {c101['tiempo_espera_total']:.2f}")
        print(f"  Horizonte del depósito:   {c101['horizonte_deposito']}")

    # --- Comparación con las mejores soluciones conocidas ---
    mejores = cargar_mejores_conocidos(os.path.join(raiz, RUTA_MEJORES_CONOCIDOS))
    if mejores:
        print("\nDESVIACIÓN FRENTE A LAS MEJORES SOLUCIONES CONOCIDAS (SINTEF)")
        print(f"  {'Clase':<8}{'Inst.':<7}{'Veh. Polux':<12}{'Veh. mejor':<12}"
              f"{'Dist. Polux':<14}{'Dist. mejor':<14}{'Gap dist.':<10}")
        clases = sorted({r["clase"] for r in resultados})
        for clase in clases:
            grupo = [r for r in resultados if r["clase"] == clase]
            comparables = [
                (r, mejores[r["instancia"].lower()])
                for r in grupo
                if r["instancia"].lower() in mejores
            ]
            if not comparables:
                continue
            veh_polux = statistics.mean(r["num_vehiculos"] for r, _ in comparables)
            veh_mejor = statistics.mean(m["num_vehiculos"] for _, m in comparables)
            dist_polux = statistics.mean(r["distancia_total"] for r, _ in comparables)
            dist_mejor = statistics.mean(m["distancia_total"] for _, m in comparables)
            gap = 100 * (dist_polux - dist_mejor) / dist_mejor
            print(f"  {clase:<8}{len(comparables):<7}{veh_polux:<12.2f}{veh_mejor:<12.2f}"
                  f"{dist_polux:<14.2f}{dist_mejor:<14.2f}{gap:>+8.1f}%")
    else:
        print("\nNo hay mejores soluciones conocidas disponibles para comparar.")

    if con_fallos:
        print("\nRESULTADO: hay comprobaciones fallidas, los resultados NO son válidos.")
        sys.exit(1)

    print("\nRESULTADO: todas las comprobaciones han pasado.")


if __name__ == "__main__":
    main()
