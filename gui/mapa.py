"""
Generación del mapa interactivo con folium.

Construye un mapa HTML que muestra el depósito, las rutas resultantes de
la optimización (cada una en un color distinto) y los clientes que han
quedado sin asignar, resaltados en rojo con un icono de advertencia.
"""

import folium

from datos.modelos import ClienteNoAsignado, Nodo, Ruta, minutos_a_hhmm
from utils.osrm import ErrorEnrutamiento, obtener_geometria_ruta

#: Proveedor de las teselas (el fondo cartográfico) del mapa.
#:
#: **No** se usan los servidores de OpenStreetMap. Su política de uso los
#: reserva a openstreetmap.org y a su comunidad, y prohíbe que las
#: aplicaciones tiren de ellos, porque están mantenidos por voluntarios.
#: Hacerlo termina en un bloqueo con el mensaje "app is not following the
#: tile usage policy of OpenStreetMap's volunteer run servers".
#:
#: Tampoco sirve CARTO: sus mapas base pasaron a exigir clave de API y
#: devuelven las teselas con un "API KEY REQUIRED" sobreimpreso, aunque la
#: petición responda con un código 200.
#:
#: Se usan los mapas base de Esri (ArcGIS Online), accesibles sin clave y
#: sin necesidad de cabecera `Referer`, lo que importa porque el mapa se
#: abre como archivo local (`file://`). folium añade su atribución
#: automáticamente.
#:
#: Alternativa si se prefiere que las rutas destaquen más sobre un fondo
#: apagado, a costa de perder detalle de calles: "Esri.WorldGrayCanvas".
PROVEEDOR_TESELAS = "Esri.WorldStreetMap"

#: Paleta de colores utilizada para diferenciar cada ruta en el mapa
PALETA_COLORES_RUTAS = [
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "cadetblue",
    "darkgreen",
    "darkblue",
    "pink",
    "gray",
]


def generar_mapa(
    depot: Nodo,
    rutas: list[Ruta],
    no_asignados: list[ClienteNoAsignado],
    ruta_salida_html: str,
) -> tuple[str, list[str]]:
    """
    Genera el mapa interactivo con el depósito, las rutas optimizadas y los
    clientes sin asignar, y lo guarda como archivo HTML.

    Para cada ruta se intenta obtener la geometría real por carretera
    (mediante OSRM) para que la línea siga las calles en lugar de trazar
    un segmento recto. Si el servicio de rutas no está disponible para
    alguna ruta concreta, esa ruta se dibuja como línea recta entre sus
    paradas y se añade una advertencia al resultado.

    Args:
        depot: Nodo del depósito.
        rutas: Rutas resultantes de la optimización.
        no_asignados: Clientes que no pudieron incluirse en ninguna ruta.
        ruta_salida_html: Ruta del archivo HTML donde se guardará el mapa.

    Returns:
        Una tupla (ruta_html, advertencias) con la ruta del archivo HTML
        generado y las advertencias sobre geometrías que no pudieron
        obtenerse de OSRM.
    """
    advertencias: list[str] = []
    mapa = folium.Map(location=[depot.lat, depot.lon], zoom_start=12, tiles=PROVEEDOR_TESELAS)

    folium.Marker(
        location=[depot.lat, depot.lon],
        popup="<b>Depósito</b>",
        tooltip="Depósito",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(mapa)

    for indice_ruta, ruta in enumerate(rutas):
        color = PALETA_COLORES_RUTAS[indice_ruta % len(PALETA_COLORES_RUTAS)]
        # Si la ruta no contempla el regreso, no se dibuja el tramo de vuelta:
        # trazarlo daría a entender un recorrido que no está planificado.
        nodos_recorrido = [depot] + ruta.paradas
        if ruta.incluye_regreso:
            nodos_recorrido.append(depot)

        try:
            puntos_recorrido = obtener_geometria_ruta(nodos_recorrido)
        except ErrorEnrutamiento:
            puntos_recorrido = [(nodo.lat, nodo.lon) for nodo in nodos_recorrido]
            advertencias.append(
                f"No se pudo obtener la geometría real por carretera del vehículo "
                f"{ruta.vehiculo.id}; se muestra una línea recta como aproximación."
            )

        folium.PolyLine(
            puntos_recorrido,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=f"Vehículo {ruta.vehiculo.id}",
        ).add_to(mapa)

        for orden, parada in enumerate(ruta.paradas, start=1):
            llegada_min = (
                ruta.horarios_llegada[orden - 1] if orden - 1 < len(ruta.horarios_llegada) else None
            )
            texto_llegada = minutos_a_hhmm(llegada_min) if llegada_min is not None else "N/D"
            popup_html = (
                f"<b>{parada.nombre}</b><br>"
                f"Vehículo: {ruta.vehiculo.id}<br>"
                f"Orden de visita: {orden}<br>"
                f"Ventana: {parada.ventana_como_texto()}<br>"
                f"Llegada estimada: {texto_llegada}<br>"
                f"Demanda: {parada.demanda}<br>"
                f"Tiempo de servicio: {parada.tiempo_servicio} min"
            )
            folium.Marker(
                location=[parada.lat, parada.lon],
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=parada.nombre,
                icon=folium.Icon(color=color, icon="cube", prefix="fa"),
            ).add_to(mapa)

    for cliente_no_asignado in no_asignados:
        cliente = cliente_no_asignado.nodo
        if not cliente.tiene_coordenadas():
            # No hay marcador posible sin coordenadas (p. ej. dirección no
            # geocodificada); el cliente sigue apareciendo en el panel de
            # resultados y en las hojas de ruta.
            continue
        popup_html = (
            f"<b>{cliente.nombre}</b> (sin asignar)<br>"
            f"Motivo: {cliente_no_asignado.motivo}<br>"
            f"{cliente_no_asignado.detalle}<br>"
            f"Ventana: {cliente.ventana_como_texto()}<br>"
            f"Demanda: {cliente.demanda}"
        )
        folium.Marker(
            location=[cliente.lat, cliente.lon],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{cliente.nombre} (sin asignar)",
            icon=folium.Icon(color="red", icon="exclamation-triangle", prefix="fa"),
        ).add_to(mapa)

    mapa.save(ruta_salida_html)
    return ruta_salida_html, advertencias


def generar_mapa_vacio(depot: Nodo, clientes: list[Nodo], ruta_salida_html: str) -> str:
    """
    Genera un mapa inicial mostrando únicamente el depósito y los clientes
    cargados, antes de ejecutar la optimización.

    Args:
        depot: Nodo del depósito.
        clientes: Clientes cargados desde el CSV.
        ruta_salida_html: Ruta del archivo HTML donde se guardará el mapa.

    Returns:
        La ruta del archivo HTML generado.
    """
    mapa = folium.Map(location=[depot.lat, depot.lon], zoom_start=12, tiles=PROVEEDOR_TESELAS)

    folium.Marker(
        location=[depot.lat, depot.lon],
        popup="<b>Depósito</b>",
        tooltip="Depósito",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(mapa)

    for cliente in clientes:
        popup_html = (
            f"<b>{cliente.nombre}</b><br>"
            f"Ventana: {cliente.ventana_como_texto()}<br>"
            f"Demanda: {cliente.demanda}"
        )
        folium.Marker(
            location=[cliente.lat, cliente.lon],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=cliente.nombre,
            icon=folium.Icon(color="lightgray", icon="cube", prefix="fa"),
        ).add_to(mapa)

    mapa.save(ruta_salida_html)
    return ruta_salida_html
