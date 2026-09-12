"""
Punto de entrada de Polux.

Ejecuta este script para lanzar la interfaz gráfica de la aplicación:

    python main.py

Admite además un modo de autocomprobación, pensado para la integración
continua, que no abre ninguna ventana:

    python main.py --autocomprobacion
"""

import os
import sys
import traceback

#: Opción que activa la autocomprobación en lugar de abrir la ventana.
OPCION_AUTOCOMPROBACION = "--autocomprobacion"

#: Archivo donde se vuelca el error si la autocomprobación falla. Hace falta
#: porque el ejecutable se compila sin consola y la salida estándar se pierde
#: en Windows: sin este archivo solo quedaría el código de salida.
ARCHIVO_REGISTRO_AUTOCOMPROBACION = "polux_autocomprobacion.log"


def autocomprobacion() -> int:
    """
    Comprueba que la aplicación empaquetada es funcional, sin abrir ventana.

    Ejercita de verdad las dependencias que con más frecuencia se rompen al
    empaquetar, en lugar de limitarse a importarlas:

    * lee el CSV de ejemplo incluido en el paquete (pandas y la ruta de
      recursos empaquetados),
    * compone una hoja de ruta en PDF en memoria (las fuentes de reportlab),
    * construye un mapa de folium (sus plantillas y las de branca).

    No accede a la red, por lo que puede ejecutarse en un entorno aislado.

    Returns:
        0 si todo es correcto; 1 si algo falla, dejando el detalle en
        `polux_autocomprobacion.log`.
    """
    try:
        import tempfile

        import folium  # noqa: F401
        import tkinterweb  # noqa: F401
        import tkinterweb_tkhtml  # noqa: F401

        from algoritmo.optimizador import optimizar
        from datos.cargador import cargar_clientes_desde_csv
        from datos.modelos import Nodo
        from gui.mapa import generar_mapa_vacio
        from gui.pdf_rutas import generar_hoja_de_ruta_en_memoria
        from utils.osrm import MatrizDistancias
        from utils.rutas_app import esta_empaquetado, ruta_csv_ejemplo

        print(f"Empaquetado: {esta_empaquetado()}")

        # 1. Leer el CSV de ejemplo incluido en el paquete.
        ruta_csv = ruta_csv_ejemplo()
        if not os.path.isfile(ruta_csv):
            raise FileNotFoundError(f"No se encuentra el CSV de ejemplo: {ruta_csv}")
        clientes, _fallidos = cargar_clientes_desde_csv(ruta_csv)
        print(f"CSV de ejemplo leído: {len(clientes)} clientes")

        # 2. Optimizar con una matriz sintética, sin tocar la red.
        depot = Nodo(
            id=0,
            nombre="Depósito",
            lat=39.4699,
            lon=-0.3763,
            hora_inicio=8 * 60,
            hora_fin=18 * 60,
            es_depot=True,
        )
        seleccion = clientes[:3]
        matriz = MatrizDistancias()
        for origen in [depot] + seleccion:
            for destino in [depot] + seleccion:
                if origen.id != destino.id:
                    matriz.distancias_km[(origen.id, destino.id)] = 5.0
                    matriz.tiempos_min[(origen.id, destino.id)] = 10.0

        resultado = optimizar(
            depot=depot,
            clientes=seleccion,
            capacidad_vehiculo=1000,
            num_vehiculos=None,
            techo_diario_min=9 * 60,
            matriz=matriz,
            hora_inicio_jornada=8 * 60,
        )
        print(f"Optimización: {resultado.num_vehiculos_utilizados} ruta(s)")
        if not resultado.rutas:
            raise RuntimeError("La optimización no ha producido ninguna ruta")

        # 3. Componer una hoja de ruta en PDF (fuentes de reportlab).
        contenido_pdf = generar_hoja_de_ruta_en_memoria(
            depot=depot,
            ruta=resultado.rutas[0],
            no_asignados=[],
            fecha_texto="2026-01-01",
            nombre_conductor="Autocomprobación",
        )
        if not contenido_pdf.startswith(b"%PDF"):
            raise RuntimeError("El PDF generado no tiene una cabecera válida")
        print(f"PDF generado: {len(contenido_pdf)} bytes")

        # 4. Construir un mapa de folium (plantillas de folium y branca).
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_mapa = os.path.join(carpeta, "mapa.html")
            generar_mapa_vacio(depot, seleccion, ruta_mapa)
            tamano_mapa = os.path.getsize(ruta_mapa)
        print(f"Mapa generado: {tamano_mapa} bytes")

    except Exception:
        detalle = traceback.format_exc()
        print(detalle, file=sys.stderr)
        try:
            with open(ARCHIVO_REGISTRO_AUTOCOMPROBACION, "w", encoding="utf-8") as registro:
                registro.write(detalle)
        except OSError:
            pass
        return 1

    print("AUTOCOMPROBACIÓN CORRECTA")
    return 0


if __name__ == "__main__":
    if OPCION_AUTOCOMPROBACION in sys.argv:
        sys.exit(autocomprobacion())

    from gui.app import lanzar_aplicacion

    lanzar_aplicacion()
