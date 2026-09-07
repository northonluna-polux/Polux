"""
Descarga y verificación de las instancias de referencia de Solomon.

Obtiene las 56 instancias de 100 clientes del conjunto de pruebas estándar
del VRPTW desde SINTEF, las organiza en subcarpetas por clase
(`c1`, `c2`, `r1`, `r2`, `rc1`, `rc2`) y comprueba que el resultado es
utilizable: 56 archivos, cada uno con exactamente 100 clientes más el
depósito y una cabecera interpretable.

Además intenta recuperar la tabla de mejores soluciones conocidas que
publica SINTEF, para poder comparar los resultados propios con la
literatura.

Uso:

    python3 scripts/descargar_instancias.py
    python3 scripts/descargar_instancias.py --solo-verificar

Si algún archivo falta o está mal formado se informa de forma explícita en
lugar de fallar en silencio.
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile

import requests

# Permite ejecutar el script directamente desde la raíz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datos.cargador_solomon import (  # noqa: E402
    ErrorCargaSolomon,
    cargar_instancia_solomon,
    clase_de_instancia,
)

#: Archivo comprimido de SINTEF con las 56 instancias de 100 clientes.
URL_ZIP_INSTANCIAS = "https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip"

#: Página de SINTEF con la tabla de mejores soluciones conocidas.
URL_PAGINA_MEJORES = (
    "https://www.sintef.no/projectweb/top/vrptw/solomon-benchmark/100-customers/"
)

#: Cabecera identificable, exigida por la política de uso de sitios públicos.
CABECERA_USER_AGENT = {"User-Agent": "Polux-TFM/1.0"}

TIMEOUT_SEGUNDOS = 90

#: Número de instancias que componen el conjunto de Solomon de 100 clientes.
NUM_INSTANCIAS_ESPERADAS = 56

#: Número de clientes por instancia, sin contar el depósito.
NUM_CLIENTES_ESPERADOS = 100

#: Directorio donde se guardan las instancias, relativo a la raíz del proyecto.
DIRECTORIO_INSTANCIAS = os.path.join("datos", "benchmark", "solomon")

#: Archivo CSV con las mejores soluciones conocidas.
RUTA_MEJORES_CONOCIDOS = os.path.join("datos", "benchmark", "mejores_conocidos.csv")

COLUMNAS_MEJORES_CONOCIDOS = ["instancia", "num_vehiculos", "distancia_total", "fuente"]


class ErrorDescarga(Exception):
    """Excepción lanzada cuando la descarga no puede completarse."""


def _raiz_proyecto() -> str:
    """Devuelve la ruta absoluta de la raíz del proyecto."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def descargar_instancias(directorio_destino: str) -> list[str]:
    """
    Descarga el archivo comprimido de SINTEF y extrae las instancias
    organizadas por clase.

    Args:
        directorio_destino: Carpeta donde crear las subcarpetas por clase.

    Returns:
        Lista de rutas de los archivos de instancia escritos.

    Raises:
        ErrorDescarga: Si la descarga falla o el contenido no es un ZIP válido.
    """
    print(f"Descargando instancias desde {URL_ZIP_INSTANCIAS}")
    try:
        respuesta = requests.get(
            URL_ZIP_INSTANCIAS, headers=CABECERA_USER_AGENT, timeout=TIMEOUT_SEGUNDOS
        )
    except requests.exceptions.RequestException as error:
        raise ErrorDescarga(
            f"No se pudo conectar con SINTEF para descargar las instancias: {error}"
        ) from error

    if respuesta.status_code != 200:
        raise ErrorDescarga(
            f"SINTEF respondió con un error HTTP {respuesta.status_code} al pedir las instancias"
        )

    try:
        archivo_zip = zipfile.ZipFile(io.BytesIO(respuesta.content))
    except zipfile.BadZipFile as error:
        raise ErrorDescarga("El contenido descargado no es un ZIP válido") from error

    archivos_escritos = []
    for nombre_interno in archivo_zip.namelist():
        nombre_base = os.path.basename(nombre_interno)
        if not nombre_base.lower().endswith(".txt"):
            continue

        clase = clase_de_instancia(nombre_base)
        if clase == "DESCONOCIDA":
            print(f"  [OMITIDO] {nombre_base}: no se reconoce su clase")
            continue

        carpeta_clase = os.path.join(directorio_destino, clase.lower())
        os.makedirs(carpeta_clase, exist_ok=True)

        ruta_destino = os.path.join(carpeta_clase, nombre_base.lower())
        with archivo_zip.open(nombre_interno) as origen:
            contenido = origen.read()
        with open(ruta_destino, "wb") as destino:
            destino.write(contenido)
        archivos_escritos.append(ruta_destino)

    print(f"  Extraídas {len(archivos_escritos)} instancias en {directorio_destino}")
    return archivos_escritos


