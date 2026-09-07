# Polux — Technical Documentation

This document explains what Polux does, how it is built, and how every module and function fits together. It is meant as a complete technical reference to the codebase — useful both for maintaining the project and as source material for the thesis write-up.

The application itself (code, UI text, comments) is entirely in Spanish, per the academic requirement. This documentation is in English for convenience; ask for a Spanish version if you need one for the thesis body.

---

## 1. What Polux does

Polux is a desktop application that solves a **Vehicle Routing Problem with Time Windows (VRPTW)** for a single day of deliveries, while enforcing the EU driving-time regulation **(EC) No 561/2006**. Given a depot, a fleet of vehicles, and a list of clients (each with a demand, a time window, and a service duration), it:

1. Asks how many hours the driver has already driven this week, and computes the real driving ceiling left for today.
2. Loads clients from a CSV (coordinates and/or free-text addresses).
3. Builds routes with the **Clarke-Wright savings algorithm**, improves them with **2-opt** local search, then runs a **reinsertion pass** that retries clients dropped during construction now that the routes are shorter.
4. Simulates every candidate route against capacity, time windows, and the 561/2006 rules (continuous-driving cap → mandatory break, daily cap, weekly cap), rejecting infeasible clients with a specific reason code.
5. Shows the result on an interactive map with real road-following routes, plus a results panel.
6. Exports results for office use (CSV, standalone HTML map) and for **drivers** (a Google Maps deep link per route, and printable PDF route sheets with an on-screen preview before saving or printing).

Two external, free web services are used at runtime:
- **OSRM** (`router.project-osrm.org`) — real driving distances/times and road-following route geometry.
- **Nominatim** (`nominatim.openstreetmap.org`) — turns a free-text address into coordinates.

---

## 2. Project layout

```
polux/
├── main.py                      # Entry point — launches the Tkinter GUI
├── algoritmo/
│   ├── optimizador.py           # Shared entry point: chains the three phases
│   ├── clarke_wright.py         # Phase 1: savings algorithm (route construction)
│   ├── two_opt.py               # Phase 2: local search (route improvement)
│   ├── reinsercion.py           # Phase 3: retry unassigned clients (cheapest insertion)
│   └── restricciones.py         # VRPTW + Reg. 561/2006 feasibility engine
├── datos/
│   ├── cargador.py              # CSV parsing, validation, geocoding fallback
│   ├── cargador_solomon.py      # Solomon benchmark instance reader (Euclidean matrix)
│   ├── modelos.py               # Core dataclasses (Nodo, Ruta, Vehiculo, ...)
│   ├── clientes_ejemplo.csv     # Sample data (15 clients around Valencia)
│   └── geocache.json            # Disk cache of geocoded addresses (generated at runtime)
├── gui/
│   ├── app.py                   # Main window; orchestrates the whole workflow
│   ├── panel_config.py          # Left panel: depot, fleet, driver, load/optimize
│   ├── panel_resumen.py         # Pre-optimization summary (live)
│   ├── panel_resultados.py      # Results panel + all exports
│   ├── mapa.py                  # Interactive map generation (folium)
│   ├── pdf_rutas.py             # Printable PDF route sheets (reportlab)
│   ├── dialogo_previsualizacion.py  # Preview / save / print the route sheets
│   └── dialogo_progreso.py      # Modal progress dialog (used during geocoding)
├── utils/
│   ├── distancia.py             # Haversine straight-line distance (quick estimate only)
│   ├── osrm.py                  # Real road distances/times + route geometry (OSRM)
│   ├── geocodificacion.py       # Address → coordinates (Nominatim), cached & rate-limited
│   └── google_maps.py           # Builds the per-route Google Maps driving link
├── scripts/
│   └── ejecutar_benchmark.py    # Solomon benchmark runner → results CSV
└── tests/                       # pytest suite, no network access required
    ├── conftest.py              # Hand-built distance matrices + node fixtures
    ├── test_restricciones.py    # 561/2006 limits, breaks, windows, capacity
    ├── test_algoritmo.py        # Clarke-Wright, 2-opt, reinsertion
    ├── test_tiempo_espera.py    # Waiting-time metric + reinsertion toggle
    ├── test_regreso_y_pausas.py # Optional depot return + break placement
    ├── test_solomon.py          # Solomon parser, Euclidean matrix, unlimited fleet
    └── test_osrm_limites.py     # Coordinate cap and bounded cache
```

Dependency direction is roughly: `gui` → `algoritmo` → `datos`/`utils`. `utils` and `datos` don't depend on the GUI, so the algorithm and data layer could in principle be reused headlessly (e.g. in a script or a test suite) without Tkinter.

---

## 3. Data model — `datos/modelos.py`

Everything else in the app is built around a small set of dataclasses. Internally, **all times are stored as minutes since midnight** (e.g. `08:00` → `480`), converted to/from `HH:MM` only at the edges (CSV parsing, UI display).

- **`Nodo`** — a point to visit: depot or client. Fields: `id`, `nombre`, `lat`/`lon` (nullable — `None` only for a client whose address failed to geocode), `demanda`, `hora_inicio`/`hora_fin` (time window), `tiempo_servicio`, `es_depot`, `direccion_original` (the free-text address, if the node came from one; used later to show a real address instead of coordinates in PDFs).
  - `.ventana_como_texto()` → `"08:00-12:00"` style string.
  - `.tiene_coordenadas()` → `True` if lat/lon are resolved.
