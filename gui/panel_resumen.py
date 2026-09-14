"""
Panel de resumen pre-optimización.

Muestra, antes de ejecutar el algoritmo, las horas ya conducidas esta
semana, el techo de conducción diaria real, el número de clientes cargados,
una estimación de cuántos serán alcanzables y las advertencias del
Reglamento (CE) nº 561/2006 que corresponda mostrar.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from algoritmo.restricciones import ResumenPreOptimizacion
from datos.modelos import minutos_a_hhmm


class PanelResumen(ttk.Frame):
    """Panel que muestra el resumen pre-optimización, actualizado en vivo."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, padding=10)

        ttk.Label(self, text="Resumen pre-optimización", font=("TkDefaultFont", 12, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        self.var_horas_semana = tk.StringVar(value="—")
        self.var_techo_diario = tk.StringVar(value="—")
        self.var_hora_salida = tk.StringVar(value="—")
        self.var_clientes_cargados = tk.StringVar(value="—")
        self.var_factibilidad = tk.StringVar(value="—")

        self._agregar_fila("Horas conducidas esta semana:", self.var_horas_semana)
        self._agregar_fila("Techo diario disponible:", self.var_techo_diario)
        self._agregar_fila("Horario de la jornada:", self.var_hora_salida)
        self._agregar_fila("Clientes cargados:", self.var_clientes_cargados)
        self._agregar_fila("Factibilidad estimada:", self.var_factibilidad)

        ttk.Label(self, text="Advertencias", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(10, 2)
        )
        # `width=1` es deliberado: un `Text` pide 80 caracteres de ancho por
        # omisión (unos 590 px) y eso arrastraba a toda la columna, que se
        # comía el espacio del mapa. Como se empaqueta con `fill="x"`, acaba
        # ocupando el ancho real de la columna de todos modos.
        self.texto_advertencias = tk.Text(
            self,
            height=6,
            width=1,
            wrap="word",
            state="disabled",
            background="#fff8e1",
            relief="flat",
        )
        self.texto_advertencias.pack(fill="both", expand=True)

        self.actualizar(None)

    def _agregar_fila(self, etiqueta: str, variable: tk.StringVar) -> None:
        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=2)
        ttk.Label(fila, text=etiqueta).pack(side="left")
        ttk.Label(fila, textvariable=variable, font=("TkDefaultFont", 10, "bold")).pack(side="right")

    def actualizar(self, resumen: Optional[ResumenPreOptimizacion]) -> None:
        """Refresca el panel con un nuevo resumen, o lo deja en blanco si es None."""
        if resumen is None:
            self.var_horas_semana.set("—")
            self.var_techo_diario.set("—")
            self.var_hora_salida.set("—")
            self.var_clientes_cargados.set("—")
            self.var_factibilidad.set("—")
            self._actualizar_advertencias([])
            return

        self.var_horas_semana.set(f"{resumen.horas_semana_conducidas:.1f} h")
        self.var_techo_diario.set(
            f"{resumen.techo_diario_min / 60:.1f} h ({resumen.techo_diario_min:.0f} min)"
        )
        self.var_hora_salida.set(
            f"{minutos_a_hhmm(resumen.hora_inicio_jornada)} – "
            f"{minutos_a_hhmm(resumen.hora_limite_regreso)}"
        )
        self.var_clientes_cargados.set(str(resumen.numero_clientes))
        self.var_factibilidad.set(
            f"{resumen.clientes_alcanzables_estimados} / {resumen.numero_clientes} clientes"
        )
        self._actualizar_advertencias(resumen.advertencias)

    def _actualizar_advertencias(self, advertencias: list[str]) -> None:
        self.texto_advertencias.config(state="normal")
        self.texto_advertencias.delete("1.0", "end")
        if advertencias:
            texto = "\n".join(f"⚠ {advertencia}" for advertencia in advertencias)
        else:
            texto = "Sin advertencias."
        self.texto_advertencias.insert("1.0", texto)
        self.texto_advertencias.config(state="disabled")
