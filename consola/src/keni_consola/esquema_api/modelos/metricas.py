"""Metricas — api/metricas.py.

Incluye el reporte/comparativa, el analisis diario narrativo, la analitica de
piezas (estadisticas + top/peores + distribucion), tendencia, drill-down por pieza,
listado e historico, y las analiticas R2 (seguidores, desglose, crosstab,
correlacion).
"""

from __future__ import annotations

from typing import TypedDict

from ._base import MarcaDisponible

__all__ = [
    "RangoMetrica",
    "OpcionesMetricas",
    "TotalMetricas",
    "CuentaMetrica",
    "RedMetrica",
    "RedCobertura",
    "MarcaCobertura",
    "ReporteMetricas",
    "ComparativaMetrica",
    "ComparativaPorMarca",
    "TotalComparativa",
    "CompararMetricas",
    "PiezaAnalisis",
    "MovimientoAnalisis",
    "SiguientePasoAnalisis",
    "AnalisisDiario",
    "EstadoMetricas",
    "PeriodoMetricas",
    "EstadisticasNumericas",
    "PiezaMetrica",
    "DistribucionBucket",
    "AnaliticaPiezas",
    "PuntoSerie",
    "TendenciaDiaria",
    "PiezaRendimiento",
    "PiezasRendimiento",
    "PiezaListado",
    "PiezasListado",
    "PuntoHistorico",
    "VelocidadPieza",
    "HistoricoPieza",
    "PuntoSeguidores",
    "SerieSeguidores",
    "CeldaDesglose",
    "DesgloseInteracciones",
    "CeldaCrosstab",
    "Crosstab",
    "PostEstrella",
    "ItemCorrelacion",
    "CorrelacionSeguidores",
]


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
    # Nº de publicaciones del periodo (todas las piezas, no solo las top).
    publicaciones: int


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
    a la pieza en el tablero (`/operacion/feed/lista`). `encontrado=False` => Metricool aún
    no tiene datos (recién publicada): la UI muestra "sin datos todavía", no ceros falsos.
    """

    # contenido_id: id del item del tablero, para enlazar a la pieza en /operacion/feed/lista.
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