- **`ClienteNoAsignado`** — a client that couldn't be placed in any feasible route: the `Nodo`, a reason code, and a human-readable detail string.
- **`Vehiculo`** — just `id` + `capacidad`.
- **`Ruta`** — one vehicle's assigned route: ordered stop list, total distance/time/driving-time, **total waiting time**, per-stop arrival times, total load, number of mandatory breaks taken, **the breaks themselves** (`pausas`), and whether the route counts the return leg (`incluye_regreso`). `.clientes()` returns the stops excluding the depot.
- **`PausaReglamentaria`** — one mandatory 45-minute rest, recorded with enough context to place it in a printed itinerary: how many customers had been served when it starts (`indice_parada_previa`), the clock instant it begins, its duration, and the leg (`origen` → `destino`) it falls inside. Counting breaks was not enough: a break can land *mid-leg*, with no customer stop to attach it to, so the driver needs to be told where it happens.
- Five reason-code constants, shared by the whole app: `MOTIVO_CAPACIDAD`, `MOTIVO_VENTANA`, `MOTIVO_TIEMPO`, `MOTIVO_FLOTA`, `MOTIVO_GEOCODIFICACION`. `MOTIVO_FLOTA` specifically means "this client was servable, but the fleet ran out of vehicles" — previously this case reused `MOTIVO_TIEMPO`, which wrongly implied a driving-time violation.
- `MOTIVOS_IRRECUPERABLES` — the subset of reasons that can never be fixed by retrying (`GEOCODIFICACIÓN`, since there is no location to visit at all, and `CAPACIDAD`, since the client's own demand exceeds a whole vehicle). The reinsertion pass (§5.4) skips these.
- Helper functions: `minutos_a_hhmm`, `hhmm_a_minutos` (clock-time conversions), `formatear_duracion_minutos` (duration formatting, e.g. `"4h 08min"` — deliberately different from clock-time formatting so a route's *duration* is never confused with a *time of day*).

---

## 4. Loading data — `datos/cargador.py`

`cargar_clientes_desde_csv(ruta_csv, callback_progreso=None)` is the single entry point. It:

1. Reads the CSV with pandas (`dtype=str`, so nothing gets silently coerced).
2. Validates the base required columns (`id, nombre, demanda, hora_inicio, hora_fin, tiempo_servicio`) and checks that the file provides a way to locate every client — either `lat`+`lon` columns or a `direccion` column (or both).
3. Per row: validates `id` (unique, integer, **not `0`** — that id is reserved for the depot to avoid collisions when the OSRM matrix is indexed by node id), non-empty name, non-negative demand, a valid `HH:MM` window with start < end, and non-negative service time.
4. For location: if the row has real `lat`/`lon` values, those are used directly (and take priority even if a `direccion` is also present in that row). Otherwise, the `direccion` text is geocoded via `utils/geocodificacion.py`. The **original address text is always preserved** on the `Nodo` (in `direccion_original`) for later display, even when coordinates were the ones actually used for positioning.
5. A row whose address fails to geocode does **not** abort the whole load — it's returned separately as a `ClienteNoAsignado` with `MOTIVO_GEOCODIFICACION`, so one bad address doesn't block the other clients from loading.
6. `callback_progreso(indice, total, texto)` is invoked once per address that actually needs geocoding (not for rows that already have coordinates), so the GUI can show progress — this matters because Nominatim enforces a 1-request/second minimum spacing, so geocoding many addresses is visibly slow.

Return value: `(clientes, fallidos_geocodificacion)` — a tuple, not just a list, precisely so that "hard" file errors (`ErrorCargaDatos`, e.g. a malformed row) and "soft" per-row failures (a specific address not found) are handled differently by the caller.

---

## 5. The optimization algorithm — `algoritmo/`

This is the academic core of the project, split cleanly into three files.

### 5.1 `restricciones.py` — the feasibility engine

Everything that decides "can this route actually be driven, legally and physically" lives here, centered on one function:

```
simular_ruta(depot, paradas, capacidad_vehiculo, techo_diario_min, matriz, hora_inicio_jornada=08:00)
    -> ResultadoSimulacion
```

Given a candidate ordered list of stops, it **walks the route minute by minute**:
- Sums total demand up front against vehicle capacity (fails fast with `MOTIVO_CAPACIDAD` if exceeded).
- For each leg (using real road distance/time from the precomputed `matriz`, see §6.1), **consumes the leg in chunks**: it drives up to whatever continuous-driving allowance is left, and the moment that allowance runs out it inserts a **45-minute mandatory break** (Reg. 561/2006), resets the continuous counter, and continues with the remainder of the *same* leg. Chunking matters because a single interurban leg can exceed 4.5 hours on its own, so the break has to be able to fall *mid-leg*, with no client stop to hang it on. Every break is both counted in `numero_pausas` and recorded as a `PausaReglamentaria` in `pausas`, tagged with the number of customers already served, so it can be placed in the printed itinerary.
- Checks accumulated *total* driving time against `techo_diario_min` (today's real ceiling — see below) on every chunk; exceeding it fails with `MOTIVO_TIEMPO`.
- At each client, checks arrival against the time window: too late fails with `MOTIVO_VENTANA`; too early means the vehicle waits until the window opens, and **those idle minutes are accumulated as waiting time** (`tiempo_espera_min`) — the fourth metric of the standard Solomon evaluation criterion, needed for the experimental validation.
- On returning to the depot, checks arrival against the **depot's own closing time** — see "The depot as a node with a time window" below.
- Returns a `ResultadoSimulacion`: feasible or not (with reason + which node broke it), plus full metrics (distance, total time, driving time, waiting time, per-stop arrivals, number of breaks) when feasible.

**The depot as a node with a time window.** The depot is not a special case in the data model: it is an ordinary `Nodo` carrying its own `hora_inicio` and `hora_fin`, and it appears **twice** in the simulated sequence — once on departure and once on return. The two visits play different roles:

- The **departure** visit sets the clock. `hora_inicio` is the configured departure time; the vehicle simply leaves then, and no window check applies (there is nothing to be late for).
- The **return** visit is the one subject to the closing check: arrival must be at or before `hora_fin`, otherwise the route is infeasible with `MOTIVO_VENTANA`.

That closing time is the **maximum end-of-day time**, and it exists because Regulation 561/2006 caps *driving* hours, not *elapsed* hours. A route with long waits can span twelve or fourteen hours while staying comfortably under the nine-hour driving limit — legal, but operationally unusable. Nothing else in the model bounds elapsed time, so without this the solver would happily emit such a day.

Three properties of the check are deliberate:

- **It applies whether or not regulations are enabled.** It is a working-day constraint, not a driving-law one. This also matters for the benchmark instances (§6.5), where the depot's due date encodes the route's total time budget: with the check absent, evaluation mode had nothing bounding route duration at all, so Clarke-Wright merged routes indefinitely and reported fewer vehicles than legitimately achievable — making the numbers incomparable with published results.
- **It is skipped entirely when `incluir_regreso=False`**, since an open route ends at the last customer and never arrives back.
- **Its rejection message is distinct.** A depot-closing failure and a customer-window failure share the code `MOTIVO_VENTANA` but are different problems, so `simular_ruta` fills `ResultadoSimulacion.detalle` with a working-day explanation naming the estimated return time and the configured limit ("La jornada terminaría a las 18:30, después de la hora límite de regreso al depósito (18:00)"). `clarke_wright._detalle_motivo` prefers that text over its generic per-reason message, so the user is not told a customer window failed when the real problem is the length of the day. The `nodo_conflicto` is `None` in this case, since no single customer is at fault.

**The `incluir_regreso` flag.** By default the simulated sequence is `depot → stops → depot`, and that return leg counts toward distance, time and the driving limits. Passing `incluir_regreso=False` drops it, so the day ends at the last customer — the *open* VRP variant, for operations where the vehicle does not need to come back to base. Two consequences worth noting: the depot's closing time is not checked (there is no arrival to validate), and routes that were infeasible with the return can become feasible without it, which typically means **fewer vehicles are needed**. The map polyline and the Google Maps link both honour the flag, so a return leg is never drawn for a route that does not plan one.

**The `aplicar_reglamento` flag.** Passing `aplicar_reglamento=False` disables the two 561/2006-specific behaviours — mandatory-break insertion and the daily-ceiling check (including the early `techo_diario_min <= 0` rejection). Capacity and time windows still apply, since those are VRPTW constraints, not driving-regulation ones. This exists solely for the benchmark instances, which have no notion of hours of the day; see §6.5 and §11.

The **daily ceiling** itself comes from `calcular_techo_diario_minutos(horas_semana_conducidas, permitir_extendido)`:

```
techo_diario = min(9h [or 10h if extended-day allowed], 56h − hours already driven this week)
```

clamped to never go negative. If it comes out to `0` (or less), `ResumenPreOptimizacion.bloqueado` is `True` and the GUI refuses to run the optimizer at all, with a clear message.

The rest of the file builds the **pre-optimization summary** shown before you click "Optimize": `estimar_clientes_alcanzables` gives a fast, offline, Haversine-based *estimate* of how many clients are reachable today (average round-trip time per client vs. total available driving capacity across all vehicles) — deliberately not using the real OSRM distances here, so this live-updating panel never has to make a network call while you're just typing into a field. `generar_resumen_preoptimizacion` assembles all of this plus contextual warnings (blocked / critically low ceiling / "only N of M clients likely reachable").

`alerta_proximidad_limite` flags any *finished, feasible* route that used ≥90% of the daily ceiling — shown in the results panel as a compliance warning even though nothing was technically violated.

**Modeling simplification worth noting explicitly**: only a dedicated 45-minute break resets the continuous-driving counter — service time at a client does *not* count as a break. This is a conservative (safe) simplification; a real driver's 20-minute unload could sometimes legally count toward part of a split break, but treating it as a hard non-break avoids under-counting risk and keeps the simulation simple and auditable.

### 5.2 `clarke_wright.py` — route construction

Implements the classic **savings algorithm**:

1. Every client that isn't even feasible *alone* (depot → client → depot) is immediately excluded with the appropriate reason (checked via `simular_ruta` with a single-stop route) — no point trying to merge something that can't be served at all.
2. Every remaining client starts as its own single-stop route.
3. Savings `S(i,j) = d(depot,i) + d(depot,j) − d(i,j)` are computed for every pair (using real road distances from the OSRM matrix) and sorted descending.
4. Walking savings from highest to lowest, two routes are merged **only** if they can be joined at their depot-adjacent ends (the standard Clarke-Wright rule — you can never splice through the middle of an existing route), and only if the merged route re-simulates as feasible (capacity, time windows, driving limits — the exact same `simular_ruta` check). When both join orientations are feasible, **all** candidates are evaluated and the one with the lowest total distance wins — taking the first feasible candidate would silently accept the worse of two valid joins.
5. If more routes remain than vehicles available, the largest routes (by stop count) are kept and the rest are pushed to unassigned with `MOTIVO_FLOTA` — a dedicated code meaning "the fleet ran out", distinct from a genuine driving-time violation.

**Unlimited fleet mode.** Passing `num_vehiculos=None` means "as many vehicles as needed": step 5 keeps every constructed route and no client is ever dropped with `MOTIVO_FLOTA`. This is the convention of the standard VRPTW, where the vehicle count is the primary quantity to *minimise* rather than a given input — without it, benchmark comparison is impossible, because a bounded fleet silently discards customers that the reference results serve. The GUI keeps the bounded behaviour as its default and exposes the unlimited mode through a checkbox.

### 5.3 `two_opt.py` — local improvement

For each route Clarke-Wright produced, this tries **every possible 2-opt swap** (reversing a contiguous segment of stops), re-simulates the candidate with `simular_ruta`, and accepts it if it's still feasible **and** strictly shorter than the current best. It repeats this (first-improvement, one pass at a time) until no swap improves the route further — a standard local-search convergence loop. Because feasibility is re-checked on every candidate, 2-opt can never turn a legal route into an illegal one.

Route metrics are written back through `restricciones.actualizar_metricas_ruta`, a single shared helper also used by the reinsertion pass, so every phase updates a `Ruta` identically.

### 5.4 `reinsercion.py` — retrying the leftovers

After 2-opt has shortened the routes there may be slack that didn't exist during construction, so clients rejected back then deserve a second chance. `reinsertar_no_asignados` implements a **cheapest-insertion** pass:

1. Take the unassigned list and drop the entries whose reason is in `MOTIVOS_IRRECUPERABLES` (`GEOCODIFICACIÓN`, `CAPACIDAD`) — retrying those can never succeed, so probing every route position for them would be pure waste.
2. For each remaining candidate, try inserting it at **every position of every existing route**, validate each candidate route with `simular_ruta`, and keep the feasible insertion that adds the least distance.
3. Apply the winning insertion, then **repeat the whole sweep** — each successful insertion consumes slack and changes what else can fit, so a single pass would under-recover.
4. Stop when a full sweep places nobody.

It returns the updated routes, the still-unassigned clients (each keeping its original reason code), and the list of recovered nodes. `app.py` passes the recovered count to the results panel, which reports it as "*N* cliente(s) recuperado(s) tras la mejora local".

**The `habilitada` toggle.** Passing `habilitada=False` makes the function a no-op that returns the routes and unassigned list untouched. This exists so the phase's contribution can be measured in isolation: the benchmark runner solves every instance twice, once each way. It defaults to enabled and is deliberately *not* exposed in the GUI — for real dispatch there is no reason to decline free recovered customers.

### 5.5 `optimizador.py` — the shared entry point

`optimizar(...)` chains the three phases in order and returns a `ResultadoOptimizacion` carrying the routes, the unassigned clients, the recovered nodes, and two provenance flags (`reglamento_aplicado`, `reinsercion_aplicada`) that record how the run was configured.

It also exposes the aggregate metrics as computed properties, so nothing downstream re-derives them by hand: `num_vehiculos_utilizados`, `distancia_total_km`, `tiempo_total_programacion_min` (the sum of route durations — travel + waiting + service, plus breaks when regulations apply), `tiempo_espera_total_min`, `tiempo_conduccion_total_min`, and `clientes_servidos`.

`clientes_servidos` counts through `Ruta.clientes()`, the accessor that filters out the depot, rather than taking `len(ruta.paradas)` directly. The two agree today because `paradas` only ever holds customers, but the accessor states what is being measured and stays correct if a depot node ever ends up in the sequence. Since this figure feeds the experimental results tables directly, an off-by-one there would be silently misreported rather than caught.

This module has **no GUI dependency at all**, which is the point: the desktop app and the benchmark scripts run the exact same pipeline through it, so an experimental result cannot diverge from what a user would get for the same inputs. Both `aplicar_reglamento` and `usar_reinsercion` are parameters here.

---

## 6. External services — `utils/`

### 6.1 `osrm.py` — real road distances (replaces straight-line distance)

The whole point of this module: **before running the algorithm**, fetch a complete real-world distance/time matrix in a **single HTTP request**.

`obtener_matriz_distancias(nodos)` calls OSRM's `table` endpoint with every node's coordinates at once, gets back full NxN distance (meters) and duration (seconds) matrices, and repackages them into a `MatrizDistancias` object indexed by `(node_id, node_id)` pairs — `.distancia(a, b)` and `.tiempo(a, b)` are then simple O(1) lookups used everywhere inside `simular_ruta`, the savings calculation, and every 2-opt candidate check. The result is cached in memory keyed by the exact node set, so re-running the optimizer without changing the depot or client list costs zero extra network calls.

Two guardrails protect this call:
- **`MAX_NODOS_OSRM = 100`** — the public demo instance caps how many coordinates a `table` request may carry. The node count is checked *before* building the request, so exceeding it produces a clear Spanish message (split the client list, or self-host OSRM) instead of an opaque HTTP error from the server.
- **`MAX_ENTRADAS_CACHE = 10`** — each cached matrix holds O(n²) entries, so the cache evicts its oldest entry once full (relying on `dict` preserving insertion order) rather than growing without bound across a long session with many different files.

`obtener_geometria_ruta(nodos_en_orden)` is separate and only used for **drawing**: it asks OSRM's `route` endpoint for the actual road-following polyline of a finished route, so the map shows real street-following lines instead of straight segments. If this specific call fails, that one route just falls back to a straight line on the map (with a visible warning) — it never blocks the optimization itself, since the distances used for the actual math already came from the `table` call above.

Both raise `ErrorEnrutamiento` on network/HTTP/parsing failure, which the GUI turns into a clear error dialog rather than a crash.

### 6.2 `geocodificacion.py` — addresses → coordinates

`geocodificar_direccion(direccion)` queries Nominatim's `search` endpoint. Three things matter here for correctness and etiquette toward a free public service:
- **Disk cache** (`datos/geocache.json`, keyed by lower-cased address text): a successfully geocoded address is never looked up again, across app restarts.
- **Rate limiting**: a module-level timestamp enforces at least 1 second between actual outbound requests, per Nominatim's usage policy.
- **Identification**: a `User-Agent: Polux-TFM/1.0` header is sent on every request, also per policy.

Returns `(lat, lon)` on success, `None` if the address genuinely wasn't found (a normal, expected outcome — not an error), and raises `ErrorGeocodificacion` only for actual connectivity/service failures.

### 6.3 `distancia.py` — Haversine (kept for one narrow purpose)

Plain great-circle distance math. Used **only** by the pre-optimization estimate (§5.1) — deliberately not used anywhere in the real routing math anymore, since that was replaced by real OSRM distances. Kept around specifically because it's instant and needs no network, which matters for a summary panel that recalculates on every keystroke.

### 6.4 `google_maps.py` — driver navigation links

One pure function, `generar_enlace_google_maps(depot, paradas, incluir_regreso)`, builds:

```
https://www.google.com/maps/dir/?api=1&origin={depot}&destination={...}&waypoints={stop1}|{stop2}|...
```

The depot is always the origin. When the route includes the return leg the **depot is also the destination** and every customer becomes an ordered waypoint, so the driver's navigation covers the way back too; for an open route the destination is the last customer instead. This is the exact URL scheme Google Maps accepts to open a multi-stop driving itinerary directly, on desktop or mobile.

---

### 6.5 `cargador_solomon.py` — benchmark instances (no network at all)

Reads the standard Solomon VRPTW instance format: an instance name, a `VEHICLE` section (count + capacity), and a `CUSTOMER` table where row `0` is the depot. `cargar_instancia_solomon(ruta)` returns an `InstanciaSolomon` with the depot, the client list, and a ready-to-use distance matrix.

Four deliberate differences from the app's normal data path:

- **Coordinates are cartesian, not geographic.** `XCOORD`/`YCOORD` are stored verbatim in `Nodo.lat`/`Nodo.lon` as nominal values and **never geocoded**. The folium map is not meaningful for them.
- **Distances are Euclidean, and travel time equals distance numerically** — that is how Solomon defines the instances. `construir_matriz_euclidea` builds the full symmetric `MatrizDistancias` locally, so this path never touches OSRM or any network service. The parser and the matrix builder are pure functions over the file contents.
- **Times stay as raw numbers.** A `READY TIME` of `912` is kept as `912`, not reinterpreted as a clock time — these instances use consistent arbitrary units, and converting them would corrupt the comparison. The depot opens at instant `0`, which is why `simular_ruta` had to accept a departure time of `0`.
- **The depot's `hora_fin` is the total route duration constraint.** Row `0`'s `DUE DATE` (for example `1236` in `C101`) is not a delivery deadline but the planning horizon: every vehicle must be back at the depot by then, which is what bounds how long a single route may last. Polux enforces it through the same depot-closing check described in §5.1, which is precisely why that check must run with regulations disabled — in this mode it is the *only* thing limiting route duration, and dropping it would let the savings algorithm merge routes without bound and under-report the vehicle count.
- **The driving regulation does not apply.** These instances have no notion of a working day, so `APLICAR_REGLAMENTO_EN_SOLOMON = False` is exported as a named constant rather than a bare `False` at the call site — the intent is then visible in the code, in the benchmark runner's console banner, and in `ResultadoOptimizacion.reglamento_aplicado`, which records on the result object that regulations were not enforced.

`clase_de_instancia(nombre)` derives the Solomon class from the file name — `C1`/`C2` (clustered), `R1`/`R2` (random), `RC1`/`RC2` (mixed), where the digit distinguishes the narrow-window/short-horizon series 1 from the wide-window/long-horizon series 2. It checks the `RC` prefix before `R` and `C`, since otherwise every `RC*` instance would be misread as `R*`.

---

## 7. The GUI — `gui/`

Built entirely in Tkinter (`ttk` widgets), laid out as three columns in a `PanedWindow` inside `app.py`'s `VentanaPrincipal`.

### 7.1 `app.py` — orchestration

This is where every other piece gets wired together. The key methods, in the order a user would actually trigger them:

- **`_obtener_depot()`** builds the depot `Nodo` from whatever the config panel currently holds (including its resolved address text, so it can appear correctly in PDF exports).
- **`_al_cargar_csv(ruta_csv)`** — loads the CSV (showing `DialogoProgreso` if any geocoding is needed), stores the valid clients and any geocoding failures separately, refreshes the file-loaded label, enables the "Optimize" button, redraws the (pre-optimization) map, and refreshes the summary panel.
- **`_al_cambiar_configuracion()`** — recomputes and redraws the live pre-optimization summary any time weekly-hours or the extended-day checkbox changes.
- **`_al_optimizar()`** — the main event: re-validates config, refuses to proceed if today's driving ceiling is exhausted, fetches the OSRM matrix (with a busy cursor while that network call is in flight), delegates the three phases to `optimizador.optimizar` (the same entry point the benchmark runner uses), computes any "close to the limit" warnings per finished route, generates the results map (merging in any map-drawing warnings), and finally pushes everything — routes, all unassigned clients (algorithm-time *and* load-time geocoding failures, combined), warnings, the driver's name, the configured departure time, and the count of reinserted clients — into the results panel. The configured departure time is threaded into every phase, so all three share one consistent notion of when the day starts.

### 7.2 `panel_config.py` — left panel

Depot address (text field + "Buscar" button that geocodes it via Nominatim, with the resolved coordinates shown underneath in small text, or a clear "not found" message), vehicle count, a **"Flota ilimitada (modo evaluación)"** checkbox (unchecked by default, which greys out the vehicle-count field and makes `obtener_configuracion` return `num_vehiculos=None`), vehicle capacity, **departure time from the depot** (`HH:MM`, default `08:00`) side by side with the **"Hora límite de regreso"** (`HH:MM`, default `18:00`) — the two become the depot node's `hora_inicio` and `hora_fin` respectively, and `obtener_configuracion` rejects a limit that is not strictly later than the departure — hours already driven this week, an "allow extended 10h day" checkbox, a **"Contar el regreso al depósito"** checkbox (checked by default; unchecking it switches to open routes), an optional driver name field, the CSV-load button, and the "Optimize" button (disabled until clients are loaded). `obtener_configuracion()` is the single source of truth the rest of the app reads from — it raises a clear error if the depot address hasn't been resolved yet, and `_validar_hora_salida()` rejects a malformed or out-of-range departure time with an explanatory message rather than letting it reach the algorithm.

A known default (Plaça de l'Ajuntament, València, with its coordinates pre-filled) means the app works immediately after first launch without requiring a network round-trip before you can even look at the map.

### 7.3 `panel_resumen.py` — live pre-optimization summary

A thin, purely reactive display: weekly hours driven, computed daily ceiling, the configured working-day window (departure – return limit), number of clients loaded, the quick reachability estimate, and a warnings box. It has no logic of its own — every time something relevant changes, `app.py` recomputes a `ResumenPreOptimizacion` and calls `actualizar()` here.

### 7.4 `mapa.py` — the interactive map

Builds a `folium` map: the depot as a black home-icon marker; each route as a colored polyline (cycling through a 10-color palette) using **real road geometry** when available, with numbered markers per stop whose popups show name, vehicle, visit order, time window, estimated arrival, demand, and service time; and any unassigned client as a red warning-triangle marker (skipped gracefully if it has no coordinates at all — a geocoding-failure case). `generar_mapa_vacio` produces a lighter "not optimized yet" version showing just the depot and raw client list, shown right after a CSV loads and before you click Optimize.

### 7.5 `panel_resultados.py` — results and every export

The busiest panel. Shows total distance, vehicle count and **total waiting time**, a sortable-by-selection route table (stop count, distance, total time, driving time, **waiting time**, breaks) with a detail view for whichever route you click, the unassigned-clients table (client, reason code, detail), and a Regulation-561 warnings box — which also carries a notice when the run used unlimited-fleet evaluation mode. Below that, the driver-facing exports:

It also shows a **"Reinserción"** line reporting how many clients the reinsertion pass recovered.

- One **"Abrir Ruta N en Google Maps"** button per route — builds the link (§6.4), copies it to the clipboard, and opens it in the system browser.
- **"Hojas de ruta (PDF)..."** — opens the preview dialog (§7.7). Saving and printing happen from inside that dialog, so nothing is written to disk until the user has actually looked at the sheets.
- **"Exportar resultados (CSV)"** — one row per route stop plus one row per unassigned client, all in a single flat file with a `tipo` column distinguishing the two, including each route's `tiempo_espera_min`. The `motivo` column carries whatever reason code applies, `FLOTA` included.
- **"Exportar mapa (HTML)"** — regenerates the current results map as a standalone file anywhere you choose.

### 7.6 `pdf_rutas.py` — printable route sheets

For each route, builds an A4 PDF via `reportlab`'s `platypus` layer: a header (date, route number, vehicle + capacity, driver name, **departure time and return limit** — the latter shown as "— (ruta abierta)" when the route does not return, depot address/coordinates), a summary block, the itinerary table, the global unassigned-clients list with reasons (repeated on every route's sheet, since those clients aren't tied to any one route), and a footer crediting Polux and citing Regulation 561/2006.

The **summary block** carries six metrics — stop count, total distance, departure time, **driving time**, waiting time and total estimated time — laid out as two label/value bands of three columns each rather than one very wide row: six headings do not fit on a single line without colliding.

The **itinerary table** (order, client, address — real text if it came from a `direccion`, coordinates otherwise, ETA, demand, service time, and a blank "Observaciones" column for handwritten notes) is not just the customer list. Two other kinds of row are interleaved into it:

- **`PAUSA OBLIGATORIA`** rows, shaded amber, inserted at the right point in the sequence from `ruta.pausas` — showing when the rest starts, how long it lasts, and which leg it falls inside (e.g. "Durante el trayecto Barcelona → Tarragona"). Without these the sheet only told the driver *how many* breaks the plan assumed, not where to take them, which is unusable for a mid-leg break on a four-hour motorway stretch.
- A closing row that is either **`REGRESO AL DEPÓSITO`** with the estimated arrival time, or **`FIN DE JORNADA`** noting that the route is open and does not return — driven by `ruta.incluye_regreso`. Filenames follow `Ruta_{vehiculo_id}_{fecha}.pdf` (`nombre_archivo_ruta` is the single place that naming rule lives).

The layout is defined exactly once, in `_generar_pdf_de_ruta`, whose `destino` argument accepts **either a file path or a binary buffer** — `SimpleDocTemplate` handles both. Two thin public wrappers sit on top:
- `generar_hojas_de_ruta_pdf(...)` — writes one file per route into a folder (used when saving).
- `generar_hoja_de_ruta_en_memoria(...)` — returns a single route's PDF as `bytes` (used for the preview).

That split is what keeps the preview honest: what you see rasterized on screen is produced by the same layout code as the file you save, so the two cannot drift apart.

### 7.7 `dialogo_previsualizacion.py` — preview, save, print

A modal window that generates every route sheet in memory, rasterizes all their pages, and lets the user page through them before committing anything: previous/next navigation, a counter reading `Ruta 2 de 4 — página 1 de 1`, **"Guardar PDF"** (asks for a folder and writes the files), **"Imprimir"** (writes the PDFs to temp files and hands them to the system's default printer — `lpr` on macOS/Linux, `os.startfile(path, "print")` on Windows, with per-route error reporting), and **"Cerrar"**.

**Rendering choice and its tradeoff.** Pages are rasterized with **PyMuPDF**. The two alternatives were both rejected:
- `pypdf` + `pdf2image` — `pdf2image` wraps the Poppler command-line utilities, so it needs Poppler installed at OS level (`brew install poppler`, `apt install poppler-utils`, separate binaries on Windows). That breaks plain `pip install -r requirements.txt`, which is a practical requirement here.
- `reportlab.graphics.renderPM` — only rasterizes `reportlab.graphics` `Drawing` objects, **not** `platypus` documents like these route sheets. Using it would have meant maintaining a second, parallel layout purely for the preview, which could silently diverge from the real PDF.

PyMuPDF ships as a binary wheel from PyPI (no system dependency) and rasterizes the exact PDF that gets saved. The tradeoff accepted in exchange is one more Python dependency, and PyMuPDF's AGPL/commercial licensing — fine for an academic project, but worth revisiting for closed-source redistribution.

One Tk detail worth knowing: `tk.PhotoImage` can only downscale by whole-number factors, so the code picks the smallest integer `subsample` factor that fits the page within `ANCHO_MAXIMO_VISTA`. A reference to each image is also kept on the label, because Tk does not hold one itself and the image would otherwise be garbage-collected mid-display.

### 7.8 `dialogo_progreso.py` — the one reusable widget

A small modal `Toplevel` with a progress bar that starts indeterminate (spinning, since we don't yet know how many addresses need geocoding) and switches to determinate once the real count is known — used exclusively during CSV loading when addresses need to be resolved.

---

## 8. A complete run, end to end

1. App launches with a working default depot (Valencia city center) already resolved — no network call needed yet.
2. User optionally changes the depot address and clicks "Buscar" → one Nominatim call, coordinates shown.
3. User sets vehicle count, capacity, departure time, hours driven this week, extended-day flag, and (optionally) their name.
4. User clicks "Cargar clientes (CSV)" → `cargador.py` validates the file; any address-only rows get geocoded one by one (rate-limited, cached, with a progress dialog); the map redraws with the depot + all loaded clients; the summary panel shows the computed daily ceiling, the departure time and a rough reachability estimate.
5. User clicks "Optimizar rutas" → the app blocks if the ceiling is `0`; otherwise it fetches the full OSRM distance/time matrix in one call (refusing early if the client list exceeds the 100-coordinate cap), runs Clarke-Wright to build initial routes, 2-opt to shorten each one, then the reinsertion pass to retry earlier rejects — every candidate route along the way is checked against capacity, time windows, and the 561/2006 driving/break rules via `simular_ruta`.
6. Results appear: the map now shows real street-following colored routes plus any unassigned clients in red; the results panel shows per-route metrics, how many clients reinsertion recovered, unassigned clients with reason codes, and any "close to the driving limit" warnings.
7. User exports whatever they need: a Google Maps link per driver, the PDF route sheets (previewed on screen first, then saved or printed), or CSV/HTML for the office.

---

## 9. Key design decisions (useful for the thesis discussion section)

- **Two distinct distance sources, deliberately**: Haversine (instant, offline) for the live pre-optimization estimate; real OSRM road distances (one network call, cached) for the actual algorithm and final metrics. This avoids hammering a public API on every keystroke while still making sure what actually gets optimized reflects real streets.
- **A single feasibility function (`simular_ruta`) used everywhere** — Clarke-Wright's merge check, 2-opt's swap check, and the final reported metrics all call the exact same simulation. This guarantees the numbers shown in the UI are never inconsistent with what the algorithm actually enforced.
- **Soft vs. hard failures are handled differently on purpose**: a malformed CSV row is a hard error (aborts the load, since the file itself is broken); a single unreachable address is a soft failure (that one client becomes "unassigned", everything else still loads); a genuine network outage (OSRM or Nominatim unreachable) is a hard error surfaced as a clear dialog, since silently falling back to worse data would be misleading for a system whose whole point is regulatory compliance.
- **Address text is preserved even when coordinates take priority** — so a CSV row can supply both, use the coordinates for positioning (a fix applied after an earlier bug), and still show the real address on the printed route sheet instead of raw numbers.
- **Only one dedicated break type is modeled** (45 continuous minutes), not the split-break variants the real regulation also allows — a conservative simplification that's easy to defend and easy to audit.
- **Breaks can fall mid-leg, not just at stops.** Tying breaks to client stops would have been simpler, but it silently permits an arbitrarily long single leg with no rest — a real 561/2006 violation on interurban routes. Consuming each leg in chunks costs a small loop and removes that whole class of false "feasible" result.
- **Reason codes distinguish *why* a client was dropped**, including a dedicated `FLOTA` for fleet exhaustion. This matters operationally: `TIEMPO` tells a planner the day is legally full, whereas `FLOTA` tells them to add a vehicle — conflating the two hides the cheaper fix.
- **Recovery is a separate third phase**, not folded into construction. Keeping cheapest-insertion after 2-opt means it operates on already-shortened routes (where the slack actually exists) and leaves the classic Clarke-Wright construction phase textbook-faithful and easy to describe.
- **Preview before writing files.** Route sheets are generated in memory and shown on screen first; nothing touches disk or a printer until the user confirms. The same layout function serves both paths, so the preview cannot drift from the artifact.
- **One pipeline, two audiences.** The GUI and the benchmark runner both go through `optimizador.optimizar`. Had the orchestration stayed inline in the Tkinter callback, the experimental results would have been produced by a second, parallel code path — and any divergence between them would invalidate the validation chapter.
- **Evaluation-mode differences are flags, not forks.** Unlimited fleet (`num_vehiculos=None`), disabled regulations (`aplicar_reglamento=False`) and the reinsertion toggle are parameters on the shared pipeline rather than a separate benchmark implementation. The result object records which were used (`reglamento_aplicado`, `reinsercion_aplicada`), so a set of numbers always carries its own provenance.
- **Reason codes are constants, never literals.** Comparing against `"CAPACIDAD"` in one place and `MOTIVO_CAPACIDAD` in another is how reason codes quietly drift apart; the constants in `datos/modelos.py` are the single source of truth, and the accented `GEOCODIFICACIÓN` in particular is exactly the kind of value that must never be retyped by hand.

---

## 10. Benchmark runner — `scripts/ejecutar_benchmark.py`

A headless script for the experimental validation chapter. Given a directory of Solomon instance files it:

1. Loads each instance with `cargar_instancia_solomon` (no network).
2. Solves each one in **evaluation mode** — unlimited fleet (`num_vehiculos=None`) and regulations disabled (`aplicar_reglamento=False`) — printing that fact as a banner so a run's provenance is never ambiguous.
3. Solves each instance **twice**, with `usar_reinsercion=True` and `False`, to isolate what the reinsertion phase contributes.
4. Times each solve with `time.perf_counter()`.
5. Writes a CSV and prints a per-class summary of averages.

**CSV schema** (`COLUMNAS_RESULTADOS`), in this exact order:

| Column | Meaning |
| --- | --- |
| `instancia` | Instance name as declared in the file (e.g. `C101`) |
| `clase` | Solomon class: `C1`, `C2`, `R1`, `R2`, `RC1`, `RC2` |
| `reinsercion` | `sí` / `no` — whether phase 3 ran |
| `num_vehiculos` | Vehicles used (non-empty routes) |
| `tiempo_total_programacion` | Total schedule time across all routes |
| `distancia_total` | Total distance across all routes |
| `tiempo_espera_total` | Total waiting time across all routes |
| `clientes_servidos` | Customers placed on a route |
| `clientes_no_asignados` | Customers left unassigned |
| `tiempo_computo_segundos` | Wall-clock solve time |

The column order is not cosmetic: results in this field are ranked **lexicographically** by vehicle count first, then total schedule time, then total distance, then waiting time, so the CSV reads left-to-right in decreasing order of precedence.

Usage:

```bash
python3 scripts/ejecutar_benchmark.py ruta/a/instancias -s resultados.csv
```

Instance files that fail to parse are reported as `[OMITIDA]` and skipped rather than aborting the whole sweep — one malformed file in a directory of 56 should not cost the entire run.

---

## 11. Tests — `tests/`

A `pytest` suite that runs **without network access**: instead of calling OSRM, the tests build `MatrizDistancias` objects by hand (`tests/conftest.py`) with exact, known travel times. That's what makes it possible to assert on regulatory limits precisely — a leg is *exactly* six hours, so the expected number of breaks is arithmetic, not an approximation.

Run from the project root:

```bash
python3 -m pytest tests/ -v
```

Coverage by file:
- **`test_regreso_y_pausas.py`** — the maximum end-of-day time: a route returning after the limit rejected with `MOTIVO_VENTANA` and `nodo_conflicto=None`, the same route accepted under a later limit, accepted regardless when `incluir_regreso=False`, still enforced with regulations disabled, a long-wait route exhausting the day on only one hour of driving, and the rejection detail naming the working day plus both times (and reaching the unassigned client without mentioning a customer window); the return leg costing exactly the last edge when enabled and nothing when not; driving time halving on an out-and-back; a route infeasible with the return becoming feasible without it; the depot's closing time only being checked when there is a return; the flag propagating to every `Ruta` and to the result object; the Google Maps destination switching between depot and last customer; and for breaks: `len(pausas) == numero_pausas`, a mid-first-leg break being tagged `indice_parada_previa=0` with the exact start instant and leg, a later break being tagged after the correct customer, no breaks recorded when regulations are off, and the break detail surviving 2-opt and reinsertion.
- **`test_tiempo_espera.py`** — waiting time is zero when every arrival falls inside its window, positive (and numerically exact) when an arrival is early, accumulates across several stops, is included in the route's total time, aggregates correctly across routes, survives the later phases rewriting route metrics; plus the reinsertion toggle defaulting to enabled and recovering nobody when disabled.
- **`test_solomon.py`** — the parser on a hand-written instance (header, depot as customer 0, client fields, raw time values preserved, no geocoding, error cases); class derivation including `RC*` not being misread as `R*`; the Euclidean matrix being symmetric, having travel time equal to distance, and zero on the diagonal; evaluation mode inserting no breaks and reporting `reglamento_aplicado=False`; departure time `0` being valid; the depot horizon being respected; and unlimited fleet never producing `MOTIVO_FLOTA` (against a control case that does produce it when bounded).
- **`test_restricciones.py`** — the daily-ceiling formula (returns `0` at/above 56 weekly hours, caps at 9h normally and 10h extended, weekly remainder winning when it's smaller); mandatory-break behaviour, including a 6-hour leg producing at least one break, a 12-hour leg producing several, an exact parametrized break count per leg duration (the regression that pins the mid-leg fix), and a reproduction check that continuous driving never exceeds 4.5h; rejection with `MOTIVO_VENTANA` for an unreachable window and `MOTIVO_CAPACIDAD` for excess demand; early arrival waiting for the window to open; and the configurable departure time shifting arrival times.
- **`test_algoritmo.py`** — fleet shortage reported as `MOTIVO_FLOTA`; over-capacity clients reported as `MOTIVO_CAPACIDAD`; all feasible clients assigned when vehicles suffice; 2-opt never increasing distance and never returning an infeasible route; reinsertion skipping irrecoverable reasons, recovering a client when slack exists, choosing the *cheapest* insertion among several routes, and leaving all routes feasible afterwards.
- **`test_osrm_limites.py`** — the 100-coordinate cap raising `ErrorEnrutamiento` before any network call, the exact limit not being rejected for size, and the cache staying bounded while evicting oldest-first.

Note on scenario design: because the savings loop merges any *feasible* pair regardless of whether the saving is positive, constructing a genuine "fleet ran out" scenario requires making pairs infeasible (e.g. via the daily ceiling) rather than merely unattractive — see the comments in `test_falta_de_vehiculos_se_reporta_como_flota`.

---

## 12. Known limitations / possible future work

- OSRM and Nominatim here point at the **public demo instances**, which have no uptime/rate guarantee — fine for a thesis demo, not for production dispatch. The OSRM matrix is additionally capped at 100 coordinates by that instance, so larger client lists need a self-hosted OSRM.
- The Clarke-Wright merge direction assumes near-symmetric costs; real one-way streets can make `d(i,j) ≠ d(j,i)`, which the savings formula doesn't fully account for (a documented, standard simplification for this class of algorithm).
- **The savings loop does not filter on the sign of the saving.** Classic Clarke-Wright only merges pairs with a *positive* saving; here any feasible merge is accepted, which can lengthen total distance when vehicles are plentiful (it does, however, serve more clients when they are scarce). Restricting merges to positive savings — or making it a user choice between "minimum distance" and "maximum coverage" — would be a well-scoped improvement.
- The "Observaciones" column on PDF route sheets is intentionally left blank for drivers to annotate by hand.
- Mandatory breaks are shown in the itinerary at the point of the sequence where they fall, but the sheet does not name a *place* to stop: for a mid-leg break it says which leg the rest belongs to, not which service area. Resolving that would need a rest-area dataset along the road geometry.
- Vehicles are homogeneous (one capacity value for the whole fleet); a heterogeneous fleet would require extending `Vehiculo` and the vehicle-count logic in `clarke_wright.py`.
- The reinsertion pass only inserts into *existing* routes; it never opens a new route even when a vehicle is idle, and it does not attempt pairwise swaps between routes (a `relocate`/`exchange` neighbourhood would recover more).
- Printing shells out to `lpr` / `os.startfile`; there is no printer selection, page range, or copy count — it always targets the system default printer.
- **The benchmark comparison is not yet apples-to-apples with the literature.** Reference results for Solomon instances come from metaheuristics that explore far beyond a single greedy construction plus 2-opt, so Polux's vehicle counts and distances should be read as a baseline, not as competitive figures. Reporting the gap to best-known values per instance would make the validation chapter stronger.
- The Solomon instances are solved with the same `2-opt`-only improvement used in production mode; classic VRPTW neighbourhoods (`relocate`, `exchange`, `Or-opt`) are not implemented, which is the main reason for that gap.
- Unlimited fleet mode is available in the GUI, but the Solomon loader is not — instances can only be run through the benchmark script. Wiring the loader into the GUI would need a different map view, since the coordinates are cartesian rather than geographic.
- The waiting-time metric counts idle time at customers only. Time spent waiting at the depot before departure is not modelled, since the vehicle simply leaves at the configured hour.
