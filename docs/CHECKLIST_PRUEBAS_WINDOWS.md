# Lista de comprobación en Windows

Esta lista sirve para validar el ejecutable de Polux **antes de publicar la
versión**. Hay que ejecutarla en un **Windows 10 u 11 de 64 bits con
conexión a internet**, preferiblemente en un equipo donde Polux no se haya
usado nunca (así se comprueba también el primer arranque).

Se tarda unos **10 minutos**. Anota el resultado de cada punto y cualquier
mensaje de error que aparezca.

- **Versión probada:** ..............................
- **Windows:** ..............................
- **Fecha:** ..............................
- **Persona:** ..............................

---

## 1. Primer arranque

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Descargar `Polux-1.0.0.exe` de la página de versiones | El archivo ocupa entre 15 MB y 150 MB aproximadamente |
| ☐ | Doble clic en el ejecutable | Aparece el aviso de SmartScreen |
| ☐ | Pulsar «Más información» → «Ejecutar de todas formas» | La aplicación arranca |
| ☐ | Esperar a que se abra la ventana | Tarda unos segundos la primera vez (se descomprime); no debe aparecer ninguna consola negra |
| ☐ | Observar la ventana | Se ven tres columnas: configuración a la izquierda, mapa en el centro, resultados a la derecha |

**Si la aplicación se cierra sola o muestra un error al arrancar, para aquí
y anota el mensaje completo.** Suele indicar que falta alguna dependencia en
el empaquetado.

## 2. Cargar los clientes de ejemplo

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Pulsar «Cargar clientes (CSV)...» | Se abre el diálogo de archivos |
| ☐ | Buscar y abrir `clientes_ejemplo.csv` | Ver la nota de abajo sobre dónde está |
| ☐ | Mirar bajo el botón | Dice `clientes_ejemplo.csv (15 clientes)` |
| ☐ | Mirar el «Resumen pre-optimización» | Techo diario: `9.0 h (540 min)`; Horario: `08:00 – 18:00`; Clientes cargados: `15` |
| ☐ | El botón «Optimizar rutas» | Ha pasado de gris a activo |

> **Dónde está el CSV de ejemplo.** Va dentro del ejecutable, así que el
> diálogo debería abrirse ya en su carpeta. Si no aparece, descárgalo del
> repositorio (`datos/clientes_ejemplo.csv`) y guárdalo en el Escritorio.

## 3. Optimizar

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Pulsar «Optimizar rutas» | El cursor cambia a «ocupado» un momento mientras consulta OSRM |
| ☐ | Panel de resultados: «Distancia total» | Un valor alrededor de `77 km` (puede variar si OSRM cambia sus datos) |
| ☐ | Panel de resultados: «Vehículos utilizados» | `2` |
| ☐ | Tabla «Rutas» | Dos filas, con nº de paradas, distancia, tiempos y pausas |
| ☐ | Pulsar sobre una fila de la tabla | Abajo aparece la secuencia de paradas con sus horas de llegada |
| ☐ | Tabla «Clientes sin asignar» | Vacía (con 3 vehículos y capacidad 100 caben los 15) |

**Si sale un error de conexión con OSRM**, comprueba que hay internet y
vuelve a intentarlo: el servicio público puede estar saturado. Anótalo, pero
no es un fallo del ejecutable.

## 4. Mapa

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Mirar la columna central | Muestra un texto titulado «Mapa de rutas» explicando que el mapa se abre en el navegador. **No debe estar en blanco** |
| ☐ | Pulsar «Abrir mapa interactivo en el navegador» | Se abre el navegador predeterminado |
| ☐ | Mirar el mapa en el navegador | Se ve Valencia con un marcador negro (depósito) y los clientes en dos colores distintos |
| ☐ | Comprobar las líneas de las rutas | Siguen las calles: hacen curvas y giros, no son líneas rectas entre puntos |
| ☐ | Pulsar sobre un marcador de cliente | Aparece un globo con nombre, vehículo, orden de visita, ventana, hora estimada de llegada y demanda |

