"""
Ventana principal de la aplicación Polux.

Coordina el panel de configuración, el resumen pre-optimización, el mapa
interactivo y el panel de resultados, y orquesta la ejecución de las dos
fases del algoritmo de optimización (Clarke-Wright y 2-opt) respetando el
Reglamento (CE) nº 561/2006.
"""

import os
import tempfile
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from tkinterweb import HtmlFrame

from algoritmo.optimizador import optimizar
from algoritmo.restricciones import (
    alerta_proximidad_limite,
    generar_resumen_preoptimizacion,
    simular_ruta,
)
from datos.cargador import ID_DEPOT_RESERVADO, ErrorCargaDatos, cargar_clientes_desde_csv
from datos.modelos import ClienteNoAsignado, Nodo
from gui.dialogo_progreso import DialogoProgreso
from gui.mapa import generar_mapa, generar_mapa_vacio
from gui.panel_config import PanelConfiguracion
from gui.panel_resultados import PanelResultados
from gui.panel_resumen import PanelResumen
from utils.geocodificacion import ErrorGeocodificacion
from utils.osrm import ErrorEnrutamiento, obtener_matriz_distancias

TITULO_APLICACION = "Polux — Optimización de rutas de reparto"


class VentanaPrincipal(tk.Tk):
    """Ventana principal de la aplicación Polux."""

    def __init__(self):
        super().__init__()
        self.title(TITULO_APLICACION)
        self.geometry("1440x860")
        self.minsize(1100, 700)

        self._clientes: list[Nodo] = []
        self._no_asignados_carga: list[ClienteNoAsignado] = []
        self._ruta_csv_cargada: Optional[str] = None

        self._directorio_temporal = tempfile.mkdtemp(prefix="polux_")
        self._ruta_mapa_html = os.path.join(self._directorio_temporal, "mapa.html")

        self._construir_layout()
        self._mostrar_mapa_inicial()

    def _construir_layout(self) -> None:
        panel_dividido = ttk.PanedWindow(self, orient="horizontal")
        panel_dividido.pack(fill="both", expand=True)

        columna_izquierda = ttk.Frame(panel_dividido)
        self.panel_config = PanelConfiguracion(
            columna_izquierda,
            al_cargar_csv=self._al_cargar_csv,
            al_optimizar=self._al_optimizar,
            al_cambiar_config=self._al_cambiar_configuracion,
        )
        self.panel_config.pack(fill="x")
        ttk.Separator(columna_izquierda, orient="horizontal").pack(fill="x", pady=4)
        self.panel_resumen = PanelResumen(columna_izquierda)
        self.panel_resumen.pack(fill="both", expand=True)
        panel_dividido.add(columna_izquierda, weight=0)

        columna_central = ttk.Frame(panel_dividido)

        # El visor HTML embebido (Tkhtml 3) solo interpreta HTML y CSS
        # estáticos: no ejecuta JavaScript. Los mapas de folium se dibujan
        # íntegramente con Leaflet, que es JavaScript, así que el mapa
        # interactivo no puede renderizarse dentro de la ventana. Se ofrece
        # por tanto un botón que lo abre en el navegador del sistema, donde
        # sí funciona por completo.
        barra_mapa = ttk.Frame(columna_central, padding=(8, 8, 8, 4))
        barra_mapa.pack(fill="x")
        self.boton_abrir_mapa = ttk.Button(
            barra_mapa,
            text="Abrir mapa interactivo en el navegador",
            command=self._abrir_mapa_en_navegador,
        )
        self.boton_abrir_mapa.pack(fill="x")

        self.marco_mapa = HtmlFrame(columna_central, messages_enabled=False)
        self.marco_mapa.pack(fill="both", expand=True)
        panel_dividido.add(columna_central, weight=3)

        columna_derecha = ttk.Frame(panel_dividido)
        self.panel_resultados = PanelResultados(columna_derecha)
        self.panel_resultados.pack(fill="both", expand=True)
        panel_dividido.add(columna_derecha, weight=1)

    def _abrir_mapa_en_navegador(self) -> None:
        """
        Abre en el navegador del sistema el último mapa generado, donde sí
        se ejecuta el JavaScript de Leaflet y el mapa es interactivo.
        """
        if not os.path.isfile(self._ruta_mapa_html):
            messagebox.showinfo(
                "Mapa",
                "Todavía no se ha generado ningún mapa. Carga un archivo de "
                "clientes para verlos sobre el mapa.",
            )
            return

        webbrowser.open(f"file://{self._ruta_mapa_html}")

    def _mostrar_aviso_mapa(self) -> None:
        """
        Muestra en el panel central un aviso estático explicando que el mapa
        interactivo se abre en el navegador.

        Se dibuja con HTML y CSS sencillos porque es justo lo que el visor
        embebido sabe interpretar.
        """
        aviso = """
        <html><body style="font-family: sans-serif; background: #f4f6f9;
                           color: #33404f; margin: 0; padding: 36px 28px;">
          <h2 style="color: #1a3c6e; margin: 0 0 12px 0;">Mapa de rutas</h2>
          <p style="line-height: 1.5; max-width: 46em;">
            El visor integrado en la ventana no ejecuta JavaScript, y los mapas
            se dibujan con Leaflet, que lo necesita. Por eso el mapa
            interactivo se abre en el <b>navegador del sistema</b>.
          </p>
          <p style="line-height: 1.5; max-width: 46em;">
            Pulsa <b>&laquo;Abrir mapa interactivo en el navegador&raquo;</b>,
            arriba, para verlo: incluye el dep&oacute;sito, cada ruta en un
            color distinto siguiendo las calles, y los clientes sin asignar
            marcados en rojo. Al pulsar sobre un marcador se muestran sus
            datos.
          </p>
          <p style="line-height: 1.5; max-width: 46em; color: #6b7684;">
            Tambi&eacute;n puedes guardarlo como archivo HTML independiente
            con <i>Exportar mapa (HTML)</i>, en el panel de resultados.
          </p>
        </body></html>
        """
        self.marco_mapa.load_html(aviso)

    def _obtener_depot(self) -> Optional[Nodo]:
        """Construye el nodo del depósito a partir de la configuración actual."""
        try:
            configuracion = self.panel_config.obtener_configuracion()
        except ValueError:
            messagebox.showerror(
                "Configuración inválida", "Revisa los campos numéricos de configuración."
            )
            return None

        # El depósito se modela como un nodo con su propia ventana de tiempo:
        # abre a la hora de salida y cierra a la hora límite de regreso. La
        # comprobación de cierre se aplica a la visita de vuelta.
        return Nodo(
            id=ID_DEPOT_RESERVADO,
            nombre="Depósito",
            lat=configuracion["depot_lat"],
            lon=configuracion["depot_lon"],
            hora_inicio=configuracion["hora_salida_min"],
            hora_fin=configuracion["hora_limite_regreso_min"],
            direccion_original=configuracion["depot_direccion"] or None,
            es_depot=True,
        )

    def _mostrar_mapa_inicial(self) -> None:
        depot = self._obtener_depot()
        if depot is None:
            return
        generar_mapa_vacio(depot, self._clientes, self._ruta_mapa_html)
        self._mostrar_aviso_mapa()

    def _al_cargar_csv(self, ruta_csv: str) -> None:
        """Carga los clientes desde el CSV seleccionado y refresca la vista."""
        dialogo: Optional[DialogoProgreso] = None

        def callback_progreso(indice: int, total: int, texto: str) -> None:
            nonlocal dialogo
            if dialogo is None:
                dialogo = DialogoProgreso(self, "Geocodificando direcciones", texto)
            dialogo.actualizar(indice, total, f"Geocodificando dirección {indice}/{total}:\n{texto}")

        try:
            clientes, fallidos_geocodificacion = cargar_clientes_desde_csv(
                ruta_csv, callback_progreso=callback_progreso
            )
        except (ErrorCargaDatos, ErrorGeocodificacion) as error:
            messagebox.showerror("Error al cargar clientes", str(error))
            return
        finally:
            if dialogo is not None:
                dialogo.cerrar()

        self._clientes = clientes
        self._no_asignados_carga = fallidos_geocodificacion
        self._ruta_csv_cargada = ruta_csv
        self.panel_config.mostrar_archivo_cargado(ruta_csv, len(clientes))
        self.panel_config.habilitar_boton_optimizar(len(clientes) > 0)
        self.panel_resultados.actualizar(self._obtener_depot(), [], self._no_asignados_carga, [])
        self._mostrar_mapa_inicial()
        self._al_cambiar_configuracion()

        if fallidos_geocodificacion:
            messagebox.showwarning(
                "Direcciones no encontradas",
                f"{len(fallidos_geocodificacion)} cliente(s) no se pudieron geocodificar y "
                "aparecen como sin asignar (motivo GEOCODIFICACIÓN) en el panel de resultados.",
            )

    def _al_cambiar_configuracion(self) -> None:
        """Recalcula y refresca el resumen pre-optimización en vivo."""
        if not self._clientes:
            self.panel_resumen.actualizar(None)
            return

        try:
            configuracion = self.panel_config.obtener_configuracion()
        except ValueError:
            self.panel_resumen.actualizar(None)
            return

        depot = self._obtener_depot()
        if depot is None:
            return

        resumen = generar_resumen_preoptimizacion(
            depot=depot,
            clientes=self._clientes,
            horas_semana_conducidas=configuracion["horas_semana"],
            permitir_extendido=configuracion["permitir_extendido"],
            num_vehiculos=configuracion["num_vehiculos"],
            hora_inicio_jornada=configuracion["hora_salida_min"],
            hora_limite_regreso=configuracion["hora_limite_regreso_min"],
        )
        self.panel_resumen.actualizar(resumen)

    def _al_optimizar(self) -> None:
        """Ejecuta las dos fases del algoritmo y muestra los resultados."""
        if not self._clientes:
            messagebox.showwarning(
                "Optimizar rutas", "Primero debes cargar un archivo de clientes."
            )
            return

        try:
            configuracion = self.panel_config.obtener_configuracion()
        except ValueError as error:
            messagebox.showerror("Configuración inválida", str(error))
            return

        depot = self._obtener_depot()
        if depot is None:
            return

        resumen = generar_resumen_preoptimizacion(
            depot=depot,
            clientes=self._clientes,
            horas_semana_conducidas=configuracion["horas_semana"],
            permitir_extendido=configuracion["permitir_extendido"],
            num_vehiculos=configuracion["num_vehiculos"],
            hora_inicio_jornada=configuracion["hora_salida_min"],
            hora_limite_regreso=configuracion["hora_limite_regreso_min"],
        )
        self.panel_resumen.actualizar(resumen)

        if resumen.bloqueado:
            messagebox.showerror(
                "Optimización bloqueada",
                "No quedan horas de conducción disponibles esta semana (techo diario <= 0). "
                "No es posible ejecutar la optimización.",
            )
            return

        try:
            self.config(cursor="watch")
            self.update_idletasks()
            matriz = obtener_matriz_distancias([depot] + self._clientes)
        except ErrorEnrutamiento as error:
            messagebox.showerror(
                "Error al calcular distancias por carretera",
                f"No se pudo obtener la matriz de distancias reales (OSRM):\n\n{error}",
            )
            return
        finally:
            self.config(cursor="")

        hora_salida = configuracion["hora_salida_min"]

        # Las tres fases del algoritmo se ejecutan a través del punto de
        # entrada común, el mismo que utilizan los scripts de evaluación.
        resultado_optimizacion = optimizar(
            depot=depot,
            clientes=self._clientes,
            capacidad_vehiculo=configuracion["capacidad_vehiculo"],
            num_vehiculos=configuracion["num_vehiculos"],
            techo_diario_min=resumen.techo_diario_min,
            matriz=matriz,
            hora_inicio_jornada=hora_salida,
            incluir_regreso=configuracion["incluir_regreso"],
        )
        rutas = resultado_optimizacion.rutas
        no_asignados = resultado_optimizacion.no_asignados
        recuperados = resultado_optimizacion.recuperados

        advertencias = []
        if configuracion["flota_ilimitada"]:
            advertencias.append(
                "Modo evaluación con flota ilimitada: el número de vehículos no está acotado."
            )
        if not configuracion["incluir_regreso"]:
            advertencias.append(
                "Rutas abiertas: no se cuenta el regreso al depósito, así que la jornada "
                "termina en el último cliente."
            )

        for ruta in rutas:
            resultado_simulacion = simular_ruta(
                depot,
                ruta.paradas,
                configuracion["capacidad_vehiculo"],
                resumen.techo_diario_min,
                matriz,
                hora_salida,
                incluir_regreso=configuracion["incluir_regreso"],
            )
            alerta = alerta_proximidad_limite(resultado_simulacion, resumen.techo_diario_min)
            if alerta:
                advertencias.append(f"Vehículo {ruta.vehiculo.id}: {alerta}")

        no_asignados_totales = no_asignados + self._no_asignados_carga

        _ruta_mapa_html, advertencias_geometria = generar_mapa(
            depot, rutas, no_asignados_totales, self._ruta_mapa_html
        )
        advertencias.extend(advertencias_geometria)
        self._mostrar_aviso_mapa()

        self.panel_resultados.actualizar(
            depot,
            rutas,
            no_asignados_totales,
            advertencias,
            configuracion["nombre_conductor"],
            hora_salida,
            len(recuperados),
        )


def lanzar_aplicacion() -> None:
    """Punto de entrada para lanzar la interfaz gráfica de Polux."""
    aplicacion = VentanaPrincipal()
    aplicacion.mainloop()
