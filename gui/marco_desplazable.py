"""
Marco con barra de desplazamiento vertical.

Los paneles laterales de Polux tienen más contenido del que cabe en una
pantalla de portátil: solo la columna de configuración necesita unos 900
píxeles de alto. Sin poder desplazarse, los controles de abajo (cargar el
CSV, optimizar, exportar) quedaban fuera de la ventana y resultaban
inalcanzables.

Este contenedor resuelve el problema de la forma habitual en Tkinter, que
no trae un marco desplazable: un lienzo (`Canvas`) que puede desplazarse,
con un marco normal dentro. Los widgets se añaden a `.interior`, nunca al
propio `MarcoDesplazable`.

La barra solo aparece cuando hace falta, para no robar espacio ni sugerir
que hay contenido oculto cuando no lo hay.
"""

import sys
import tkinter as tk
from tkinter import ttk


class MarcoDesplazable(ttk.Frame):
    """
    Contenedor con desplazamiento vertical.

    Los widgets hijos deben crearse dentro del atributo `interior`:

        marco = MarcoDesplazable(padre)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco.interior, text="hola").pack()
    """

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)

        self._lienzo = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self._barra = ttk.Scrollbar(self, orient="vertical", command=self._lienzo.yview)
        self._lienzo.configure(yscrollcommand=self._barra.set)

        # Se usa `grid` y no `pack`: con `pack`, el lienzo va primero y con
        # `expand`, así que cuando su ancho solicitado supera el del panel se
        # queda con toda la cavidad y la barra no llega a mostrarse nunca.
        # Con `grid`, la columna de la barra tiene su hueco reservado.
        self._lienzo.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        #: Marco donde se añaden los widgets hijos.
        self.interior = ttk.Frame(self._lienzo)
        self._ventana_interior = self._lienzo.create_window(
            (0, 0), window=self.interior, anchor="nw"
        )

        self.interior.bind("<Configure>", self._al_redimensionar_interior)
        self._lienzo.bind("<Configure>", self._al_redimensionar_lienzo)

        # La rueda solo se captura mientras el puntero está encima, para no
        # robar el desplazamiento a otros paneles de la ventana.
        self._lienzo.bind("<Enter>", self._activar_rueda)
        self._lienzo.bind("<Leave>", self._desactivar_rueda)

    def _al_redimensionar_interior(self, _evento) -> None:
        """Ajusta la región desplazable al contenido y muestra u oculta la barra."""
        self._lienzo.configure(scrollregion=self._lienzo.bbox("all"))
        self._propagar_ancho_solicitado()
        self._actualizar_visibilidad_barra()

    def _propagar_ancho_solicitado(self) -> None:
        """
        Hace que el lienzo pida el ancho que necesita su contenido.

        Un `Canvas` vacío pide un ancho fijo por omisión (unos 265 px), muy
        inferior al de estos paneles. Sin esto, el contenedor padre (aquí un
        `PanedWindow`) reserva ese ancho por omisión y los rótulos salen
        recortados. Solo se propaga el ancho: el alto es justamente lo que
        este marco existe para no imponer.
        """
        ancho = self.interior.winfo_reqwidth() + self._barra.winfo_reqwidth()
        if self._lienzo.cget("width") != ancho:
            self._lienzo.configure(width=ancho)

    def _al_redimensionar_lienzo(self, evento) -> None:
        """Hace que el contenido ocupe todo el ancho disponible."""
        self._lienzo.itemconfigure(self._ventana_interior, width=evento.width)
        self._actualizar_visibilidad_barra()

    def _actualizar_visibilidad_barra(self) -> None:
        """Muestra la barra solo si el contenido no cabe."""
        hace_falta = self.interior.winfo_reqheight() > self._lienzo.winfo_height()
        if hace_falta and not self._barra.winfo_ismapped():
            self._barra.grid(row=0, column=1, sticky="ns")
        elif not hace_falta and self._barra.winfo_ismapped():
            # `grid_remove` conserva la posición para volver a mostrarla.
            self._barra.grid_remove()

    def _activar_rueda(self, _evento) -> None:
        # En Linux la rueda llega como los botones 4 y 5; en Windows y macOS
        # como un evento MouseWheel, pero con escalas de `delta` distintas.
        self._lienzo.bind_all("<MouseWheel>", self._al_girar_rueda)
        self._lienzo.bind_all("<Button-4>", self._al_girar_rueda)
        self._lienzo.bind_all("<Button-5>", self._al_girar_rueda)

    def _desactivar_rueda(self, _evento) -> None:
        self._lienzo.unbind_all("<MouseWheel>")
        self._lienzo.unbind_all("<Button-4>")
        self._lienzo.unbind_all("<Button-5>")

    def _al_girar_rueda(self, evento) -> None:
        if self.interior.winfo_reqheight() <= self._lienzo.winfo_height():
            return  # todo el contenido cabe: no hay nada que desplazar

        if evento.num == 4:
            unidades = -1
        elif evento.num == 5:
            unidades = 1
        elif sys.platform == "darwin":
            unidades = -evento.delta
        else:
            unidades = -evento.delta // 120

        self._lienzo.yview_scroll(int(unidades), "units")
