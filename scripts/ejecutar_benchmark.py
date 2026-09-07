"""
Script de evaluación experimental con instancias de referencia de Solomon.

Resuelve un directorio completo de instancias de Solomon en modo evaluación
(flota ilimitada y Reglamento (CE) nº 561/2006 desactivado, ya que estas
instancias no modelan jornadas laborales) y escribe un CSV con una fila por
instancia y configuración.

Cada instancia se resuelve dos veces: con la fase de reinserción activada y
sin ella, para poder medir su aportación.

Uso:

    python3 scripts/ejecutar_benchmark.py <directorio_instancias> [-s salida.csv]

Criterio de evaluación: los resultados en este campo se ordenan
lexicográficamente por número de vehículos primero, después por tiempo
total de programación, después por distancia total y por último por tiempo
de espera. El orden de las columnas del CSV refleja esa jerarquía.
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

#: Columnas del CSV de resultados, en el orden del criterio de evaluación.
COLUMNAS_RESULTADOS = [
    "instancia",
    "clase",
    "reinsercion",
    "num_vehiculos",
    "tiempo_total_programacion",
    "distancia_total",
    "tiempo_espera_total",
    "clientes_servidos",
    "clientes_no_asignados",
    "tiempo_computo_segundos",
]

#: Extensiones consideradas como archivos de instancia.
EXTENSIONES_INSTANCIA = (".txt", ".dat", "")


def localizar_instancias(directorio: str) -> list[str]:
    """
    Devuelve las rutas de los archivos de instancia de un directorio,
    ordenadas por nombre.

    La búsqueda es recursiva, de modo que funciona tanto con un directorio
    plano como con la organización por clases (`c1/`, `c2/`, `r1/`, ...)
    que genera `scripts/descargar_instancias.py`.

    Args:
        directorio: Directorio que contiene los archivos de instancia.

    Returns:
        Lista ordenada de rutas de archivo.
    """
    if not os.path.isdir(directorio):
        raise NotADirectoryError(f"No es un directorio: {directorio}")

    rutas = []
    for carpeta_actual, _subcarpetas, archivos in os.walk(directorio):
        for nombre_archivo in archivos:
            if os.path.splitext(nombre_archivo)[1].lower() in EXTENSIONES_INSTANCIA:
                rutas.append(os.path.join(carpeta_actual, nombre_archivo))

    return sorted(rutas, key=lambda ruta: os.path.basename(ruta).lower())


def resolver_instancia(
    instancia: InstanciaSolomon, usar_reinsercion: bool
) -> tuple[ResultadoOptimizacion, float]:
    """
    Resuelve una instancia en modo evaluación y mide el tiempo de cómputo.

    Args:
        instancia: Instancia de Solomon ya cargada.
        usar_reinsercion: Si se ejecuta la fase de reinserción.

    Returns:
        Una tupla (resultado, segundos_de_computo).
    """
    instante_inicial = time.perf_counter()
    resultado = optimizar(
        depot=instancia.depot,
        clientes=instancia.clientes,
        capacidad_vehiculo=instancia.capacidad_vehiculo,
        # Flota ilimitada: en el VRPTW estándar el número de vehículos es la
        # magnitud a minimizar, no un dato de entrada.
        num_vehiculos=None,
        # Irrelevante en modo evaluación, pero debe ser positivo por si se
        # reactivara el Reglamento.
        techo_diario_min=float("inf"),
        matriz=instancia.matriz,
        hora_inicio_jornada=HORA_INICIO_SOLOMON,
        aplicar_reglamento=APLICAR_REGLAMENTO_EN_SOLOMON,
        usar_reinsercion=usar_reinsercion,
    )
    segundos = time.perf_counter() - instante_inicial
    return resultado, segundos


def construir_fila(
    instancia: InstanciaSolomon,
    resultado: ResultadoOptimizacion,
    segundos: float,
    usar_reinsercion: bool,
) -> dict:
    """Construye la fila del CSV correspondiente a una ejecución."""
    return {
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
    }


def ejecutar_benchmark(directorio: str, ruta_salida: str) -> list[dict]:
    """
    Resuelve todas las instancias del directorio, con y sin reinserción, y
    escribe los resultados en un CSV.

    Args:
        directorio: Directorio con los archivos de instancia.
        ruta_salida: Ruta del CSV de resultados a generar.

    Returns:
        La lista de filas generadas.
    """
    rutas_instancias = localizar_instancias(directorio)
    if not rutas_instancias:
        print(f"No se han encontrado instancias en: {directorio}")
        return []

    print(f"Instancias encontradas: {len(rutas_instancias)}")
    print(
        "Modo evaluación: flota ilimitada y Reglamento (CE) nº 561/2006 "
        "DESACTIVADO (las instancias de Solomon no modelan jornadas)."
    )
    print()

    filas: list[dict] = []
    for ruta_instancia in rutas_instancias:
        try:
            instancia = cargar_instancia_solomon(ruta_instancia)
        except ErrorCargaSolomon as error:
            print(f"  [OMITIDA] {os.path.basename(ruta_instancia)}: {error}")
            continue

        for usar_reinsercion in (True, False):
            resultado, segundos = resolver_instancia(instancia, usar_reinsercion)
            fila = construir_fila(instancia, resultado, segundos, usar_reinsercion)
            filas.append(fila)
            print(
                f"  {fila['instancia']:<10} {fila['clase']:<4} "
                f"reinserción={fila['reinsercion']:<3} "
                f"vehículos={fila['num_vehiculos']:<4} "
                f"programación={fila['tiempo_total_programacion']:<10} "
                f"distancia={fila['distancia_total']:<10} "
                f"espera={fila['tiempo_espera_total']:<10} "
                f"({fila['tiempo_computo_segundos']} s)"
            )

    _escribir_csv(filas, ruta_salida)
    print(f"\nResultados escritos en: {ruta_salida}")
    return filas


def _escribir_csv(filas: list[dict], ruta_salida: str) -> None:
    """Escribe las filas de resultados en un archivo CSV."""
    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    os.makedirs(carpeta, exist_ok=True)

    with open(ruta_salida, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_RESULTADOS)
        escritor.writeheader()
        escritor.writerows(filas)


#: Métricas resumidas, con su etiqueta y el número de decimales a mostrar.
METRICAS_RESUMEN = [
    ("num_vehiculos", "Vehículos", 2),
    ("tiempo_total_programacion", "Programación", 2),
    ("distancia_total", "Distancia", 2),
    ("tiempo_espera_total", "Espera", 2),
    ("clientes_servidos", "Servidos", 2),
    ("tiempo_computo_segundos", "Cómputo (s)", 4),
]


def _medias_por_clase(filas: list[dict], reinsercion: str) -> dict:
    """Calcula las medias de cada métrica por clase, para una configuración."""
    medias: dict[str, dict] = {}
    for clase in sorted({fila["clase"] for fila in filas}):
        grupo = [
            fila
            for fila in filas
            if fila["clase"] == clase and fila["reinsercion"] == reinsercion
        ]
        if not grupo:
            continue
        medias[clase] = {"instancias": len(grupo)}
        for campo, _etiqueta, _decimales in METRICAS_RESUMEN:
            medias[clase][campo] = statistics.mean(fila[campo] for fila in grupo)
    return medias


def _imprimir_tabla(titulo: str, medias: dict, con_signo: bool = False) -> None:
    """Imprime una tabla de medias por clase."""
    print(f"\n{titulo}")
    encabezado = f"{'Clase':<8}{'Inst.':<7}" + "".join(
        f"{etiqueta:<15}" for _campo, etiqueta, _decimales in METRICAS_RESUMEN
    )
    print(encabezado)
    print("-" * len(encabezado))

    for clase, valores in medias.items():
        linea = f"{clase:<8}{valores['instancias']:<7}"
        for campo, _etiqueta, decimales in METRICAS_RESUMEN:
            formato = f"{{:+.{decimales}f}}" if con_signo else f"{{:.{decimales}f}}"
            linea += f"{formato.format(valores[campo]):<15}"
        print(linea)


def imprimir_resumen_por_clase(filas: list[dict]) -> None:
    """
    Imprime tres tablas resumen agrupadas por clase de instancia: con la
    fase de reinserción activada, sin ella, y la diferencia entre ambas.
    """
    if not filas:
        return

    con = _medias_por_clase(filas, "sí")
    sin = _medias_por_clase(filas, "no")

    _imprimir_tabla("Resumen por clase — CON reinserción (medias)", con)
    _imprimir_tabla("Resumen por clase — SIN reinserción (medias)", sin)

    diferencias: dict[str, dict] = {}
    for clase in con:
        if clase not in sin:
            continue
        diferencias[clase] = {"instancias": con[clase]["instancias"]}
        for campo, _etiqueta, _decimales in METRICAS_RESUMEN:
            diferencias[clase][campo] = con[clase][campo] - sin[clase][campo]

    _imprimir_tabla(
        "Diferencia (con reinserción − sin reinserción)", diferencias, con_signo=True
    )


def main() -> None:
    """Punto de entrada del script."""
    analizador = argparse.ArgumentParser(
        description=(
            "Resuelve un directorio de instancias de Solomon en modo evaluación "
            "(flota ilimitada, sin Reglamento 561/2006) y genera un CSV de resultados."
        )
    )
    analizador.add_argument(
        "directorio", help="Directorio que contiene los archivos de instancia de Solomon"
    )
    analizador.add_argument(
        "-s",
        "--salida",
        default="resultados_benchmark.csv",
        help="Ruta del CSV de resultados (por defecto: resultados_benchmark.csv)",
    )
    argumentos = analizador.parse_args()

    try:
        filas = ejecutar_benchmark(argumentos.directorio, argumentos.salida)
    except NotADirectoryError as error:
        analizador.error(str(error))
        return

    imprimir_resumen_por_clase(filas)


if __name__ == "__main__":
    main()
