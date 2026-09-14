"""
Diálogo de previsualización de las hojas de ruta en PDF.

Muestra las hojas de ruta generadas página a página, renderizadas como
imágenes, para que el usuario pueda revisarlas antes de guardarlas o
imprimirlas.

Decisión de implementación (renderizado del PDF a imagen)
---------------------------------------------------------
Se usa PyMuPDF (`pymupdf`, importado históricamente como `fitz`) para
rasterizar cada página del PDF ya maquetado.

Se descartaron las dos alternativas consideradas:

* `pypdf` + `pdf2image`: `pdf2image` es un envoltorio sobre las utilidades
  de Poppler, por lo que exige instalar Poppler en el sistema
  (`brew install poppler`, `apt install poppler-utils`, binarios aparte en
  Windows). Eso rompe la instalación con un simple
  `pip install -r requirements.txt`, que es un requisito práctico del
  proyecto.
* `reportlab.graphics.renderPM`: solo sabe rasterizar objetos `Drawing` de
  `reportlab.graphics`, no documentos de `platypus` como estas hojas de
  ruta. Habría obligado a mantener una segunda maquetación paralela solo
  para la vista previa, con el riesgo de que dejara de coincidir con el PDF
  real.

PyMuPDF se instala como rueda binaria desde PyPI (sin dependencias del
sistema) y rasteriza exactamente el mismo PDF que se va a guardar, así que
lo que se previsualiza es literalmente lo que se exporta.
"""

import os
import platform
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pymupdf

from datos.modelos import ClienteNoAsignado, Nodo, Ruta
from utils.rutas_app import directorio_hojas_de_ruta
from gui.pdf_rutas import (
    generar_hoja_de_ruta_en_memoria,
    generar_hojas_de_ruta_pdf,
    nombre_archivo_ruta,
)

#: Factor de escala al rasterizar cada página (2.0 ≈ 144 dpi, legible en pantalla)
ESCALA_RENDERIZADO = 2.0

#: Ancho máximo en píxeles de la imagen mostrada, para que quepa en la ventana
ANCHO_MAXIMO_VISTA = 780

#: Píxeles que se reservan para la barra superior, la de botones y el marco
#: de la ventana al calcular cuánto alto queda para la página.
ALTO_RESERVADO_CONTROLES = 190


