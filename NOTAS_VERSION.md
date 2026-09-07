## Polux 1.0.0

Primera versión pública. Polux planifica las rutas de reparto de una flota
para una jornada, con distancias reales por carretera y cumpliendo los
límites de conducción y descanso del **Reglamento (CE) nº 561/2006**.

### Qué incluye

- Optimización **VRPTW** en tres fases: construcción con el algoritmo de
  ahorros de **Clarke-Wright**, mejora local con **2-opt** y reinserción de
  los clientes descartados.
- **Distancias y tiempos reales por carretera** mediante OSRM.
- **Reglamento 561/2006**: pausa obligatoria de 45 min tras 4 h 30 de
  conducción continua (incluso si cae en mitad de un trayecto), máximo de
  9 h diarias ampliable a 10 h, y tope semanal de 56 h descontando las horas
  ya conducidas.
- **Hora de salida y hora límite de regreso** configurables, que acotan la
  duración de la jornada.
- Clientes por **coordenadas o por dirección de texto**, geocodificada con
  Nominatim y guardada en caché.
- **Hojas de ruta en PDF** con previsualización en pantalla antes de
  guardar o imprimir, con las pausas obligatorias intercaladas en el
  itinerario.
- **Enlace de Google Maps por ruta**, que se abre en el navegador o en el
  móvil y se copia al portapapeles.
- Exportación de resultados a **CSV** y del mapa a **HTML**.
- Motivos de exclusión explícitos por cliente: `CAPACIDAD`, `VENTANA`,
  `TIEMPO`, `FLOTA` y `GEOCODIFICACIÓN`.

### Requisitos

- **Windows 10 o 11** de 64 bits. No requiere instalar Python.
- **Conexión a internet** para calcular rutas (OSRM) y geocodificar
  direcciones nuevas (Nominatim). Las direcciones ya consultadas quedan en
  caché y siguen funcionando sin red.

### Aviso de SmartScreen al abrirlo

El ejecutable **no está firmado digitalmente**, porque firmar requiere un
certificado de pago. Por eso Windows mostrará un aviso la primera vez:

> *Windows ha protegido tu PC*

Para continuar: pulsa **«Más información»** y después
**«Ejecutar de todas formas»**. El aviso no aparecerá en los siguientes
arranques.

### Limitaciones conocidas

- **El mapa interactivo se abre en el navegador**, no dentro de la ventana:
  el visor HTML integrado no ejecuta JavaScript y los mapas se dibujan con
  Leaflet, que lo necesita. La aplicación incluye un botón para abrirlo.
- **OSRM y Nominatim son instancias públicas de demostración**, sin
  garantía de disponibilidad. OSRM limita la matriz a 100 ubicaciones por
  consulta y Nominatim a una petición por segundo. Para uso continuado hay
  que instalar instancias propias.
- **Flota homogénea**: una sola capacidad para todos los vehículos.
- **Un viaje por vehículo y día**: no se contemplan segundas cargas, así que
  si la demanda total supera la capacidad de la flota sobran clientes.
- El algoritmo de ahorros **acepta cualquier fusión factible**, incluso con
  ahorro negativo, lo que puede alargar la distancia total cuando sobran
  vehículos, aunque a cambio atiende a más clientes cuando escasean.
- La **reinserción solo inserta en rutas existentes**: nunca abre una ruta
  nueva aunque quede un vehículo libre, ni intercambia clientes entre rutas.
- Las **pausas obligatorias se sitúan en el itinerario** pero no proponen un
  lugar concreto donde parar: indican el trayecto, no el área de servicio.
- La columna **«Observaciones»** de las hojas de ruta se deja en blanco a
  propósito, para que el conductor anote a mano.
- **Impresión al dispositivo predeterminado**: no hay selección de
  impresora, rango de páginas ni número de copias.
- Frente a las mejores soluciones publicadas de las instancias de Solomon,
  los resultados quedan entre un **+10 % y un +23 % en distancia** y usan
  bastantes más vehículos. Es lo esperable de una heurística constructiva
  con mejora local; el detalle está en `DOCUMENTACION_TECNICA.md`.

### Licencia

MIT. El código fuente y la documentación técnica están en el repositorio.
