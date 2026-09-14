"""
Panel de resultados de la optimización.

Muestra la distancia total, el número de rutas utilizadas, el desglose de
cada ruta (secuencia de paradas, distancia, tiempo total y tiempo de
conducción), la lista de clientes sin asignar con su motivo, y permite
exportar los resultados a CSV y el mapa a un archivo HTML independiente.
"""

import csv
import tkinter as tk
import webbrowser
from datetime import date
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from algoritmo.restricciones import HORA_INICIO_JORNADA_MIN
from datos.modelos import ClienteNoAsignado, Nodo, Ruta, formatear_duracion_minutos, minutos_a_hhmm
from gui.dialogo_previsualizacion import DialogoPrevisualizacion
from gui.mapa import generar_mapa
from utils.google_maps import generar_enlace_google_maps
from utils.rutas_app import directorio_datos_usuario


class PanelResultados(ttk.Frame):
    """Panel con el desglose de resultados de la optimización y sus exportaciones."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=10)

        self._depot: Optional[Nodo] = None
        self._rutas: list[Ruta] = []
        self._no_asignados: list[ClienteNoAsignado] = []
        self._nombre_conductor: str = ""
        self._hora_inicio_jornada_min: int = HORA_INICIO_JORNADA_MIN

        self._construir_widgets()

    def _construir_widgets(self) -> None:
        ttk.Label(self, text="Resultados", font=("TkDefaultFont", 12, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        fila_totales = ttk.Frame(self)
        fila_totales.pack(fill="x", pady=(0, 10))
        self.var_distancia_total = tk.StringVar(value="—")
        self.var_num_rutas = tk.StringVar(value="—")
        ttk.Label(fila_totales, text="Distancia total:").grid(row=0, column=0, sticky="w")
        ttk.Label(
            fila_totales, textvariable=self.var_distancia_total, font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=1, sticky="w", padx=(4, 20))
        ttk.Label(fila_totales, text="Vehículos utilizados:").grid(row=0, column=2, sticky="w")
        ttk.Label(
            fila_totales, textvariable=self.var_num_rutas, font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=3, sticky="w", padx=(4, 0))

        self.var_espera_total = tk.StringVar(value="—")
        ttk.Label(fila_totales, text="Tiempo de espera total:").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Label(
            fila_totales, textvariable=self.var_espera_total, font=("TkDefaultFont", 10, "bold")
        ).grid(row=1, column=1, sticky="w", padx=(4, 20), pady=(4, 0))

        self.var_recuperados = tk.StringVar(value="—")
        ttk.Label(fila_totales, text="Reinserción:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            fila_totales, textvariable=self.var_recuperados, foreground="#1a6e2e"
        ).grid(row=2, column=1, columnspan=3, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(self, text="Rutas", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.tabla_rutas = ttk.Treeview(
            self,
            columns=(
                "paradas",
                "distancia",
                "tiempo_total",
                "tiempo_conduccion",
                "tiempo_espera",
                "pausas",
            ),
            show="headings",
            height=6,
        )
        for columna, titulo in [
            ("paradas", "Nº paradas"),
            ("distancia", "Distancia (km)"),
            ("tiempo_total", "Tiempo total"),
            ("tiempo_conduccion", "Tiempo conducción"),
            ("tiempo_espera", "Tiempo espera"),
            ("pausas", "Pausas 45'"),
        ]:
            self.tabla_rutas.heading(columna, text=titulo)
            self.tabla_rutas.column(columna, width=95, anchor="center")
        self.tabla_rutas.pack(fill="x", pady=(2, 8))
        self.tabla_rutas.bind("<<TreeviewSelect>>", self._mostrar_detalle_ruta_seleccionada)

        ttk.Label(self, text="Secuencia de la ruta seleccionada", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )
        # `width=1`: sin esto el `Text` pide 80 caracteres (unos 590 px) y
        # fuerza el ancho de toda la columna de resultados. Se estira solo
        # con el `fill="x"` del empaquetado.
        self.texto_detalle_ruta = tk.Text(self, height=6, width=1, wrap="word", state="disabled")
        self.texto_detalle_ruta.pack(fill="both", expand=False, pady=(2, 10))

        ttk.Label(self, text="Clientes sin asignar", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )
        self.tabla_no_asignados = ttk.Treeview(
            self, columns=("cliente", "motivo", "detalle"), show="headings", height=5
        )
        for columna, titulo, ancho in [
            ("cliente", "Cliente", 120),
            ("motivo", "Motivo", 90),
            ("detalle", "Detalle", 260),
        ]:
            self.tabla_no_asignados.heading(columna, text=titulo)
            self.tabla_no_asignados.column(columna, width=ancho, anchor="w")
        self.tabla_no_asignados.pack(fill="both", expand=True, pady=(2, 8))

        ttk.Label(self, text="Advertencias del Reglamento 561/2006", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )
        self.texto_advertencias = tk.Text(
            self, height=4, width=1, wrap="word", state="disabled", background="#fff8e1"
        )
        self.texto_advertencias.pack(fill="both", expand=False, pady=(2, 10))

        ttk.Label(self, text="Para el conductor", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )
        self.marco_google_maps = ttk.Frame(self)
        self.marco_google_maps.pack(fill="x", pady=(2, 6))

        ttk.Button(
            self, text="Hojas de ruta (PDF)...", command=self._previsualizar_pdf
        ).pack(fill="x", pady=(0, 10))

        fila_exportar = ttk.Frame(self)
        fila_exportar.pack(fill="x", pady=(4, 0))
        ttk.Button(
            fila_exportar, text="Exportar resultados (CSV)", command=self._exportar_csv
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(
            fila_exportar, text="Exportar mapa (HTML)", command=self._exportar_mapa
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def actualizar(
        self,
        depot: Nodo,
        rutas: list[Ruta],
        no_asignados: list[ClienteNoAsignado],
        advertencias_regulacion: list[str],
        nombre_conductor: str = "",
        hora_inicio_jornada_min: int = HORA_INICIO_JORNADA_MIN,
        clientes_recuperados: int = 0,
    ) -> None:
        """Refresca el panel con los resultados de una nueva optimización."""
        self._depot = depot
        self._rutas = rutas
        self._no_asignados = no_asignados
        self._nombre_conductor = nombre_conductor
        self._hora_inicio_jornada_min = hora_inicio_jornada_min

        distancia_total = sum(ruta.distancia_total_km for ruta in rutas)
        self.var_distancia_total.set(f"{distancia_total:.2f} km")
        self.var_num_rutas.set(str(len(rutas)))

        espera_total = sum(ruta.tiempo_espera_min for ruta in rutas)
        self.var_espera_total.set(
            formatear_duracion_minutos(espera_total) if rutas else "—"
        )
        self.var_recuperados.set(
            f"{clientes_recuperados} cliente(s) recuperado(s) tras la mejora local"
            if clientes_recuperados
            else "—"
        )

        self.tabla_rutas.delete(*self.tabla_rutas.get_children())
        for indice, ruta in enumerate(rutas):
            self.tabla_rutas.insert(
                "",
                "end",
                iid=str(indice),
                text=f"Vehículo {ruta.vehiculo.id}",
                values=(
                    len(ruta.paradas),
                    f"{ruta.distancia_total_km:.2f}",
                    formatear_duracion_minutos(ruta.tiempo_total_min),
                    formatear_duracion_minutos(ruta.tiempo_conduccion_min),
                    formatear_duracion_minutos(ruta.tiempo_espera_min),
                    ruta.numero_pausas,
                ),
            )
        self._limpiar_detalle_ruta()

        self.tabla_no_asignados.delete(*self.tabla_no_asignados.get_children())
        for no_asignado in no_asignados:
            self.tabla_no_asignados.insert(
                "",
                "end",
                values=(no_asignado.nodo.nombre, no_asignado.motivo, no_asignado.detalle),
            )

        self._actualizar_texto(self.texto_advertencias, advertencias_regulacion)
        self._reconstruir_botones_google_maps()

    def _reconstruir_botones_google_maps(self) -> None:
        """Recrea un botón 'Abrir Ruta N en Google Maps' por cada ruta actual."""
        for widget in self.marco_google_maps.winfo_children():
            widget.destroy()

        if not self._rutas:
            ttk.Label(self.marco_google_maps, text="—", foreground="gray").pack(anchor="w")
            return

        for ruta in self._rutas:
            ttk.Button(
                self.marco_google_maps,
                text=f"Abrir Ruta {ruta.vehiculo.id} en Google Maps",
                command=lambda ruta=ruta: self._abrir_en_google_maps(ruta),
            ).pack(fill="x", pady=2)

    def _abrir_en_google_maps(self, ruta: Ruta) -> None:
        if self._depot is None or not ruta.paradas:
            return

        enlace = generar_enlace_google_maps(
            self._depot, ruta.paradas, incluir_regreso=ruta.incluye_regreso
        )

        self.clipboard_clear()
        self.clipboard_append(enlace)

        webbrowser.open(enlace)

    def _mostrar_detalle_ruta_seleccionada(self, _evento) -> None:
        seleccion = self.tabla_rutas.selection()
        if not seleccion:
            return
        indice = int(seleccion[0])
        ruta = self._rutas[indice]

        lineas = [f"Vehículo {ruta.vehiculo.id} — {len(ruta.paradas)} paradas"]
        for orden, parada in enumerate(ruta.paradas, start=1):
            llegada = ruta.horarios_llegada[orden - 1] if orden - 1 < len(ruta.horarios_llegada) else None
            texto_llegada = minutos_a_hhmm(llegada) if llegada is not None else "N/D"
            lineas.append(
                f"  {orden}. {parada.nombre} — llegada {texto_llegada} — "
                f"ventana {parada.ventana_como_texto()} — demanda {parada.demanda}"
            )
        self._actualizar_texto(self.texto_detalle_ruta, lineas)

    def _limpiar_detalle_ruta(self) -> None:
        self._actualizar_texto(self.texto_detalle_ruta, [])

    @staticmethod
    def _actualizar_texto(widget_texto: tk.Text, lineas: list[str]) -> None:
        widget_texto.config(state="normal")
        widget_texto.delete("1.0", "end")
        widget_texto.insert("1.0", "\n".join(lineas) if lineas else "—")
        widget_texto.config(state="disabled")

    def _exportar_csv(self) -> None:
        if not self._rutas and not self._no_asignados:
            messagebox.showinfo("Exportar resultados", "No hay resultados para exportar todavía.")
            return

        ruta_destino = filedialog.asksaveasfilename(
            title="Exportar resultados a CSV",
            initialdir=directorio_datos_usuario(),
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv")],
        )
        if not ruta_destino:
            return

        with open(ruta_destino, "w", newline="", encoding="utf-8") as archivo_csv:
            escritor = csv.writer(archivo_csv)
            escritor.writerow(
                [
                    "tipo",
                    "vehiculo",
                    "orden",
                    "cliente",
                    "lat",
                    "lon",
                    "llegada_estimada",
                    "demanda",
                    "distancia_total_km",
                    "tiempo_total_min",
                    "tiempo_conduccion_min",
                    "tiempo_espera_min",
                    "numero_pausas",
                    "motivo",
                    "detalle",
                ]
            )
            for ruta in self._rutas:
                for orden, parada in enumerate(ruta.paradas, start=1):
                    llegada = (
                        ruta.horarios_llegada[orden - 1]
                        if orden - 1 < len(ruta.horarios_llegada)
                        else None
                    )
                    escritor.writerow(
                        [
                            "RUTA",
                            ruta.vehiculo.id,
                            orden,
                            parada.nombre,
                            parada.lat,
                            parada.lon,
                            minutos_a_hhmm(llegada) if llegada is not None else "",
                            parada.demanda,
                            f"{ruta.distancia_total_km:.2f}",
                            f"{ruta.tiempo_total_min:.0f}",
                            f"{ruta.tiempo_conduccion_min:.0f}",
                            f"{ruta.tiempo_espera_min:.0f}",
                            ruta.numero_pausas,
                            "",
                            "",
                        ]
                    )
            for no_asignado in self._no_asignados:
                escritor.writerow(
                    [
                        "SIN_ASIGNAR",
                        "",
                        "",
                        no_asignado.nodo.nombre,
                        no_asignado.nodo.lat if no_asignado.nodo.lat is not None else "",
                        no_asignado.nodo.lon if no_asignado.nodo.lon is not None else "",
                        "",
                        no_asignado.nodo.demanda,
                        # distancia, tiempo total, conducción, espera y pausas
                        # no aplican a un cliente que no está en ninguna ruta.
                        "",
                        "",
                        "",
                        "",
                        "",
                        no_asignado.motivo,
                        no_asignado.detalle,
                    ]
                )

        messagebox.showinfo("Exportar resultados", f"Resultados exportados en:\n{ruta_destino}")

    def _exportar_mapa(self) -> None:
        if self._depot is None:
            messagebox.showinfo("Exportar mapa", "No hay ningún mapa generado todavía.")
            return

        ruta_destino = filedialog.asksaveasfilename(
            title="Exportar mapa a HTML",
            initialdir=directorio_datos_usuario(),
            defaultextension=".html",
            filetypes=[("Archivos HTML", "*.html")],
        )
        if not ruta_destino:
            return

        _ruta_html, advertencias_geometria = generar_mapa(
            self._depot, self._rutas, self._no_asignados, ruta_destino
        )
        mensaje = f"Mapa exportado en:\n{ruta_destino}"
        if advertencias_geometria:
            mensaje += "\n\n" + "\n".join(advertencias_geometria)
        messagebox.showinfo("Exportar mapa", mensaje)

    def _previsualizar_pdf(self) -> None:
        """
        Abre la previsualización de las hojas de ruta. El guardado y la
        impresión se realizan desde dentro del propio diálogo.
        """
        if self._depot is None or not self._rutas:
            messagebox.showinfo(
                "Hojas de ruta", "No hay rutas optimizadas todavía para previsualizar."
            )
            return

        DialogoPrevisualizacion(
            self,
            depot=self._depot,
            rutas=self._rutas,
            no_asignados=self._no_asignados,
            fecha_texto=date.today().isoformat(),
            nombre_conductor=self._nombre_conductor,
            hora_inicio_jornada_min=self._hora_inicio_jornada_min,
        )
