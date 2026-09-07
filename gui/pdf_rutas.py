"""
Generación de hojas de ruta en PDF para los conductores, mediante reportlab.

Cada hoja de ruta resume una única ruta: cabecera con fecha/vehículo/
conductor, tabla resumen, tabla parada a parada y, si procede, el listado
global de clientes sin asignar con su motivo de exclusión.
"""

import io
import os
from typing import BinaryIO, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from algoritmo.restricciones import HORA_INICIO_JORNADA_MIN
from datos.modelos import (
    ClienteNoAsignado,
    Nodo,
    Ruta,
    formatear_duracion_minutos,
    minutos_a_hhmm,
)

NOMBRE_APLICACION = "Polux"
NOTA_REGLAMENTO = (
    "Hoja de ruta generada conforme a las restricciones de conducción y descanso "
    "del Reglamento (CE) nº 561/2006."
)

_COLOR_CABECERA = colors.HexColor("#1a3c6e")
_COLOR_CABECERA_ALERTA = colors.HexColor("#8a1f1f")
#: Fondo de las filas de pausa obligatoria (ámbar suave, para que el
#: conductor las localice de un vistazo entre los clientes).
_COLOR_PAUSA = colors.HexColor("#fff2cc")
#: Fondo de la fila de regreso al depósito o fin de jornada.
_COLOR_REGRESO = colors.HexColor("#e8eef7")


def nombre_archivo_ruta(ruta: Ruta, fecha_texto: str) -> str:
    """Devuelve el nombre de archivo PDF correspondiente a una ruta."""
    return f"Ruta_{ruta.vehiculo.id}_{fecha_texto}.pdf"


def generar_hojas_de_ruta_pdf(
    depot: Nodo,
    rutas: list[Ruta],
    no_asignados: list[ClienteNoAsignado],
    carpeta_destino: str,
    fecha_texto: str,
    nombre_conductor: str = "",
    hora_inicio_jornada_min: int = HORA_INICIO_JORNADA_MIN,
) -> list[str]:
    """
    Genera un archivo PDF por cada ruta, con su hoja de ruta imprimible
    para el conductor, y devuelve la lista de archivos generados.

    Args:
        depot: Nodo del depósito.
        rutas: Rutas resultantes de la optimización.
        no_asignados: Clientes sin asignar (se listan en cada hoja de ruta).
        carpeta_destino: Carpeta donde se guardarán los archivos PDF.
        fecha_texto: Fecha del reparto, usada en la cabecera y el nombre de archivo.
        nombre_conductor: Nombre del conductor, opcional.
        hora_inicio_jornada_min: Hora de salida del depósito, en minutos desde medianoche.

    Returns:
        Lista de rutas de archivo (.pdf) generadas, una por ruta.
    """
    archivos_generados = []

    for ruta in rutas:
        ruta_archivo = os.path.join(carpeta_destino, nombre_archivo_ruta(ruta, fecha_texto))
        _generar_pdf_de_ruta(
            depot, ruta, no_asignados, ruta_archivo, nombre_conductor, fecha_texto, hora_inicio_jornada_min
        )
        archivos_generados.append(ruta_archivo)

    return archivos_generados


def generar_hoja_de_ruta_en_memoria(
    depot: Nodo,
    ruta: Ruta,
    no_asignados: list[ClienteNoAsignado],
    fecha_texto: str,
    nombre_conductor: str = "",
    hora_inicio_jornada_min: int = HORA_INICIO_JORNADA_MIN,
) -> bytes:
    """
    Genera la hoja de ruta de una única ruta en memoria, sin escribir en
    disco, y devuelve el PDF como bytes.

    Se usa para la previsualización en pantalla, de modo que el mismo código
    de maquetación sirve tanto para previsualizar como para exportar.

    Args:
        depot: Nodo del depósito.
        ruta: Ruta cuya hoja se quiere generar.
        no_asignados: Clientes sin asignar (se listan en la hoja de ruta).
        fecha_texto: Fecha del reparto, usada en la cabecera.
        nombre_conductor: Nombre del conductor, opcional.
        hora_inicio_jornada_min: Hora de salida del depósito, en minutos desde medianoche.

    Returns:
        El contenido del PDF como bytes.
    """
    buffer = io.BytesIO()
    _generar_pdf_de_ruta(
        depot, ruta, no_asignados, buffer, nombre_conductor, fecha_texto, hora_inicio_jornada_min
    )
    return buffer.getvalue()