class DialogoPrevisualizacion(tk.Toplevel):
    """Ventana modal que previsualiza, guarda e imprime las hojas de ruta."""

    def __init__(
        self,
        parent: tk.Widget,
        depot: Nodo,
        rutas: list[Ruta],
        no_asignados: list[ClienteNoAsignado],
        fecha_texto: str,
        nombre_conductor: str,
        hora_inicio_jornada_min: int,
    ):
        super().__init__(parent)
        self.title("Previsualización de las hojas de ruta")
        self.transient(parent)

        self._depot = depot
        self._rutas = rutas
        self._no_asignados = no_asignados
        self._fecha_texto = fecha_texto
        self._nombre_conductor = nombre_conductor
        self._hora_inicio_jornada_min = hora_inicio_jornada_min

        # Lista plana de páginas: (indice_ruta, numero_pagina_en_ruta,
        # total_paginas_de_esa_ruta, imagen). Así la navegación recorre
        # todas las páginas de todas las rutas de forma continua.
        self._paginas: list[tuple[int, int, int, tk.PhotoImage]] = []
        self._indice_actual = 0
        self._pdfs_por_ruta: list[bytes] = []

        self._construir_widgets()
        self._renderizar_todas_las_hojas()
        self._mostrar_pagina_actual()

        self.grab_set()

    def _alto_maximo_pagina(self) -> int:
        """
        Alto máximo, en píxeles, que puede ocupar la imagen de la página.

        Se calcula a partir de la pantalla y no con una constante fija: una
        hoja A4 rasterizada mide más que la altura útil de un portátil, y si
        no se acota, la ventana crece tanto que la barra de botones queda
        fuera de la pantalla y no hay forma de guardar ni imprimir.
        """
        return max(320, self.winfo_screenheight() - ALTO_RESERVADO_CONTROLES)

    def _construir_widgets(self) -> None:
        marco_superior = ttk.Frame(self, padding=(10, 8))
        marco_superior.pack(side="top", fill="x")

        self.var_contador = tk.StringVar(value="—")
        ttk.Label(
            marco_superior, textvariable=self.var_contador, font=("TkDefaultFont", 10, "bold")
        ).pack(side="left")

        self._boton_anterior = ttk.Button(
            marco_superior, text="◀ Anterior", command=self._pagina_anterior
        )
        self._boton_anterior.pack(side="right", padx=(4, 0))
        self._boton_siguiente = ttk.Button(
            marco_superior, text="Siguiente ▶", command=self._pagina_siguiente
        )
        self._boton_siguiente.pack(side="right")

        # La barra de acciones se empaqueta ANTES que la imagen y anclada
        # abajo. Al empaquetarla la última, como estaba, era lo primero que
        # se salía de la pantalla cuando la página no cabía, dejando los
        # botones de guardar e imprimir inalcanzables.
        marco_acciones = ttk.Frame(self, padding=(10, 0, 10, 10))
        marco_acciones.pack(side="bottom", fill="x")

        self._etiqueta_pagina = ttk.Label(self, relief="sunken", anchor="center")
        self._etiqueta_pagina.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 8))
        ttk.Button(marco_acciones, text="Guardar PDF", command=self._guardar).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ttk.Button(marco_acciones, text="Imprimir", command=self._imprimir).pack(
            side="left", expand=True, fill="x", padx=4
        )
        ttk.Button(marco_acciones, text="Cerrar", command=self._cerrar).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
        )

    def _renderizar_todas_las_hojas(self) -> None:
        """Genera cada hoja de ruta en memoria y rasteriza todas sus páginas."""
        for indice_ruta, ruta in enumerate(self._rutas):
            contenido_pdf = generar_hoja_de_ruta_en_memoria(
                depot=self._depot,
                ruta=ruta,
                no_asignados=self._no_asignados,
                fecha_texto=self._fecha_texto,
                nombre_conductor=self._nombre_conductor,
                hora_inicio_jornada_min=self._hora_inicio_jornada_min,
            )
            self._pdfs_por_ruta.append(contenido_pdf)

            documento = pymupdf.open(stream=contenido_pdf, filetype="pdf")
            try:
                total_paginas = documento.page_count
                for numero_pagina in range(total_paginas):
                    pagina = documento.load_page(numero_pagina)
                    mapa_bits = pagina.get_pixmap(
                        matrix=pymupdf.Matrix(ESCALA_RENDERIZADO, ESCALA_RENDERIZADO)
                    )
                    imagen = tk.PhotoImage(data=mapa_bits.tobytes("ppm"))

                    # PhotoImage solo permite reducir por factores enteros;
                    # se aplica el menor factor que haga caber la página
                    # tanto de ancho como de alto. Acotar solo el ancho, como
                    # se hacía antes, dejaba una imagen demasiado alta para
                    # la pantalla.
                    factor_ancho = -(-mapa_bits.width // ANCHO_MAXIMO_VISTA)
                    factor_alto = -(-mapa_bits.height // self._alto_maximo_pagina())
                    factor_reduccion = max(1, factor_ancho, factor_alto)
                    if factor_reduccion > 1:
                        imagen = imagen.subsample(factor_reduccion, factor_reduccion)

                    self._paginas.append(
                        (indice_ruta, numero_pagina + 1, total_paginas, imagen)
                    )
            finally:
                documento.close()

    def _mostrar_pagina_actual(self) -> None:
        if not self._paginas:
            self.var_contador.set("No hay hojas de ruta que previsualizar")
            return

        indice_ruta, numero_pagina, total_paginas, imagen = self._paginas[self._indice_actual]
        ruta = self._rutas[indice_ruta]

        self._etiqueta_pagina.config(image=imagen)
        # Se guarda una referencia para que el recolector de basura de Python
        # no descarte la imagen mientras se está mostrando.
        self._etiqueta_pagina.image = imagen

        self.var_contador.set(
            f"Ruta {ruta.vehiculo.id} de {len(self._rutas)} — "
            f"página {numero_pagina} de {total_paginas}"
        )
        self._boton_anterior.config(
            state="normal" if self._indice_actual > 0 else "disabled"
        )
        self._boton_siguiente.config(
            state="normal" if self._indice_actual < len(self._paginas) - 1 else "disabled"
        )

    def _pagina_anterior(self) -> None:
        if self._indice_actual > 0:
            self._indice_actual -= 1
            self._mostrar_pagina_actual()

    def _pagina_siguiente(self) -> None:
        if self._indice_actual < len(self._paginas) - 1:
            self._indice_actual += 1
            self._mostrar_pagina_actual()

    def _guardar(self) -> None:
        carpeta_destino = filedialog.askdirectory(
            title="Selecciona la carpeta donde guardar las hojas de ruta",
            initialdir=directorio_hojas_de_ruta(),
            parent=self,
        )
        if not carpeta_destino:
            return

        archivos = generar_hojas_de_ruta_pdf(
            depot=self._depot,
            rutas=self._rutas,
            no_asignados=self._no_asignados,
            carpeta_destino=carpeta_destino,
            fecha_texto=self._fecha_texto,
            nombre_conductor=self._nombre_conductor,
            hora_inicio_jornada_min=self._hora_inicio_jornada_min,
        )
        nombres = "\n".join(os.path.basename(archivo) for archivo in archivos)
        messagebox.showinfo(
            "Guardar hojas de ruta",
            f"Se han generado {len(archivos)} hoja(s) de ruta en:\n{carpeta_destino}\n\n{nombres}",
            parent=self,
        )

    def _imprimir(self) -> None:
        """
        Envía las hojas de ruta a la impresora predeterminada del sistema.

        Los PDF se escriben primero en archivos temporales, ya que las
        utilidades de impresión del sistema operan sobre archivos.
        """
        if not self._pdfs_por_ruta:
            return

        carpeta_temporal = tempfile.mkdtemp(prefix="polux_impresion_")
        errores: list[str] = []

        for ruta, contenido_pdf in zip(self._rutas, self._pdfs_por_ruta):
            ruta_temporal = os.path.join(
                carpeta_temporal, nombre_archivo_ruta(ruta, self._fecha_texto)
            )
            with open(ruta_temporal, "wb") as archivo:
                archivo.write(contenido_pdf)

            try:
                if platform.system() == "Windows":
                    os.startfile(ruta_temporal, "print")  # type: ignore[attr-defined]
                else:
                    subprocess.run(["lpr", ruta_temporal], check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                errores.append(f"Ruta {ruta.vehiculo.id}: {error}")

        if errores:
            messagebox.showerror(
                "Error al imprimir",
                "No se pudieron enviar algunas hojas de ruta a la impresora:\n\n"
                + "\n".join(errores),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Imprimir hojas de ruta",
                f"Se han enviado {len(self._rutas)} hoja(s) de ruta a la impresora "
                "predeterminada del sistema.",
                parent=self,
            )

    def _cerrar(self) -> None:
        self.grab_release()
        self.destroy()
