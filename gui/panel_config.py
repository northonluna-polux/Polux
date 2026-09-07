"""
Panel izquierdo de configuración de la aplicación Polux.

Permite introducir la dirección del depósito (geocodificada mediante
Nominatim), la flota disponible, las horas ya conducidas esta semana, el
nombre del conductor y cargar el archivo CSV de clientes, además de lanzar
la optimización de rutas.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from algoritmo.restricciones import HORA_INICIO_JORNADA_MIN, HORA_LIMITE_REGRESO_MIN
from datos.modelos import hhmm_a_minutos, minutos_a_hhmm
from utils.geocodificacion import ErrorGeocodificacion, geocodificar_direccion
from utils.rutas_app import directorio_inicial_para_csv

#: Dirección de depósito por defecto, con coordenadas ya conocidas para
#: que la aplicación funcione sin depender de la red nada más arrancar.
DIRECCION_DEPOT_POR_DEFECTO = "Plaça de l'Ajuntament, València, España"
LAT_DEPOT_POR_DEFECTO = 39.4699
LON_DEPOT_POR_DEFECTO = -0.3763


class PanelConfiguracion(ttk.Frame):
    """Panel con los controles de configuración y las acciones principales."""

    def __init__(
        self,
        parent: tk.Widget,
        al_cargar_csv: Callable[[str], None],
        al_optimizar: Callable[[], None],
        al_cambiar_config: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent, padding=10)
        self._al_cargar_csv = al_cargar_csv
        self._al_optimizar = al_optimizar
        self._al_cambiar_config = al_cambiar_config

        self._depot_lat: Optional[float] = LAT_DEPOT_POR_DEFECTO
        self._depot_lon: Optional[float] = LON_DEPOT_POR_DEFECTO

        self.var_depot_direccion = tk.StringVar(value=DIRECCION_DEPOT_POR_DEFECTO)
        self.var_depot_coords_texto = tk.StringVar(
            value=f"Coordenadas: {LAT_DEPOT_POR_DEFECTO:.4f}, {LON_DEPOT_POR_DEFECTO:.4f}"
        )
        self.var_num_vehiculos = tk.IntVar(value=3)
        self.var_capacidad_vehiculo = tk.DoubleVar(value=100.0)
        self.var_horas_semana = tk.DoubleVar(value=0.0)
        self.var_permitir_extendido = tk.BooleanVar(value=False)
        self.var_hora_salida = tk.StringVar(value=minutos_a_hhmm(HORA_INICIO_JORNADA_MIN))
        self.var_hora_limite_regreso = tk.StringVar(
            value=minutos_a_hhmm(HORA_LIMITE_REGRESO_MIN)
        )
        self.var_flota_ilimitada = tk.BooleanVar(value=False)
        self.var_incluir_regreso = tk.BooleanVar(value=True)
        self.var_nombre_conductor = tk.StringVar(value="")

        self._construir_widgets()

        self.var_horas_semana.trace_add("write", self._notificar_cambio_config)
        self.var_permitir_extendido.trace_add("write", self._notificar_cambio_config)
        self.var_hora_salida.trace_add("write", self._notificar_cambio_config)

    def _construir_widgets(self) -> None:
        ttk.Label(self, text="Configuración", font=("TkDefaultFont", 13, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        ttk.Label(self, text="Dirección del depósito").pack(anchor="w")
        fila_depot = ttk.Frame(self)
        fila_depot.pack(fill="x", pady=(2, 2))
        ttk.Entry(fila_depot, textvariable=self.var_depot_direccion).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        ttk.Button(fila_depot, text="Buscar", command=self._geocodificar_depot).pack(side="left")

        ttk.Label(
            self, textvariable=self.var_depot_coords_texto, foreground="gray", font=("TkDefaultFont", 8)
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self, text="Número de vehículos").pack(anchor="w")
        self._campo_num_vehiculos = ttk.Spinbox(
            self, from_=1, to=50, textvariable=self.var_num_vehiculos, width=10
        )
        self._campo_num_vehiculos.pack(fill="x", pady=(2, 4))

        ttk.Checkbutton(
            self,
            text="Flota ilimitada (modo evaluación)",
            variable=self.var_flota_ilimitada,
            command=self._al_cambiar_flota_ilimitada,
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self, text="Capacidad por vehículo").pack(anchor="w")
        ttk.Spinbox(
            self, from_=1, to=1_000_000, textvariable=self.var_capacidad_vehiculo, width=10
        ).pack(fill="x", pady=(2, 10))

        fila_horario = ttk.Frame(self)
        fila_horario.pack(fill="x", pady=(0, 10))
        ttk.Label(fila_horario, text="Hora de salida (HH:MM)").grid(row=0, column=0, sticky="w")
        ttk.Label(fila_horario, text="Hora límite de regreso").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Entry(fila_horario, textvariable=self.var_hora_salida, width=10).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Entry(fila_horario, textvariable=self.var_hora_limite_regreso, width=10).grid(
            row=1, column=1, sticky="w", padx=(10, 0), pady=(2, 0)
        )

        ttk.Label(self, text="Horas ya conducidas esta semana").pack(anchor="w")
        ttk.Spinbox(
            self,
            from_=0,
            to=56,
            increment=0.5,
            textvariable=self.var_horas_semana,
            width=10,
        ).pack(fill="x", pady=(2, 10))

        ttk.Checkbutton(
            self,
            text="Permitir jornada extendida (10 h, máx. 2 veces/semana)",
            variable=self.var_permitir_extendido,
        ).pack(anchor="w", pady=(0, 4))

        ttk.Checkbutton(
            self,
            text="Contar el regreso al depósito",
            variable=self.var_incluir_regreso,
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self, text="Nombre del conductor (opcional)").pack(anchor="w")
        ttk.Entry(self, textvariable=self.var_nombre_conductor).pack(fill="x", pady=(2, 14))

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(0, 14))

        ttk.Button(self, text="Cargar clientes (CSV)...", command=self._cargar_csv).pack(
            fill="x", pady=(0, 6)
        )

        self.etiqueta_csv = ttk.Label(self, text="Ningún archivo cargado", foreground="gray")
        self.etiqueta_csv.pack(anchor="w", pady=(0, 14))

        self.boton_optimizar = ttk.Button(
            self, text="Optimizar rutas", command=self._al_optimizar, state="disabled"
        )
        self.boton_optimizar.pack(fill="x")

    def _al_cambiar_flota_ilimitada(self) -> None:
        """
        Desactiva el campo de número de vehículos cuando la flota es
        ilimitada, ya que en ese modo no se tiene en cuenta.
        """
        flota_ilimitada = bool(self.var_flota_ilimitada.get())
        self._campo_num_vehiculos.config(state="disabled" if flota_ilimitada else "normal")
        self._notificar_cambio_config()

    def _geocodificar_depot(self) -> None:
        direccion = self.var_depot_direccion.get().strip()
        if not direccion:
            messagebox.showerror("Dirección del depósito", "Introduce una dirección para buscar.")
            return

        try:
            resultado = geocodificar_direccion(direccion)
        except ErrorGeocodificacion as error:
            messagebox.showerror("Error de geocodificación", str(error))
            return

        if resultado is None:
            self._depot_lat = None
            self._depot_lon = None
            self.var_depot_coords_texto.set("Dirección no encontrada. Intenta ser más específico.")
            return

        self._depot_lat, self._depot_lon = resultado
        self.var_depot_coords_texto.set(f"Coordenadas: {self._depot_lat:.4f}, {self._depot_lon:.4f}")
        self._notificar_cambio_config()

    def _cargar_csv(self) -> None:
        ruta_csv = filedialog.askopenfilename(
            title="Seleccionar archivo de clientes",
            # Se abre en la carpeta de los datos de ejemplo para que el
            # archivo de prueba esté a la vista sin tener que buscarlo.
            initialdir=directorio_inicial_para_csv(),
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if ruta_csv:
            self._al_cargar_csv(ruta_csv)

    def _notificar_cambio_config(self, *_args) -> None:
        if self._al_cambiar_config:
            self._al_cambiar_config()

    def mostrar_archivo_cargado(self, ruta_csv: str, num_clientes: int) -> None:
        """Actualiza la etiqueta que indica qué archivo de clientes está cargado."""
        nombre_archivo = ruta_csv.split("/")[-1]
        self.etiqueta_csv.config(
            text=f"{nombre_archivo} ({num_clientes} clientes)", foreground="black"
        )

    def habilitar_boton_optimizar(self, habilitado: bool) -> None:
        """Activa o desactiva el botón de optimización."""
        self.boton_optimizar.config(state="normal" if habilitado else "disabled")

    def obtener_configuracion(self) -> dict:
        """
        Devuelve la configuración introducida por el usuario.

        Raises:
            ValueError: Si el depósito no tiene coordenadas resueltas, si la
                hora de salida no tiene un formato HH:MM válido, o si algún
                campo numérico contiene un valor inválido.
        """
        if self._depot_lat is None or self._depot_lon is None:
            raise ValueError("La dirección del depósito no se ha resuelto todavía")

        hora_salida_min = self._validar_hora("Hora de salida", self.var_hora_salida)
        hora_limite_regreso_min = self._validar_hora(
            "Hora límite de regreso", self.var_hora_limite_regreso
        )

        if hora_limite_regreso_min <= hora_salida_min:
            raise ValueError(
                "La hora límite de regreso debe ser posterior a la hora de salida"
            )

        flota_ilimitada = bool(self.var_flota_ilimitada.get())

        return {
            "depot_lat": self._depot_lat,
            "depot_lon": self._depot_lon,
            "depot_direccion": self.var_depot_direccion.get().strip(),
            # None significa flota ilimitada para el optimizador.
            "num_vehiculos": None if flota_ilimitada else int(self.var_num_vehiculos.get()),
            "flota_ilimitada": flota_ilimitada,
            "capacidad_vehiculo": float(self.var_capacidad_vehiculo.get()),
            "horas_semana": float(self.var_horas_semana.get()),
            "permitir_extendido": bool(self.var_permitir_extendido.get()),
            "hora_salida_min": hora_salida_min,
            "hora_limite_regreso_min": hora_limite_regreso_min,
            "incluir_regreso": bool(self.var_incluir_regreso.get()),
            "nombre_conductor": self.var_nombre_conductor.get().strip(),
        }

    @staticmethod
    def _validar_hora(etiqueta: str, variable: tk.StringVar) -> int:
        """
        Valida un campo de hora y lo convierte a minutos desde medianoche.

        Args:
            etiqueta: Nombre del campo, usado en los mensajes de error.
            variable: Variable de Tkinter que contiene el texto HH:MM.

        Raises:
            ValueError: Si el texto no tiene formato HH:MM o está fuera del
                rango de un día.
        """
        texto = variable.get().strip()
        try:
            minutos = hhmm_a_minutos(texto)
        except (ValueError, AttributeError) as error:
            raise ValueError(
                f"{etiqueta}: '{texto}' no tiene un formato HH:MM válido"
            ) from error

        if not 0 <= minutos < 24 * 60:
            raise ValueError(f"{etiqueta}: '{texto}' está fuera del rango 00:00-23:59")

        return minutos