def _texto_direccion(nodo: Nodo) -> str:
    """Dirección de texto del cliente si se conoce; si no, sus coordenadas."""
    if nodo.direccion_original:
        return nodo.direccion_original
    if nodo.tiene_coordenadas():
        return f"{nodo.lat:.5f}, {nodo.lon:.5f}"
    return "—"


def _generar_pdf_de_ruta(
    depot: Nodo,
    ruta: Ruta,
    no_asignados: list[ClienteNoAsignado],
    destino: Union[str, BinaryIO],
    nombre_conductor: str,
    fecha_texto: str,
    hora_inicio_jornada_min: int,
) -> None:
    """
    Construye y escribe la hoja de ruta de una ruta concreta.

    `destino` puede ser una ruta de archivo o un objeto binario en memoria
    (reportlab admite ambos), de forma que la maquetación se define una sola
    vez y sirve tanto para exportar a disco como para previsualizar.
    """
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "TituloPolux", parent=estilos["Title"], fontSize=24, textColor=_COLOR_CABECERA, spaceAfter=0
    )
    estilo_subtitulo = ParagraphStyle(
        "Subtitulo", parent=estilos["Normal"], fontSize=12, textColor=colors.HexColor("#555555"), spaceAfter=12
    )
    estilo_pie = ParagraphStyle("Pie", parent=estilos["Normal"], fontSize=8, textColor=colors.grey)
    estilo_celda = ParagraphStyle("Celda", parent=estilos["Normal"], fontSize=8, leading=10)

    elementos = [
        Paragraph(NOMBRE_APLICACION, estilo_titulo),
        Paragraph("Hoja de ruta para el conductor", estilo_subtitulo),
    ]

    tabla_cabecera = Table(
        [
            ["Fecha:", fecha_texto, "Ruta nº:", str(ruta.vehiculo.id)],
            [
                "Vehículo:",
                f"Vehículo {ruta.vehiculo.id} (capacidad {ruta.vehiculo.capacidad:g})",
                "Conductor:",
                nombre_conductor.strip() or "—",
            ],
            [
                "Salida:",
                minutos_a_hhmm(hora_inicio_jornada_min),
                "Límite regreso:",
                minutos_a_hhmm(depot.hora_fin) if ruta.incluye_regreso else "— (ruta abierta)",
            ],
            ["Depósito:", Paragraph(_texto_direccion(depot), estilo_celda), "", ""],
        ],
        # La tercera columna alberga rótulos largos como "Límite regreso:",
        # por lo que necesita algo más de ancho que la primera.
        colWidths=[2.2 * cm, 5.8 * cm, 2.9 * cm, 5.9 * cm],
    )
    _FILA_DEPOSITO = 3
    tabla_cabecera.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("SPAN", (1, _FILA_DEPOSITO), (3, _FILA_DEPOSITO)),
            ]
        )
    )
    elementos.append(tabla_cabecera)
    elementos.append(Spacer(1, 14))

    # El resumen se dispone en dos bloques de tres columnas (rótulo encima
    # del valor) en lugar de una única fila muy ancha: con seis métricas los
    # rótulos no caben en una sola línea sin solaparse.
    tabla_resumen = Table(
        [
            ["Paradas totales", "Distancia total", "Hora de salida"],
            [
                str(len(ruta.paradas)),
                f"{ruta.distancia_total_km:.2f} km",
                minutos_a_hhmm(hora_inicio_jornada_min),
            ],
            ["Tiempo de conducción", "Tiempo de espera", "Tiempo total estimado"],
            [
                formatear_duracion_minutos(ruta.tiempo_conduccion_min),
                formatear_duracion_minutos(ruta.tiempo_espera_min),
                formatear_duracion_minutos(ruta.tiempo_total_min),
            ],
        ],
        colWidths=[5.6 * cm] * 3,
    )
    tabla_resumen.setStyle(
        TableStyle(
            [
                # Filas 0 y 2 son rótulos; filas 1 y 3 son los valores.
                ("BACKGROUND", (0, 0), (-1, 0), _COLOR_CABECERA),
                ("BACKGROUND", (0, 2), (-1, 2), _COLOR_CABECERA),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("TEXTCOLOR", (0, 2), (-1, 2), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elementos.append(tabla_resumen)
    elementos.append(Spacer(1, 16))

    elementos.append(Paragraph("Paradas de la ruta", estilos["Heading3"]))

    filas_paradas = [["Nº", "Cliente", "Dirección", "Hora est. llegada", "Demanda", "T. servicio", "Observaciones"]]
    # Índices de fila que corresponden a pausas o al regreso, para poder
    # resaltarlas después con un estilo distinto al de los clientes.
    filas_pausa: list[int] = []
    filas_regreso: list[int] = []

    def _agregar_pausas_tras(indice_parada: int) -> None:
        """Intercala en la tabla las pausas que corresponden a este punto."""
        for pausa in ruta.pausas:
            if pausa.indice_parada_previa != indice_parada:
                continue
            filas_paradas.append(
                [
                    "—",
                    Paragraph("<b>PAUSA OBLIGATORIA</b>", estilo_celda),
                    Paragraph(
                        f"Durante el trayecto {pausa.origen} → {pausa.destino}", estilo_celda
                    ),
                    minutos_a_hhmm(pausa.instante_inicio),
                    "—",
                    f"{pausa.duracion_min} min",
                    Paragraph("Descanso Reg. 561/2006", estilo_celda),
                ]
            )
            filas_pausa.append(len(filas_paradas) - 1)

    # Pausas que caen antes de visitar al primer cliente.
    _agregar_pausas_tras(0)

    for orden, parada in enumerate(ruta.paradas, start=1):
        llegada_min = ruta.horarios_llegada[orden - 1] if orden - 1 < len(ruta.horarios_llegada) else None
        texto_llegada = minutos_a_hhmm(llegada_min) if llegada_min is not None else "N/D"
        filas_paradas.append(
            [
                str(orden),
                Paragraph(parada.nombre, estilo_celda),
                Paragraph(_texto_direccion(parada), estilo_celda),
                texto_llegada,
                f"{parada.demanda:g}",
                f"{parada.tiempo_servicio} min",
                "",
            ]
        )
        _agregar_pausas_tras(orden)

    # Última fila: regreso al depósito, o aviso de que la ruta es abierta.
    if ruta.incluye_regreso:
        instante_regreso = int(hora_inicio_jornada_min + ruta.tiempo_total_min)
        filas_paradas.append(
            [
                "—",
                Paragraph("<b>REGRESO AL DEPÓSITO</b>", estilo_celda),
                Paragraph(_texto_direccion(depot), estilo_celda),
                minutos_a_hhmm(instante_regreso),
                "—",
                "—",
                "",
            ]
        )
    else:
        filas_paradas.append(
            [
                "—",
                Paragraph("<b>FIN DE JORNADA</b>", estilo_celda),
                Paragraph(
                    "Ruta abierta: no se contempla el regreso al depósito", estilo_celda
                ),
                "—",
                "—",
                "—",
                "",
            ]
        )
    filas_regreso.append(len(filas_paradas) - 1)

    tabla_paradas = Table(
        filas_paradas,
        colWidths=[1 * cm, 3.2 * cm, 4.3 * cm, 2.6 * cm, 1.8 * cm, 2 * cm, 2.6 * cm],
        repeatRows=1,
    )
    estilo_tabla_paradas = [
        ("BACKGROUND", (0, 0), (-1, 0), _COLOR_CABECERA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]
    for indice_fila in filas_pausa:
        estilo_tabla_paradas.append(
            ("BACKGROUND", (0, indice_fila), (-1, indice_fila), _COLOR_PAUSA)
        )
    for indice_fila in filas_regreso:
        estilo_tabla_paradas.append(
            ("BACKGROUND", (0, indice_fila), (-1, indice_fila), _COLOR_REGRESO)
        )
    tabla_paradas.setStyle(TableStyle(estilo_tabla_paradas))
    elementos.append(tabla_paradas)

    if no_asignados:
        elementos.append(Spacer(1, 16))
        elementos.append(Paragraph("Clientes sin asignar (todas las rutas)", estilos["Heading3"]))
        filas_no_asignados = [["Cliente", "Motivo", "Detalle"]]
        for no_asignado in no_asignados:
            filas_no_asignados.append(
                [
                    Paragraph(no_asignado.nodo.nombre, estilo_celda),
                    no_asignado.motivo,
                    Paragraph(no_asignado.detalle, estilo_celda),
                ]
            )
        tabla_no_asignados = Table(filas_no_asignados, colWidths=[3.5 * cm, 3 * cm, 11 * cm])
        tabla_no_asignados.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _COLOR_CABECERA_ALERTA),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        elementos.append(tabla_no_asignados)

    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(f"Generado por {NOMBRE_APLICACION}", estilo_pie))
    elementos.append(Paragraph(NOTA_REGLAMENTO, estilo_pie))

    documento = SimpleDocTemplate(
        destino,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title=f"{NOMBRE_APLICACION} — Ruta {ruta.vehiculo.id}",
    )
    documento.build(elementos)
