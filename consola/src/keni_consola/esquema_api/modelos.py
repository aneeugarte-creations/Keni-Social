"""Modelos (`TypedDict`) del subconjunto estable del contrato `/api/*`.

Cada `TypedDict` describe la forma EXACTA del JSON que emite el handler asociado
(verificado contra el handler y sus tests). Son solo tipos: no se instancian ni
validan en runtime; existen para derivar el TypeScript del frontend y para que el
guard detecte divergencias. Ver el docstring del paquete.

Convencion de campos OPCIONALES: se modelan con `NotRequired[...]` (clave que
puede no venir). Convencion de NULABLES: `X | None` (la clave viene pero su valor
puede ser `null`). Las dos cosas son distintas y se respetan tal cual en el TS.

El orden de `MODELOS` (abajo) fija el orden en que aparecen las interfaces en el
`types.gen.ts`, para que la generacion sea estable y el diff sea minimo.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# --------------------------------------------------------------------------- #
# Estado (autodiagnostico del sistema) — api/estado.py                         #
# --------------------------------------------------------------------------- #

NivelEstado = Literal["ok", "aviso", "error"]


class ResultadoEstado(TypedDict):
    estado: NivelEstado
    nombre: str
    detalle: str
    icono: str


class RespuestaEstado(TypedDict):
    resultados: list[ResultadoEstado]
    resumen: str
    siguiente_paso: str


# --------------------------------------------------------------------------- #
# Configuracion — api/config.py                                                #
# --------------------------------------------------------------------------- #


class MarcaDisponible(TypedDict):
    id: str
    nombre: str


class CredencialesPresentes(TypedDict):
    meta: bool
    youtube: bool
    x: bool
    tiktok: bool


class RespuestaConfig(TypedDict):
    fuente: str
    fuentes_validas: list[str]
    marcas: list[str]
    marcas_disponibles: list[MarcaDisponible]
    credenciales_presentes: CredencialesPresentes


class CuerpoGuardarConfig(TypedDict):
    fuente: str
    marcas: list[str]


# --------------------------------------------------------------------------- #
# Limites de caracteres por red — api/limites.py / limites_plataforma.py       #
# --------------------------------------------------------------------------- #


class LimiteRed(TypedDict):
    """Limite de caracteres canonico de una red (fuente unica, `GET /api/limites`).

    `limite` es `null` si la red no tiene tope tecnico practico (Facebook/YouTube).
    """

    id: str
    nombre: str
    limite: int | None


class RespuestaLimites(TypedDict):
    """Respuesta de `GET /api/limites`: los limites por red, en orden fijo."""

    limites: list[LimiteRed]


# --------------------------------------------------------------------------- #
# Metricas — api/metricas.py                                                   #
# --------------------------------------------------------------------------- #


class RangoMetrica(TypedDict):
    id: str
    etiqueta: str


class OpcionesMetricas(TypedDict):
    marcas: list[MarcaDisponible]
    rangos: list[RangoMetrica]


class TotalMetricas(TypedDict):
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class CuentaMetrica(TypedDict):
    marca_id: str
    marca: str
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class RedMetrica(TypedDict):
    """Una red (plataforma) del reporte con sus métricas agregadas entre marcas.

    Agrega el `por_plataforma` de TODAS las cuentas del reporte por plataforma. `red`
    es el id de plataforma (el frontend lo traduce a nombre). `alcance` es `null` si
    NINGUNA cuenta mide esa red (#138: no se inventa un 0).
    """

    red: str
    visualizaciones: int
    # alcance: None = ninguna cuenta mide alcance en esta red (no es 0 real).
    alcance: int | None
    interacciones: int
    engagement_pct: float


class RedCobertura(TypedDict):
    """Estado de UNA red social para una marca en el rango (auditoría de cobertura).

    Responde a la pregunta "¿por qué esta red no muestra datos?" sin esconder las
    redes vacías. `estado` ∈ {"con_datos", "sin_metricas", "sin_lectura",
    "no_configurada", "sin_credenciales", "presupuesto_agotado"}:

      - con_datos:        respondió con métricas en el rango.
      - sin_metricas:     conectada, pero sin actividad/métricas en el periodo.
      - sin_lectura:      no se pudo leer (red no conectada en Metricool o métrica
                          no disponible en el plan / error de la API).
      - no_configurada:   la marca no tiene esta red dada de alta en Metricool.
      - sin_credenciales / presupuesto_agotado: motivos de omisión heredados.

    Las métricas son `null` cuando la red NO respondió (no se inventa un 0 falso);
    `motivo` es el texto legible que la UI muestra como explicación.
    """

    red: str
    estado: str
    visualizaciones: int | None
    alcance: int | None
    interacciones: int | None
    engagement_pct: float | None
    motivo: str | None


class MarcaCobertura(TypedDict):
    """Cobertura de TODAS las redes auditables de una marca (auditoría por marca).

    `redes` lista SIEMPRE el universo completo de redes sociales medibles (aunque no
    tengan datos), cada una con su `estado` y `motivo`, para que el operador vea de un
    vistazo qué falta y por qué.
    """

    marca_id: str
    marca: str
    redes: list[RedCobertura]


class ReporteMetricas(TypedDict):
    """Respuesta de `GET /api/metricas/reporte`."""

    rango: str
    etiqueta_rango: str
    marca: str
    # Procedencia: "muestra" (ficticios) o el nombre de la fuente real (p. ej.
    # "meta"). La UI pinta un badge de advertencia con esto.
    fuente: str
    total: TotalMetricas
    cuentas: list[CuentaMetrica]
    # Las métricas agregadas POR RED (suma de todas las marcas del reporte por
    # plataforma). Acotada a la marca seleccionada cuando el filtro está activo.
    por_red: list[RedMetrica]
    # Auditoría de cobertura: por cada marca del reporte, TODAS las redes auditables
    # con su estado (con datos / sin métricas / sin lectura / no configurada) y el
    # motivo legible. Hace visibles las redes vacías en vez de ocultarlas.
    cobertura_redes: list[MarcaCobertura]
    # Cuándo se calculó este reporte (ISO). La UI lo muestra como "Actualizado hace X".
    # Sale de la cache de métricas (refresco en 2º plano + botón Actualizar).
    generado_en: str


class ComparativaMetrica(TypedDict):
    metrica: str
    a: float
    b: float
    diferencia: float
    variacion_pct: float


class ComparativaPorMarca(TypedDict):
    marca_id: str
    marca: str
    comparativa: list[ComparativaMetrica]


class TotalComparativa(TypedDict):
    metricas: list[ComparativaMetrica]


class CompararMetricas(TypedDict):
    """Respuesta de `GET /api/metricas/comparar`: comparativa A vs B."""

    marca: str
    rango_a: str
    rango_b: str
    etiqueta_a: str
    etiqueta_b: str
    # Procedencia de los datos comparados ("muestra" = ficticios; "muestra" si
    # cualquiera de los dos reportes lo es).
    fuente: str
    total: TotalComparativa
    por_marca: list[ComparativaPorMarca]
    # La más antigua de las dos lecturas comparadas (ISO): la comparativa es tan
    # fresca como su dato más viejo.
    generado_en: str


class PiezaAnalisis(TypedDict):
    """Pieza que explica un movimiento (o que apuntala el siguiente paso)."""

    titulo: str
    plataforma: str
    engagement_pct: float
    # url: puede no existir según la fuente/plataforma.
    url: str | None


class MovimientoAnalisis(TypedDict):
    """Un movimiento del periodo: qué se movió y la pieza que lo explica."""

    marca_id: str
    marca: str
    variacion_vis_pct: float
    # direccion: "sube" | "baja" | "estable" (se deriva del signo de la variación).
    direccion: str
    visualizaciones: int
    # engagement_pct: None si no es comparable entre plataformas (#138).
    engagement_pct: float | None
    # pieza: None si la marca no tiene piezas que destacar.
    pieza: PiezaAnalisis | None


class SiguientePasoAnalisis(TypedDict):
    """Sugerencia accionable que cierra el loop a la acción (UX-roadmap #11)."""

    marca_id: str
    marca: str
    engagement_pct: float | None
    pieza: PiezaAnalisis | None
    texto: str


class AnalisisDiario(TypedDict):
    """Respuesta de `GET /api/metricas/analisis`: lectura "qué cambió y por qué".

    Capa narrativa (F6/#146) sobre las métricas: top movimientos con la(s) pieza(s)
    que los explican y un siguiente paso. `es_muestra`/`fuente` marcan cuando los
    datos son de muestra y no reales (issue #131).
    """

    rango: str
    etiqueta_rango: str
    marca: str
    # Procedencia: "muestra" (ficticios) o nombre de la fuente real.
    fuente: str
    es_muestra: bool
    movimientos: list[MovimientoAnalisis]
    movimientos_resto: int
    marcas_estables: int
    # Marcas con cobertura parcial (nombres resueltos); la lectura puede estar
    # incompleta. Vacío = cobertura completa.
    cobertura_parcial: list[str]
    # siguiente_paso: None si no hay una marca líder clara a la que apuntar.
    siguiente_paso: SiguientePasoAnalisis | None
    # Cuándo se calculó este análisis (ISO). Igual que en ReporteMetricas: la UI lo
    # muestra como "Actualizado hace X".
    generado_en: str


class EstadoMetricas(TypedDict):
    """Respuesta de `GET /api/metricas/estado` y `POST /api/metricas/refrescar`.

    Estado del refresco de la cache de métricas (en 2º plano) + "última actualización"
    del combo consultado. La UI lo usa para el botón Actualizar (spinner mientras
    `corriendo`) y para el polling (deja de pollear cuando `corriendo` pasa a false).
    """

    # corriendo: hay un refresco en curso (no se arranca otro hasta que termine).
    corriendo: bool
    # iniciado_en / terminado_en: ISO del último refresco (o "" si no aplica todavía).
    iniciado_en: str
    terminado_en: str
    # ultimo_error: mensaje del último fallo de barrido, "" si fue bien.
    ultimo_error: str
    # generado_en: ISO de la última actualización del combo `?rango=&marca=` consultado
    # ("" si ese combo aún no está en cache).
    generado_en: str


class PeriodoMetricas(TypedDict):
    """Ventana de fechas (ISO) de un periodo de métricas."""

    desde: str
    hasta: str


class EstadisticasNumericas(TypedDict):
    """Resumen estadístico de una serie (engagement o visualizaciones por pieza).

    Todos los campos salvo `n` son `null` cuando no hay datos suficientes (la
    desviación necesita n>=2): la UI distingue "0" de "sin dato".
    """

    n: int
    media: float | None
    mediana: float | None
    p25: float | None
    p75: float | None
    minimo: float | None
    maximo: float | None
    desviacion: float | None


class PiezaMetrica(TypedDict):
    """Una pieza/video del periodo (fila de top/peores).

    El servicio de métricas serializa cada `Pieza` con el desglose GRANULAR (likes,
    comentarios, compartidos, guardados, video_views, tiempo medio de visualización,
    clics de enlace) además del agregado. Esos campos son `null` cuando la fuente no
    los expone para esa pieza (no se inventa un 0): la UI distingue "0" de "sin dato".
    `formato`/`cuenta` y `rendimiento_relativo` (vs la media de su grupo) también vienen
    del servicio; `null` cuando no aplican.
    """

    id: str
    plataforma: str
    titulo: str
    # publicado: fecha ISO (AAAA-MM-DD).
    publicado: str
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    # url: puede no existir según la fuente/plataforma.
    url: str | None
    # Desglose granular por pieza; null cuando la fuente no lo expone (no se inventa 0).
    likes: int | None
    comentarios: int | None
    compartidos: int | None
    guardados: int | None
    video_views: int | None
    tiempo_medio_vis_s: int | None
    clics_enlace: int | None
    # formato (reel/post/short…) y cuenta (id_metricas) de la pieza; null si no aplican.
    formato: str | None
    cuenta: str | None
    # rendimiento_relativo: engagement de la pieza frente a la media de su grupo; null si
    # no es comparable (grupo de 1, métrica n/d).
    rendimiento_relativo: float | None


class DistribucionBucket(TypedDict):
    """Un tramo del histograma de engagement (cuántas piezas caen en [inicio, fin))."""

    etiqueta: str
    inicio: float
    # fin: null = tramo abierto superior ("10%+").
    fin: float | None
    n: int


class AnaliticaPiezas(TypedDict):
    """Respuesta de `GET /api/metricas/piezas`: estadísticas + top/peores + distribución.

    `cuenta` es `null` cuando agrega todas las marcas (tab "Todas"). Coste 0 de API:
    se construye sobre las piezas que el reporte ya descarga del periodo.
    """

    # cuenta: id_metricas de la marca, o null = todas.
    cuenta: str | None
    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    total: int
    fuente: str
    engagement: EstadisticasNumericas
    visualizaciones: EstadisticasNumericas
    top: list[PiezaMetrica]
    peores: list[PiezaMetrica]
    distribucion: list[DistribucionBucket]
    generado_en: str


class PuntoSerie(TypedDict):
    """Un día de la serie temporal: totales del día."""

    # fecha: ISO (AAAA-MM-DD).
    fecha: str
    visualizaciones: int
    interacciones: int


class TendenciaDiaria(TypedDict):
    """Respuesta de `GET /api/metricas/tendencia`: evolución diaria del periodo.

    `puntos` vacío = la fuente activa no expone serie diaria (degradación honesta).
    """

    # cuenta: id_metricas de la marca, o null = todas.
    cuenta: str | None
    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    fuente: str
    puntos: list[PuntoSerie]
    generado_en: str


class PiezaRendimiento(TypedDict):
    """Una pieza YA PUBLICADA del tablero con su rendimiento REAL (drill-down marca->pieza).

    A diferencia de `PiezaMetrica` (mejores/peores del periodo descubiertas desde la
    lista de posts), esto es el rendimiento de una pieza CONCRETA que el equipo publicó
    desde la Consola, leído de Metricool por su `id_post_metricool`. `contenido_id` enlaza
    a la pieza en el tablero (`/parrilla/pendientes`). `encontrado=False` => Metricool aún
    no tiene datos (recién publicada): la UI muestra "sin datos todavía", no ceros falsos.
    """

    # contenido_id: id del item del tablero, para enlazar a la pieza en /parrilla/pendientes.
    contenido_id: str
    plataforma_id: str
    titulo: str
    # marca: id de marca de la Consola; marca_nombre: etiqueta legible.
    marca: str
    marca_nombre: str
    red: str
    id_post_metricool: str
    encontrado: bool
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    url: str | None
    # publicado: fecha ISO (AAAA-MM-DD) o null si la fuente no la conoce todavía.
    publicado: str | None
    fuente: str
    generado_en: str


class PiezasRendimiento(TypedDict):
    """Respuesta de `GET /api/metricas/piezas-rendimiento`: drill-down marca -> pieza.

    Lista las piezas publicadas (con `id_post_metricool`) y su rendimiento REAL, leído de
    la MISMA fuente única (Metricool) que el dashboard y las tarjetas del tablero, sin
    desfase. Ordenadas por engagement desc (las "sin datos" al final).
    """

    # marca: id_metricas con el que se acotó (igual que el resto de Analíticas), o "".
    marca: str
    # fuente: "muestra" si alguna pieza viene de muestra; si no, la fuente real o "desconocida".
    fuente: str
    total: int
    piezas: list[PiezaRendimiento]


class PiezaListado(TypedDict):
    """Una pieza del listado COMPLETO del periodo (tabla "Todas las piezas").

    Misma forma que `PiezaMetrica` (granulares incluidos) MÁS `linea`: el nombre de la
    LÍNEA editorial (etiqueta clase `vertical`) a la que pertenece la pieza, resuelto
    cruzándola con su contenido de la Consola. `linea` es `null` cuando la pieza no tiene
    línea atribuible (la mayoría de piezas que no nacieron en la Consola): la UI muestra
    "Sin línea". Se separa de `PiezaMetrica` para no forzar `linea` en top/peores.
    """

    id: str
    plataforma: str
    titulo: str
    publicado: str
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    url: str | None
    likes: int | None
    comentarios: int | None
    compartidos: int | None
    guardados: int | None
    video_views: int | None
    tiempo_medio_vis_s: int | None
    clics_enlace: int | None
    formato: str | None
    cuenta: str | None
    rendimiento_relativo: float | None
    # linea: nombre de la línea editorial de la pieza; null si no es atribuible.
    linea: str | None


class PiezasListado(TypedDict):
    """Respuesta de `GET /api/metricas/piezas-listado`: listado COMPLETO de piezas del periodo.

    TODAS las piezas de la(s) cuenta(s) del periodo tal como las emite la fuente única
    (`servicio.construir_listado_piezas`), no solo top/peores. Cada `PiezaListado` trae
    su `id` (de Metricool), granulares, url y su `linea` editorial. Es el insumo de la
    tabla "Todas las piezas del periodo" (filtros + orden + paginación por día + detalle
    por pieza). Coste 0 de API: reúsa lo que el dashboard ya descarga.
    """

    rango: str
    etiqueta_rango: str
    # marca: id_metricas con el que se acotó, o "".
    marca: str
    periodo: PeriodoMetricas
    fuente: str
    piezas: list[PiezaListado]
    total: int
    generado_en: str


class PuntoHistorico(TypedDict):
    """Un snapshot acumulado de UNA pieza en el histórico (ADR 0007).

    El daemon de refresco escribe un punto por pieza seguida cada N horas. Todas las
    métricas son los valores ACUMULADOS en ese instante (`ts`, ISO). Las granulares
    valen 0 cuando la fuente no las trajo en ese snapshot (no se distingue de un 0 real
    en la serie persistida; la honestidad está a nivel de pieza: si no se sigue, no hay
    puntos).
    """

    # ts: instante del snapshot (ISO).
    ts: str
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    alcance: int
    likes: int
    comentarios: int
    compartidos: int
    guardados: int
    video_views: int
    tiempo_medio_vis_s: int
    clics_enlace: int


class VelocidadPieza(TypedDict):
    """Resumen de cómo CRECE una pieza, derivado de sus snapshots (honesto, sin inventar).

    `null` (la respuesta entera) cuando hay menos de 2 snapshots: sin dos puntos no hay
    velocidad medible. Dentro, cada campo puede ser `null` si su cálculo no aplica
    (p. ej. `pct_en_primeras_24h` cuando las visualizaciones finales son 0).
    """

    # pct_en_primeras_24h: % de las visualizaciones FINALES ya acumuladas en las 1as 24 h.
    pct_en_primeras_24h: float | None
    # delta_medio_por_dia: visualizaciones ganadas por día entre el 1er y el último snapshot.
    delta_medio_por_dia: float | None
    n_snapshots: int


class HistoricoPieza(TypedDict):
    """Respuesta de `GET /api/metricas/pieza-historico`: serie histórica + velocidad de una pieza.

    `puntos` vacío = la pieza aún NO se está siguiendo (no hay snapshots): la UI lo dice
    honestamente ("sin histórico todavía"), nunca dibuja una curva inventada. `velocidad`
    es `null` con menos de 2 puntos.
    """

    pieza_id: str
    puntos: list[PuntoHistorico]
    velocidad: VelocidadPieza | None


# --------------------------------------------------------------------------- #
# Analíticas R2: seguidores, desglose, crosstab, correlación — api/metricas.py #
# --------------------------------------------------------------------------- #


class PuntoSeguidores(TypedDict):
    """Un día de la serie de seguidores: total + desglose por red."""

    # fecha: ISO (AAAA-MM-DD).
    fecha: str
    total: int
    # por_red: {red: seguidores} ese día.
    por_red: dict[str, int]


class SerieSeguidores(TypedDict):
    """Respuesta de `GET /api/metricas/seguidores`: evolución de seguidores del periodo.

    `cuenta` es `null` cuando agrega todas las marcas. `puntos` vacío = la fuente activa
    no expone serie de seguidores (degradación honesta). `neto`/`neto_por_red` resumen la
    ganancia/pérdida del periodo.
    """

    # cuenta: id_metricas de la marca, o null = todas.
    cuenta: str | None
    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    fuente: str
    puntos: list[PuntoSeguidores]
    neto: int
    generado_en: str
    # neto_por_red: {red: neto del periodo}. Va al final del modelo a propósito: el
    # guard del esquema (test_esquema_api) parsea el .ts con un regex `[^}]*` que se
    # detiene en el primer `}` del cuerpo, y un `dict` se emite como `{ [k: string]:
    # number }` (lleva `}`); dejándolo último no se pierde ningún nombre de campo.
    neto_por_red: dict[str, int]


class CeldaDesglose(TypedDict):
    """Una celda marca×red del desglose de interacciones (suma del periodo)."""

    marca: str
    red: str
    likes: int
    comentarios: int
    compartidos: int
    guardados: int
    video_views: int
    interacciones: int
    visualizaciones: int
    engagement_pct: float
    n_piezas: int


class DesgloseInteracciones(TypedDict):
    """Respuesta de `GET /api/metricas/desglose`: interacciones por marca×red.

    Cada celda detalla likes/comentarios/compartidos/guardados/video_views y los
    agregados; `totales` cierra la tabla con la suma global (misma forma que una celda
    sin `marca`/`red`).
    """

    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    fuente: str
    celdas: list[CeldaDesglose]
    generado_en: str
    # totales: suma global de la tabla (mismas claves numéricas que una celda). Va al
    # final del modelo a propósito (ver nota en `SerieSeguidores.neto_por_red`): un
    # `dict` se emite como `{ [k: string]: number }` y el regex del guard se detiene en
    # su `}`; dejándolo último no se pierde ningún campo del modelo.
    totales: dict[str, float]


class CeldaCrosstab(TypedDict):
    """Una celda marca×red×formato del crosstab de rendimiento."""

    marca: str
    red: str
    # formato: reel/post/short…; null si la fuente no lo conoce para esa celda.
    formato: str | None
    n_piezas: int
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    # rendimiento_relativo_medio: engagement medio de la celda vs la media de su grupo;
    # null si no es comparable.
    rendimiento_relativo_medio: float | None


class Crosstab(TypedDict):
    """Respuesta de `GET /api/metricas/crosstab`: rendimiento cruzado marca×red×formato."""

    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    fuente: str
    celdas: list[CeldaCrosstab]
    generado_en: str


class PostEstrella(TypedDict):
    """La pieza que mejor rindió de una marca×red×fecha (apuntala la correlación)."""

    id: str
    titulo: str
    engagement_pct: float
    # url: puede no existir según la fuente/plataforma.
    url: str | None


class ItemCorrelacion(TypedDict):
    """Un punto de la correlación seguidores ganados ↔ piezas publicadas."""

    marca: str
    red: str
    # fecha: ISO (AAAA-MM-DD).
    fecha: str
    seguidores_ganados: int
    n_posts: int
    # seguidores_por_post: ratio del día; null si no hubo posts (no se divide por cero).
    seguidores_por_post: float | None
    # post_estrella: la pieza que mejor rindió ese día; null si no hay piezas.
    post_estrella: PostEstrella | None


class CorrelacionSeguidores(TypedDict):
    """Respuesta de `GET /api/metricas/correlacion`: seguidores ganados ↔ piezas.

    `nota` explica la lectura (correlación, no causalidad) para la UI.
    """

    rango: str
    etiqueta_rango: str
    periodo: PeriodoMetricas
    fuente: str
    items: list[ItemCorrelacion]
    nota: str
    generado_en: str


# --------------------------------------------------------------------------- #
# Paginacion — envelope aditivo comun a los listados pesados (#121)            #
# --------------------------------------------------------------------------- #


class Paginacion(TypedDict):
    """Envelope ADITIVO de paginacion (offset-based, #121).

    Lo añaden los listados pesados (publicaciones/runs/generaciones) junto a su
    clave de lista. `total` = filas existentes sin paginar; `limite` = tamaño de
    pagina efectivo (igual a `total` si no se paginó); `desplazamiento` = offset.
    """

    total: int
    limite: int
    desplazamiento: int


# --------------------------------------------------------------------------- #
# Metricas de un run/generacion — emitidas por el CLI cuando devuelve JSON     #
# --------------------------------------------------------------------------- #


class MetricasRun(TypedDict):
    """Metricas de monitorizacion de un run/generacion IA (las que reporta el CLI).

    El handler las omite (clave a `null`) si el run no produjo metricas (interactivo
    o CLI sin JSON). Cuando vienen, traen estos seis campos.
    """

    tokens_in: int
    tokens_out: int
    num_turns: int
    total_cost_usd: float
    duration_ms: int
    modelo: str


# --------------------------------------------------------------------------- #
# Publicaciones — dominio/publicaciones.py (publicacion_a_dict) + api          #
# --------------------------------------------------------------------------- #

# El flujo de aprobacion de equipo (#9, Fase 3) intercala `en_revision` entre el
# borrador y el aprobado.
EstadoPublicacion = Literal["borrador", "en_revision", "aprobado", "programado", "publicado"]
# Etapa REAL de la tubería IA de una pieza (Flujo C), derivada por
# `pipeline_estado.etapa_de_pieza`. La consume el Feed de ideación (Flujo D): es el
# estado-por-etapa "en vivo" de la pieza, más rico que `estado` (incluye el gate humano).
# Mantener en sincronía con `pipeline_estado.ETAPAS_PIEZA` y con `EtapaIa` del front.
EtapaIa = Literal[
    "generando_copy",
    "generando_arte",
    "lista_para_revisar",
    "aprobada",
    "programada",
    "publicada",
]
# Veredicto editorial de una pieza: TEXTO LIBRE. El auto-verificador (skills de copy)
# escribe veredictos legibles y matizados ("ok — confirmar marcador con el equipo",
# "marcar claramente como rumor", "pendiente resultado real del partido"), no un enum
# cerrado. La UI deriva la insignia (Listo/Revisar/No publicar) de un prefijo normalizado
# (`meta.metaVeredicto`). "" = sin veredicto. Era un `Literal` cerrado y eso rompía el
# contrato `RespuestaPublicaciones` en cada pieza con veredicto real (drift del calendario).
Veredicto = str


class Publicacion(TypedDict):
    """Una publicacion serializada (`dominio.publicaciones.publicacion_a_dict`).

    `marca_nombre`/`red_nombre` se resuelven en servidor. `imagen` es el nombre de
    archivo ("" si no hay) e `imagen_url` su ruta servible ("" si no hay).
    `autor_id`/`autor_nombre` (atribucion por usuario, #130 Fase 1) identifican a quien
    creo la pieza; "" en piezas legadas/anonimas (la UI las muestra como "desconocido").

    Flujo de aprobacion de equipo (#9, Fase 3): `enviado_a_revision_en`/`revisor_id`/
    `revisor_nombre`/`revisado_en` registran quien la envio/reviso y cuando; "" mientras
    no haya pasado por revision (incluidas las piezas legadas). `preparado_en` es la marca
    DRY-RUN del programador (instante en que quedo "lista para publicar"; el posteo real
    via Metricool esta gated por `KENI_PUBLICAR_REAL`); "" hasta que vence su `fecha_programada`.
    """

    id: str
    # Id del `contenido` padre (tema). La UI lo usa para colgar los comentarios del item,
    # que son del tema y no de la fila por red. "" en piezas legadas sin padre.
    contenido_id: str
    titulo: str
    marca: str
    marca_nombre: str
    red: str
    red_nombre: str
    contenido: str
    # Texto que va DENTRO de la imagen (copy-in: titular/claim sobre la placa), distinto del
    # `contenido` que acompana a la publicacion. "" en piezas legadas o si no se genero.
    copy_in: str
    estado: EstadoPublicacion
    veredicto: Veredicto
    autor_id: str
    autor_nombre: str
    enviado_a_revision_en: str
    revisor_id: str
    revisor_nombre: str
    revisado_en: str
    preparado_en: str
    id_post_metricool: str
    # Origen de la imagen: "ia"|"galeria"|"fuente". Si es "fuente", `imagen_fuente` trae la
    # URL original del articulo (p.ej. RSS de marca propia); el editor ofrece usarla.
    tipo_contenido: str
    imagen_fuente: str
    # Media id de la FOTO CRUDA de fondo (separada de `imagen`, la placa ya compuesta);
    # permite al editor inline recomponer la placa en vivo al reabrir la pieza.
    foto: str
    # Checklist de produccion por red (pendiente=True): Copy/Imagen/Revision/Publicar. El
    # editor unificado los expone como checks marcables (PATCH a la fila por plataforma).
    falta_copy: bool
    falta_imagen: bool
    falta_revision: bool
    falta_publicar: bool
    # Etapa REAL de la tubería IA (Flujo C), derivada de `estado`+checklist por
    # `pipeline_estado.etapa_de_pieza`. La prefiere el Feed (Flujo D) sobre su derivación.
    etapa_ia: EtapaIa
    fecha_creacion: str
    fecha_actualizacion: str
    fecha_programada: str
    origen: str
    imagen: str
    imagen_url: str
    evergreen: bool
    # Auto-avance: la pieza esta EXENTA de copy-in (imagen dramatica/autoexplicativa que no lo
    # necesita). Opcional: las piezas legadas no lo traen y el feed lo lee como False.
    copy_in_exento: NotRequired[bool]


class RespuestaPublicaciones(TypedDict):
    """Listado de `GET /api/publicaciones` con el envelope de paginacion (#121)."""

    publicaciones: list[Publicacion]
    paginacion: Paginacion


class RespuestaPublicacion(TypedDict):
    """Respuesta de los endpoints que devuelven UNA publicacion (`{publicacion}`)."""

    publicacion: Publicacion


# --------------------------------------------------------------------------- #
# Aprobacion de equipo + panel ligero — api/aprobacion.py + api/panel.py (#9)  #
# --------------------------------------------------------------------------- #


class RespuestaColaAprobacion(TypedDict):
    """Cola de aprobacion (`GET /api/aprobacion/cola`): piezas en revision, FIFO.

    Cada item es una `Publicacion` completa (incluye `autor_nombre`/
    `enviado_a_revision_en`: quien la envio y desde cuando espera). `total` = nº en cola.
    """

    cola: list[Publicacion]
    total: int


class TotalPanel(TypedDict):
    """Total consolidado de metricas para el panel (mismas 4 metricas que el reporte)."""

    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class PicoPanel(TypedDict):
    """Un movimiento destacado ('pico') del periodo en el panel."""

    marca: str
    # direccion: "sube" | "baja" | "estable".
    direccion: str
    variacion_vis_pct: float
    visualizaciones: int
    pieza_titulo: str


class MetricasPanel(TypedDict):
    """Resumen de metricas del panel (REUSA `keni_metricas.servicio`, solo lectura).

    `disponible` es False si la fuente de metricas falló (el resto del panel sigue útil);
    en ese caso `total` es `null` y `picos` viene vacío. `rango` solo está cuando hay
    datos, por eso es `NotRequired`. `fuente` marca muestra vs real (badge en la UI).
    """

    disponible: bool
    fuente: str
    total: TotalPanel | None
    picos: list[PicoPanel]
    rango: NotRequired[str]


class ColaPanel(TypedDict):
    """Bloque 'cola de aprobacion' del panel: cuántas piezas esperan revisión."""

    total: int


class ProximaPanel(TypedDict):
    """Una pieza programada próxima (vista mínima del panel, nombres resueltos).

    `preparado_en` viene con el instante DRY-RUN si el programador ya la preparó (venció);
    "" si aún no vence. El posteo real vía Metricool está gated por `KENI_PUBLICAR_REAL`.
    """

    id: str
    titulo: str
    marca: str
    marca_nombre: str
    red: str
    red_nombre: str
    fecha_programada: str
    preparado_en: str


class ProximasPanel(TypedDict):
    """Bloque 'próximas programadas' del panel: las más inminentes + el total."""

    items: list[ProximaPanel]
    total: int


class GatingPanel(TypedDict):
    """Aviso de frontera del producto: el sistema NO publica solo (gated por `KENI_PUBLICAR_REAL`)."""

    publicacion_real_activa: bool
    nota: str


class RespuestaPanel(TypedDict):
    """Respuesta de `GET /api/panel`: dashboard ligero de un vistazo (#9, Fase 3).

    Agrega métricas/picos (reusa los caminos de lectura de Metricas, sin tocar su
    página), el contador de la cola de aprobación y las próximas piezas programadas.
    `gating` recuerda que el posteo real (vía Metricool) está gated por `KENI_PUBLICAR_REAL`.
    """

    metricas: MetricasPanel
    cola: ColaPanel
    proximas: ProximasPanel
    gating: GatingPanel


# --------------------------------------------------------------------------- #
# Generaciones — DEFERIDO del subconjunto generado (#120).                     #
#                                                                              #
# `Generacion` y sus envelopes NO se modelan aqui a proposito: su campo        #
# `resultado` es un dict LIBRE cuya forma depende del `tipo` (copy/rss/        #
# hashtags/imagen/verificacion) y el frontend lo tipa de forma RICA            #
# (`ResultadoGeneracion`, con `piezas`/`publicaciones`/`verificacion`...). Un  #
# `$def` con `resultado: object` regresaria ese tipado a `{}`, perdiendo       #
# seguridad de tipos en ~14 consumidores. Mejor mantener `Generacion` a mano   #
# en `types.ts` (rico) que forzar un contrato generado mas pobre. El sondeo    #
# de generaciones tampoco se valida en runtime por la misma razon.            #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Comercial — api/comercial.py (_a_dict) + comercial.py. Procedencia (#124):   #
# `fuente`/`es_muestra` marcan cifras de muestra (sinteticas) vs reales.       #
# --------------------------------------------------------------------------- #

EstadoComercial = Literal["activa", "pausada", "cerrada"]
MetricaComercial = Literal["interacciones", "visualizaciones", "alcance"]


class ActualComercial(TypedDict):
    """Valor actual de una pieza comercial (del ultimo snapshot)."""

    ts: str
    interacciones: int
    visualizaciones: int
    alcance: int
    engagement_pct: float


class SnapshotComercial(TypedDict):
    """Un punto de la serie temporal de una pieza comercial (acumulado).

    Ademas de las metricas "base" (interacciones/visualizaciones/alcance) lleva el
    desglose GRANULAR por pieza; cada uno es 0 cuando la fuente no lo expone (no se
    inventa), igual que `alcance` por pieza.
    """

    ts: str
    interacciones: int
    visualizaciones: int
    alcance: int
    likes: int
    comentarios: int
    compartidos: int
    guardados: int
    video_views: int
    tiempo_medio_vis_s: int
    clics_enlace: int
    seguidores_netos_atribuidos: int


class PostSeleccionableComercial(TypedDict):
    """Un post real de Metricool elegible para monitorizar (`GET /api/comercial/posts`)."""

    id: str
    red: str
    titulo: str
    publicado: str
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    url: NotRequired[str | None]


class RespuestaPostsComercial(TypedDict):
    """Listado de posts seleccionables + procedencia (muestra vs real)."""

    posts: list[PostSeleccionableComercial]
    fuente: str
    es_muestra: bool


class PublicacionComercial(TypedDict):
    """Una pieza comercial monitoreada (`api/comercial._a_dict`).

    `fuente`/`es_muestra` (#124) marcan la procedencia de las cifras. `serie` solo
    viene en el detalle / al crear (`con_serie=True`), por eso es `NotRequired`.
    """

    id: str
    url: str
    id_post_metricool: str
    titulo: str
    marca: str
    marca_nombre: str
    cliente: str
    campania: str
    red: str
    red_nombre: str
    formato: str
    metrica_objetivo: MetricaComercial
    objetivo: int
    estado: EstadoComercial
    publicado: str
    notas: str
    aviso_en: str
    fecha_creacion: str
    fecha_actualizacion: str
    actual: ActualComercial
    progreso_pct: float
    alcanzado: bool
    fuente: str
    es_muestra: bool
    serie: NotRequired[list[SnapshotComercial]]


class RespuestaPublicacionesComercial(TypedDict):
    """Listado de `GET /api/comercial/publicaciones` con procedencia comun (#124)."""

    publicaciones: list[PublicacionComercial]
    fuente: str
    es_muestra: bool


class RespuestaPublicacionComercial(TypedDict):
    """Respuesta de los endpoints que devuelven UNA pieza comercial (`{publicacion}`)."""

    publicacion: PublicacionComercial


class RespuestaRefrescarComercial(TypedDict):
    """Respuesta de `POST /api/comercial/refrescar`: nº de piezas actualizadas."""

    actualizadas: int


# --------------------------------------------------------------------------- #
# Respuestas genericas comunes                                                 #
# --------------------------------------------------------------------------- #


class RespuestaMensaje(TypedDict):
    mensaje: str


class ErrorApi(TypedDict):
    """Forma de error que devuelve el backend (uno u otro campo, en espanol)."""

    error: NotRequired[str]
    mensaje: NotRequired[str]


# Orden estable de las interfaces en el `types.gen.ts` generado. Cada `TypedDict`
# se exporta como `interface`; los `Literal` (p. ej. `NivelEstado`) viajan inline
# en los campos que los usan y NO necesitan listarse aqui.
MODELOS = [
    ResultadoEstado,
    RespuestaEstado,
    MarcaDisponible,
    CredencialesPresentes,
    RespuestaConfig,
    CuerpoGuardarConfig,
    LimiteRed,
    RespuestaLimites,
    RangoMetrica,
    OpcionesMetricas,
    TotalMetricas,
    CuentaMetrica,
    RedMetrica,
    RedCobertura,
    MarcaCobertura,
    ReporteMetricas,
    ComparativaMetrica,
    ComparativaPorMarca,
    TotalComparativa,
    CompararMetricas,
    # Análisis diario con narrativa (F6/#146).
    PiezaAnalisis,
    MovimientoAnalisis,
    SiguientePasoAnalisis,
    AnalisisDiario,
    # Estado del refresco de la cache de métricas (botón Actualizar + polling).
    EstadoMetricas,
    # Analítica de piezas (estadísticas + top/peores + distribución) y tendencia diaria.
    PeriodoMetricas,
    EstadisticasNumericas,
    PiezaMetrica,
    DistribucionBucket,
    AnaliticaPiezas,
    PuntoSerie,
    TendenciaDiaria,
    # Drill-down marca -> pieza (rendimiento por pieza publicada).
    PiezaRendimiento,
    PiezasRendimiento,
    # Listado completo de piezas del periodo + histórico por pieza + velocidad.
    PiezaListado,
    PiezasListado,
    PuntoHistorico,
    VelocidadPieza,
    HistoricoPieza,
    # Analíticas R2: seguidores, desglose, crosstab, correlación.
    PuntoSeguidores,
    SerieSeguidores,
    CeldaDesglose,
    DesgloseInteracciones,
    CeldaCrosstab,
    Crosstab,
    PostEstrella,
    ItemCorrelacion,
    CorrelacionSeguidores,
    # Envelope/auxiliares compartidos.
    Paginacion,
    MetricasRun,
    # Publicaciones (#101 ampliacion churn).
    Publicacion,
    RespuestaPublicaciones,
    RespuestaPublicacion,
    # Aprobacion de equipo + panel ligero (#9, Fase 3).
    RespuestaColaAprobacion,
    TotalPanel,
    PicoPanel,
    MetricasPanel,
    ColaPanel,
    ProximaPanel,
    ProximasPanel,
    GatingPanel,
    RespuestaPanel,
    # Generaciones: DEFERIDAS (ver bloque arriba). Se mantienen a mano en types.ts.
    # Comercial (#124: fuente/es_muestra).
    ActualComercial,
    SnapshotComercial,
    PostSeleccionableComercial,
    RespuestaPostsComercial,
    PublicacionComercial,
    RespuestaPublicacionesComercial,
    RespuestaPublicacionComercial,
    RespuestaRefrescarComercial,
    RespuestaMensaje,
    ErrorApi,
]
