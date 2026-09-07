"""
Evaluación con flota acotada sobre las instancias de Solomon.

El benchmark estándar (`scripts/ejecutar_benchmark.py`) usa flota ilimitada,
que es la convención del VRPTW. Con flota ilimitada ningún cliente queda sin
asignar, por lo que la fase de reinserción no tiene nada que recuperar y su
aportación medida es exactamente cero.

Este script mide esa aportación en el escenario donde sí puede existir:
limita la flota de cada instancia al número de vehículos de su mejor
solución conocida y resuelve dos veces, con y sin reinserción. Al acotar la
flota aparecen clientes sin asignar (sobre todo con motivo FLOTA), que es
precisamente lo que la reinserción intenta recuperar.

El Reglamento (CE) nº 561/2006 sigue desactivado, igual que en el benchmark
estándar: las instancias de Solomon no modelan jornadas laborales.

Uso:

    python3 scripts/ejecutar_benchmark_flota.py datos/benchmark/solomon \\
        -s resultados/benchmark_flota_acotada.csv
"""

import argparse
import csv
import os
import statistics
import sys
import time

# Permite ejecutar el script directamente desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algoritmo.optimizador import ResultadoOptimizacion, optimizar  # noqa: E402
from datos.cargador_solomon import (  # noqa: E402
    APLICAR_REGLAMENTO_EN_SOLOMON,
    HORA_INICIO_SOLOMON,
    ErrorCargaSolomon,
    InstanciaSolomon,
    cargar_instancia_solomon,
)
from datos.modelos import (  # noqa: E402
    MOTIVO_CAPACIDAD,
    MOTIVO_FLOTA,
    MOTIVO_GEOCODIFICACION,
    MOTIVO_TIEMPO,
    MOTIVO_VENTANA,
)
from scripts.ejecutar_benchmark import COLUMNAS_RESULTADOS, localizar_instancias  # noqa: E402
from scripts.verificar_benchmark import cargar_mejores_conocidos  # noqa: E402

#: Ruta del CSV con las mejores soluciones conocidas.
RUTA_MEJORES_CONOCIDOS = os.path.join("datos", "benchmark", "mejores_conocidos.csv")

#: Motivos de exclusión que se desglosan en el CSV, con el nombre de columna.
MOTIVOS_DESGLOSADOS = [
    (MOTIVO_FLOTA, "sin_asignar_flota"),
    (MOTIVO_VENTANA, "sin_asignar_ventana"),
    (MOTIVO_CAPACIDAD, "sin_asignar_capacidad"),
    (MOTIVO_TIEMPO, "sin_asignar_tiempo"),
    (MOTIVO_GEOCODIFICACION, "sin_asignar_geocodificacion"),
]

#: Esquema del CSV: las columnas del benchmark estándar, más el tope de
#: flota aplicado y el desglose de clientes sin asignar por motivo.
COLUMNAS_FLOTA_ACOTADA = (
    COLUMNAS_RESULTADOS
    + ["num_vehiculos_permitidos"]
    + [columna for _motivo, columna in MOTIVOS_DESGLOSADOS]
)


def resolver_con_flota_acotada(
    instancia: InstanciaSolomon, num_vehiculos: int, usar_reinsercion: bool
) -> tuple[ResultadoOptimizacion, float]:
    """
    Resuelve una instancia con la flota limitada al número indicado, y mide
    el tiempo de cómputo.

    Args:
        instancia: Instancia de Solomon ya cargada.
        num_vehiculos: Número máximo de vehículos permitidos.
        usar_reinsercion: Si se ejecuta la fase de reinserción.

    Returns:
        Una tupla (resultado, segundos_de_computo).
    """
    instante_inicial = time.perf_counter()
    resultado = optimizar(
        depot=instancia.depot,
        clientes=instancia.clientes,
        capacidad_vehiculo=instancia.capacidad_vehiculo,
        num_vehiculos=num_vehiculos,
        techo_diario_min=float("inf"),
        matriz=instancia.matriz,
        hora_inicio_jornada=HORA_INICIO_SOLOMON,
        aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        usar_reinsercion=usar_reinsercion,
    )
    return resultado, time.perf_counter() - instante_inicial


def construir_fila(
    instancia: InstanciaSolomon,
    resultado: ResultadoOptimizacion,
    segundos: float,
    usar_reinsercion: bool,
    num_vehiculos_permitidos: int,
) -> dict:
    """Construye la fila del CSV correspondiente a una ejecución."""
    fila = {
        "instancia": instancia.nombre,
        "clase": instancia.clase,
        "reinsercion": "sí" if usar_reinsercion else "no",
        "num_vehiculos": resultado.num_vehiculos_utilizados,
        "tiempo_total_programacion": round(resultado.tiempo_total_programacion_min, 2),
        "distancia_total": round(resultado.distancia_total_km, 2),
        "tiempo_espera_total": round(resultado.tiempo_espera_total_min, 2),
        "clientes_servidos": resultado.clientes_servidos,
        "clientes_no_asignados": len(resultado.no_asignados),
        "tiempo_computo_segundos": round(segundos, 4),
        "num_vehiculos_permitidos": num_vehiculos_permitidos,
    }

    for motivo, columna in MOTIVOS_DESGLOSADOS:
        fila[columna] = sum(1 for na in resultado.no_asignados if na.motivo == motivo)

    return fila