## 5. Hoja de ruta en PDF

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Escribir un nombre en «Nombre del conductor (opcional)» | Por ejemplo, tu nombre |
| ☐ | Pulsar «Optimizar rutas» otra vez | Para que el nombre entre en la hoja |
| ☐ | Pulsar «Hojas de ruta (PDF)...» | Se abre una ventana de previsualización con la hoja dibujada como imagen |
| ☐ | Mirar la cabecera de la hoja | Fecha de hoy, `Ruta nº`, vehículo, el nombre del conductor que escribiste, `Salida: 08:00` y `Límite regreso: 18:00` |
| ☐ | Mirar el bloque resumen | Paradas, distancia, hora de salida, y debajo tiempo de conducción, de espera y total |
| ☐ | Mirar la tabla de paradas | Una fila por cliente, con dirección, hora estimada, demanda y tiempo de servicio |
| ☐ | Mirar la última fila de la tabla | Dice `REGRESO AL DEPÓSITO` con una hora |
| ☐ | Usar «Siguiente ▶» y «◀ Anterior» | Se cambia de hoja; el contador dice `Ruta 1 de 2 — página 1 de 1` |
| ☐ | Pulsar «Guardar PDF» y elegir una carpeta | Se crean `Ruta_1_<fecha>.pdf` y `Ruta_2_<fecha>.pdf` |
| ☐ | Abrir uno de los PDF generados | Se abre bien y el contenido coincide con la previsualización |
| ☐ | *(Opcional, si hay impresora)* Pulsar «Imprimir» | El trabajo llega a la impresora predeterminada |

## 6. Enlace de Google Maps

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Pulsar «Abrir Ruta 1 en Google Maps» | Se abre el navegador en Google Maps |
| ☐ | Mirar el itinerario | Sale una ruta con varias paradas, empezando y acabando en el depósito de Valencia |
| ☐ | Pegar el portapapeles en un editor de texto (Ctrl+V) | Aparece la misma URL: el enlace también se copia |

## 7. Geocodificación de direcciones

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Cambiar «Dirección del depósito» por otra, p. ej. `Estación del Norte, Valencia` | — |
| ☐ | Pulsar «Buscar» | Debajo cambian las coordenadas |
| ☐ | Escribir una dirección inventada, p. ej. `qwertyasdf 12345` y pulsar «Buscar» | Aparece el mensaje `Dirección no encontrada. Intenta ser más específico.` |
| ☐ | Volver a poner una dirección válida y pulsar «Buscar» | Se recuperan unas coordenadas correctas |

## 8. Restricciones del Reglamento

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Poner «Horas ya conducidas esta semana» a `54` | El resumen muestra un techo diario de `2.0 h (120 min)` y un aviso de techo críticamente bajo |
| ☐ | Pulsar «Optimizar rutas» | Varios clientes quedan sin asignar con motivo `TIEMPO` |
| ☐ | Poner las horas a `56` y pulsar «Optimizar rutas» | Sale un error: la optimización está bloqueada por no quedar horas disponibles |
| ☐ | Volver a poner `0` | El resumen recupera las `9.0 h` |
| ☐ | Poner «Número de vehículos» a `1` y optimizar | Sobran clientes con motivo `FLOTA`, porque la demanda total (186) supera la capacidad de un vehículo (100) |

## 9. Dónde guarda sus datos

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Abrir el Explorador y escribir `%LOCALAPPDATA%\Polux` en la barra de direcciones | La carpeta existe |
| ☐ | Mirar su contenido | Hay un `geocache.json` (direcciones consultadas) y, si guardaste PDF ahí, una carpeta `hojas_de_ruta` |
| ☐ | Comprobar la carpeta del ejecutable | **No** se han creado archivos junto al `.exe` |

## 10. Cierre

| | Comprobación | Resultado esperado |
|---|---|---|
| ☐ | Cerrar la ventana | La aplicación se cierra sin errores |
| ☐ | Abrir el Administrador de tareas | No queda ningún proceso `Polux` colgado |
| ☐ | Volver a abrir la aplicación | Arranca más rápido y sin aviso de SmartScreen |

---

## Resultado

- ☐ **Todo correcto** — se puede publicar la versión.
- ☐ **Con problemas menores** — se puede publicar, anotándolos como
  limitaciones conocidas. Cuáles: ..............................
- ☐ **Con problemas graves** — no publicar. Cuáles:
  ..............................

**Observaciones:**

..................................................................

..................................................................