def verificar_instancias(directorio: str) -> tuple[list[str], list[str]]:
    """
    Comprueba que las instancias descargadas son completas y utilizables.

    Verifica que hay 56 archivos, que cada uno tiene una cabecera
    interpretable y que contiene exactamente 100 clientes más el depósito.

    Args:
        directorio: Carpeta raíz que contiene las subcarpetas por clase.

    Returns:
        Una tupla (instancias_correctas, problemas) con las rutas válidas y
        la lista de problemas detectados, descritos en español.
    """
    problemas: list[str] = []
    correctas: list[str] = []

    if not os.path.isdir(directorio):
        return [], [f"No existe el directorio de instancias: {directorio}"]

    rutas = []
    for carpeta_actual, _subcarpetas, archivos in os.walk(directorio):
        for nombre_archivo in sorted(archivos):
            if nombre_archivo.lower().endswith(".txt"):
                rutas.append(os.path.join(carpeta_actual, nombre_archivo))

    if len(rutas) != NUM_INSTANCIAS_ESPERADAS:
        problemas.append(
            f"Se esperaban {NUM_INSTANCIAS_ESPERADAS} instancias y se han encontrado {len(rutas)}"
        )

    for ruta in sorted(rutas):
        nombre_archivo = os.path.basename(ruta)
        try:
            instancia = cargar_instancia_solomon(ruta)
        except ErrorCargaSolomon as error:
            problemas.append(f"{nombre_archivo}: cabecera o contenido inválido ({error})")
            continue

        if len(instancia.clientes) != NUM_CLIENTES_ESPERADOS:
            problemas.append(
                f"{nombre_archivo}: tiene {len(instancia.clientes)} clientes, "
                f"se esperaban {NUM_CLIENTES_ESPERADOS}"
            )
            continue

        if instancia.capacidad_vehiculo <= 0:
            problemas.append(f"{nombre_archivo}: capacidad de vehículo inválida")
            continue

        # La clase deducida del nombre debe coincidir con la subcarpeta.
        clase_carpeta = os.path.basename(os.path.dirname(ruta)).upper()
        if instancia.clase != clase_carpeta:
            problemas.append(
                f"{nombre_archivo}: está en la carpeta {clase_carpeta} "
                f"pero su clase es {instancia.clase}"
            )
            continue

        correctas.append(ruta)

    return correctas, problemas


def descargar_mejores_conocidos(ruta_csv: str) -> int:
    """
    Descarga la tabla de mejores soluciones conocidas publicada por SINTEF y
    la guarda como CSV.

    Si la tabla no puede obtenerse o interpretarse, se crea el archivo con
    solo la cabecera: nunca se inventan valores.

    Args:
        ruta_csv: Ruta del archivo CSV a generar.

    Returns:
        Número de filas de datos escritas (0 si no se ha podido obtener).
    """
    os.makedirs(os.path.dirname(os.path.abspath(ruta_csv)), exist_ok=True)

    filas: list[dict] = []
    try:
        print(f"Descargando mejores soluciones conocidas desde {URL_PAGINA_MEJORES}")
        respuesta = requests.get(
            URL_PAGINA_MEJORES, headers=CABECERA_USER_AGENT, timeout=TIMEOUT_SEGUNDOS
        )
        if respuesta.status_code == 200:
            filas = _interpretar_tabla_mejores(respuesta.text)
        else:
            print(f"  SINTEF respondió con un error HTTP {respuesta.status_code}")
    except requests.exceptions.RequestException as error:
        print(f"  No se pudo conectar con SINTEF: {error}")

    with open(ruta_csv, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_MEJORES_CONOCIDOS)
        escritor.writeheader()
        escritor.writerows(filas)

    if filas:
        print(f"  Guardadas {len(filas)} mejores soluciones conocidas en {ruta_csv}")
    else:
        print(
            f"  No se han podido obtener las mejores soluciones conocidas. "
            f"Se ha creado {ruta_csv} solo con la cabecera, sin valores inventados."
        )

    return len(filas)