def ejecutar(directorio: str, ruta_salida: str) -> list[dict]:
    """
    Resuelve todas las instancias con flota acotada, con y sin reinserción,
    y escribe los resultados en un CSV.

    Returns:
        La lista de filas generadas.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mejores = cargar_mejores_conocidos(os.path.join(raiz, RUTA_MEJORES_CONOCIDOS))
    if not mejores:
        print(
            "ERROR: no hay mejores soluciones conocidas en "
            f"{RUTA_MEJORES_CONOCIDOS}, que es de donde se toma el tope de flota.\n"
            "Ejecuta primero scripts/descargar_instancias.py."
        )
        return []

    rutas_instancias = localizar_instancias(directorio)
    if not rutas_instancias:
        print(f"No se han encontrado instancias en: {directorio}")
        return []

    print(f"Instancias encontradas: {len(rutas_instancias)}")
    print(
        "Flota acotada al número de vehículos de la mejor solución conocida de "
        "cada instancia. Reglamento (CE) nº 561/2006 DESACTIVADO."
    )
    print()

    filas: list[dict] = []
    sin_referencia: list[str] = []

    for ruta_instancia in rutas_instancias:
        try:
            instancia = cargar_instancia_solomon(ruta_instancia)
        except ErrorCargaSolomon as error:
            print(f"  [OMITIDA] {os.path.basename(ruta_instancia)}: {error}")
            continue

        referencia = mejores.get(instancia.nombre.lower())
        if referencia is None:
            sin_referencia.append(instancia.nombre)
            print(f"  [OMITIDA] {instancia.nombre}: sin mejor solución conocida")
            continue

        tope = referencia["num_vehiculos"]
        for usar_reinsercion in (True, False):
            resultado, segundos = resolver_con_flota_acotada(
                instancia, tope, usar_reinsercion
            )
            fila = construir_fila(
                instancia, resultado, segundos, usar_reinsercion, tope
            )
            filas.append(fila)
            print(
                f"  {fila['instancia']:<8} {fila['clase']:<4} "
                f"reins={fila['reinsercion']:<3} "
                f"tope={tope:<3} usados={fila['num_vehiculos']:<3} "
                f"servidos={fila['clientes_servidos']:<4} "
                f"sin_asignar={fila['clientes_no_asignados']:<4} "
                f"(FLOTA={fila['sin_asignar_flota']}, VENTANA={fila['sin_asignar_ventana']})"
            )

    if sin_referencia:
        print(f"\nInstancias omitidas por falta de referencia: {len(sin_referencia)}")

    _escribir_csv(filas, ruta_salida)
    print(f"\nResultados escritos en: {ruta_salida}")
    return filas


def _escribir_csv(filas: list[dict], ruta_salida: str) -> None:
    """Escribe las filas de resultados en un archivo CSV."""
    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    os.makedirs(carpeta, exist_ok=True)

    with open(ruta_salida, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_FLOTA_ACOTADA)
        escritor.writeheader()
        escritor.writerows(filas)


def imprimir_aportacion_reinsercion(filas: list[dict]) -> None:
    """
    Informa de la aportación de la fase de reinserción: clientes servidos
    con y sin ella, diferencia absoluta y porcentual, y número de instancias
    en las que cambia algo.
    """
    if not filas:
        return

    con = {fila["instancia"]: fila for fila in filas if fila["reinsercion"] == "sí"}
    sin = {fila["instancia"]: fila for fila in filas if fila["reinsercion"] == "no"}
    instancias = sorted(set(con) & set(sin))

    print("\nAPORTACIÓN DE LA REINSERCIÓN — clientes servidos")
    encabezado = (
        f"{'Clase':<8}{'Inst.':<7}{'Sin reins.':<12}{'Con reins.':<12}"
        f"{'Dif. abs.':<12}{'Dif. %':<10}{'Inst. que cambian':<20}"
    )
    print(encabezado)
    print("-" * len(encabezado))

    clases = sorted({con[nombre]["clase"] for nombre in instancias})
    for clase in clases:
        del_grupo = [n for n in instancias if con[n]["clase"] == clase]
        servidos_con = sum(con[n]["clientes_servidos"] for n in del_grupo)
        servidos_sin = sum(sin[n]["clientes_servidos"] for n in del_grupo)
        cambian = [
            n
            for n in del_grupo
            if con[n]["clientes_servidos"] != sin[n]["clientes_servidos"]
        ]
        diferencia = servidos_con - servidos_sin
        porcentaje = (100 * diferencia / servidos_sin) if servidos_sin else 0.0
        print(
            f"{clase:<8}{len(del_grupo):<7}{servidos_sin:<12}{servidos_con:<12}"
            f"{diferencia:<+12}{porcentaje:<+10.2f}{len(cambian)}/{len(del_grupo):<18}"
        )

    servidos_con = sum(con[n]["clientes_servidos"] for n in instancias)
    servidos_sin = sum(sin[n]["clientes_servidos"] for n in instancias)
    cambian = [
        n for n in instancias if con[n]["clientes_servidos"] != sin[n]["clientes_servidos"]
    ]
    diferencia = servidos_con - servidos_sin
    porcentaje = (100 * diferencia / servidos_sin) if servidos_sin else 0.0
    print("-" * len(encabezado))
    print(
        f"{'TOTAL':<8}{len(instancias):<7}{servidos_sin:<12}{servidos_con:<12}"
        f"{diferencia:<+12}{porcentaje:<+10.2f}{len(cambian)}/{len(instancias):<18}"
    )

    if cambian:
        print("\n  Instancias donde la reinserción recupera clientes:")
        for nombre in cambian:
            recuperados = con[nombre]["clientes_servidos"] - sin[nombre]["clientes_servidos"]
            print(
                f"    {nombre:<8} {sin[nombre]['clientes_servidos']:>3} -> "
                f"{con[nombre]['clientes_servidos']:>3}  ({recuperados:+d})"
            )


def imprimir_distribucion_motivos(filas: list[dict]) -> None:
    """Informa del reparto de clientes sin asignar por motivo de exclusión."""
    if not filas:
        return

    print("\nDISTRIBUCIÓN DE MOTIVOS DE EXCLUSIÓN")
    encabezado = f"{'Reinserción':<14}" + "".join(
        f"{columna.replace('sin_asignar_', '').upper():<16}"
        for _motivo, columna in MOTIVOS_DESGLOSADOS
    ) + f"{'TOTAL':<10}"
    print(encabezado)
    print("-" * len(encabezado))

    for etiqueta in ("no", "sí"):
        grupo = [fila for fila in filas if fila["reinsercion"] == etiqueta]
        linea = f"{etiqueta:<14}"
        total = 0
        for _motivo, columna in MOTIVOS_DESGLOSADOS:
            suma = sum(fila[columna] for fila in grupo)
            total += suma
            linea += f"{suma:<16}"
        linea += f"{total:<10}"
        print(linea)


def imprimir_resumen_metricas(filas: list[dict]) -> None:
    """Imprime las medias por clase de las métricas principales."""
    if not filas:
        return

    print("\nMÉTRICAS POR CLASE (medias, con reinserción)")
    encabezado = (
        f"{'Clase':<8}{'Inst.':<7}{'Tope flota':<12}{'Veh. usados':<13}"
        f"{'Servidos':<11}{'Distancia':<12}{'Cómputo (s)':<12}"
    )
    print(encabezado)
    print("-" * len(encabezado))

    grupo_con = [fila for fila in filas if fila["reinsercion"] == "sí"]
    for clase in sorted({fila["clase"] for fila in grupo_con}):
        del_grupo = [fila for fila in grupo_con if fila["clase"] == clase]
        print(
            f"{clase:<8}{len(del_grupo):<7}"
            f"{statistics.mean(f['num_vehiculos_permitidos'] for f in del_grupo):<12.2f}"
            f"{statistics.mean(f['num_vehiculos'] for f in del_grupo):<13.2f}"
            f"{statistics.mean(f['clientes_servidos'] for f in del_grupo):<11.2f}"
            f"{statistics.mean(f['distancia_total'] for f in del_grupo):<12.2f}"
            f"{statistics.mean(f['tiempo_computo_segundos'] for f in del_grupo):<12.4f}"
        )


def main() -> None:
    """Punto de entrada del script."""
    analizador = argparse.ArgumentParser(
        description=(
            "Resuelve las instancias de Solomon con la flota acotada al número de "
            "vehículos de su mejor solución conocida, con y sin reinserción."
        )
    )
    analizador.add_argument("directorio", help="Directorio con las instancias")
    analizador.add_argument(
        "-s",
        "--salida",
        default=os.path.join("resultados", "benchmark_flota_acotada.csv"),
        help="Ruta del CSV de resultados",
    )
    argumentos = analizador.parse_args()

    try:
        filas = ejecutar(argumentos.directorio, argumentos.salida)
    except NotADirectoryError as error:
        analizador.error(str(error))
        return

    imprimir_resumen_metricas(filas)
    imprimir_aportacion_reinsercion(filas)
    imprimir_distribucion_motivos(filas)


if __name__ == "__main__":
    main()
