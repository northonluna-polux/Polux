"""
Diálogo modal de progreso.

Se usa durante operaciones que pueden tardar varios segundos, como la
geocodificación de direcciones al cargar un CSV con muchos clientes
(Nominatim exige un mínimo de un segundo entre peticiones).
"""

import tkinter as tk
from tkinter import ttk


class DialogoProgreso(tk.Toplevel):
    """Ventana modal con una barra de progreso, inicialmente indeterminada."""

    def __init__(self, parent: tk.Widget, titulo: str, texto_inicial: str):
        super().__init__(parent)
        self.title(titulo)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # no cerrar manualmente

        self.var_texto = tk.StringVar(value=texto_inicial)
        ttk.Label(self, textvariable=self.var_texto, padding=(16, 12, 16, 4), width=48).pack()

        self._barra = ttk.Progressbar(self, mode="indeterminate", length=340)
        self._barra.pack(padx=16, pady=(0, 16))
        self._barra.start(15)
        self._modo_determinado = False

        self.grab_set()
        self.update_idletasks()

    def actualizar(self, indice: int, total: int, texto: str) -> None:
        """Actualiza la barra de progreso y el texto mostrado."""
        if not self._modo_determinado and total > 0:
            self._barra.stop()
            self._barra.config(mode="determinate", maximum=total, value=0)
            self._modo_determinado = True

        if self._modo_determinado:
            self._barra["value"] = indice

        self.var_texto.set(texto)
        self.update_idletasks()

    def cerrar(self) -> None:
        """Cierra el diálogo de progreso."""
        self.grab_release()
        self.destroy()