def _interpretar_tabla_mejores(html: str) -> list[dict]:
    """
    Extrae de la página de SINTEF las filas de la tabla de mejores
    soluciones conocidas.

    Cada fila tiene la forma: enlace con el nombre de la instancia, número
    de vehículos, distancia total y código de la referencia bibliográfica.

    Se admiten dos peculiaridades de la página real:
      - El rótulo del enlace puede llevar una letra final (p. ej. "r205b",
        "rc101b"), que SINTEF usa para señalar un valor corregido respecto
        al publicado originalmente.
      - La distancia puede llevar un asterisco (p. ej. "1096.73*") que
        remite a una nota al pie de la propia página.
    """
    patron_fila = re.compile(
        r"<a[^>]*>\s*([A-Za-z]+\d+)[A-Za-z]*\s*</a>\s*</td>\s*"
        r"<td[^>]*>\s*(\d+)\s*</td>\s*"
        r"<td[^>]*>\s*([\d.]+)\s*\*?\s*</td>\s*"
        r"<td[^>]*>\s*([^<]*?)\s*</td>",
        re.S,
    )

    filas: list[dict] = []
    vistas: set[str] = set()
    for bloque_fila in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        coincidencia = patron_fila.search(bloque_fila)
        if not coincidencia:
            continue

        nombre, vehiculos, distancia, referencia = coincidencia.groups()
        nombre = nombre.lower()

        # Solo interesan los nombres que corresponden a una instancia real.
        if clase_de_instancia(nombre) == "DESCONOCIDA" or nombre in vistas:
            continue
        vistas.add(nombre)

        filas.append(
            {
                "instancia": nombre,
                "num_vehiculos": int(vehiculos),
                "distancia_total": float(distancia),
                "fuente": f"SINTEF ({referencia})" if referencia else "SINTEF",
            }
        )

    return filas


def main() -> None:
    """Punto de entrada del script."""
    analizador = argparse.ArgumentParser(
        description=(
            "Descarga las 56 instancias de Solomon de 100 clientes desde SINTEF, "
            "las organiza por clase y verifica que están completas."
        )
    )
    analizador.add_argument(
        "--destino",
        default=None,
        help=f"Carpeta de destino (por defecto: {DIRECTORIO_INSTANCIAS})",
    )
    analizador.add_argument(
        "--solo-verificar",
        action="store_true",
        help="No descarga nada, solo verifica las instancias ya presentes",
    )
    argumentos = analizador.parse_args()

    raiz = _raiz_proyecto()
    directorio = argumentos.destino or os.path.join(raiz, DIRECTORIO_INSTANCIAS)

    if not argumentos.solo_verificar:
        try:
            descargar_instancias(directorio)
        except ErrorDescarga as error:
            print(f"\nERROR: {error}")
            print(
                "Fuentes alternativas: la página de Marius Solomon en Northeastern "
                "University, o los paquetes 'pyvrp' / 'vrplib'."
            )
            sys.exit(1)

        descargar_mejores_conocidos(os.path.join(raiz, RUTA_MEJORES_CONOCIDOS))

    print("\nVerificando instancias...")
    correctas, problemas = verificar_instancias(directorio)

    print(f"  Instancias correctas: {len(correctas)}/{NUM_INSTANCIAS_ESPERADAS}")
    if problemas:
        print(f"  Problemas detectados ({len(problemas)}):")
        for problema in problemas:
            print(f"    - {problema}")
        sys.exit(1)

    print("  Todas las instancias son correctas: 56 archivos, 100 clientes + depósito cada uno.")


if __name__ == "__main__":
    main()
