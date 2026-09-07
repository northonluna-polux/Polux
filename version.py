"""
Identidad y versión de la aplicación.

Se define en un módulo propio y sin dependencias para que puedan leerlo
tanto la aplicación como el archivo de configuración de PyInstaller.
"""

#: Nombre de la aplicación, usado en títulos, rutas de datos y empaquetado.
NOMBRE_APLICACION = "Polux"

#: Versión de la aplicación (control de versiones semántico).
VERSION = "1.0.0"

#: Versión como tupla de cuatro enteros, formato que exige el recurso de
#: versión de los ejecutables de Windows.
VERSION_TUPLA = (1, 0, 0, 0)

#: Descripción breve, mostrada en las propiedades del ejecutable.
DESCRIPCION = "Optimización de rutas de reparto con restricciones VRPTW y Reglamento (CE) 561/2006"
