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
# Veredicto editorial de una pieza. "" = sin veredicto.
Veredicto = Literal["listo", "revisar", "no_publicar", ""]


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
    esta gated por #5/#8); "" hasta que vence su `fecha_programada`.
    """

    id: str
    titulo: str
    marca: str
    marca_nombre: str
    red: str
    red_nombre: str
    contenido: str
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
    fecha_creacion: str
    fecha_actualizacion: str
    fecha_programada: str
    origen: str
    imagen: str
    imagen_url: str
    evergreen: bool


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
    "" si aún no vence. El posteo real está gated por #5/#8.
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
    """Aviso de frontera del producto: el sistema NO publica solo (gated por #5/#8)."""

    publicacion_real_activa: bool
    nota: str


class RespuestaPanel(TypedDict):
    """Respuesta de `GET /api/panel`: dashboard ligero de un vistazo (#9, Fase 3).

    Agrega métricas/picos (reusa los caminos de lectura de Metricas, sin tocar su
    página), el contador de la cola de aprobación y las próximas piezas programadas.
    `gating` recuerda que el posteo real está pendiente de #5/#8.
    """

    metricas: MetricasPanel
    cola: ColaPanel
    proximas: ProximasPanel
    gating: GatingPanel


# --------------------------------------------------------------------------- #
# Runs — agentes._parsear_run + api/agentes.py (listado global y por agente)   #
# --------------------------------------------------------------------------- #

# Estado del ciclo de vida de un run. La forma publica conserva el valor crudo
# del YAML, asi que se modela abierto (str) en vez de un Literal cerrado.
EstadoRun = str


class Run(TypedDict):
    """Un run (ejecucion) de un agente, en su forma publica.

    Forma CANONICA: la de `agentes._parsear_run` (`GET .../runs/{id}` y el listado
    `GET .../runs`): `id/prompt/modo/estado/motivo/fecha_inicio/metricas` + la
    `salida` y `fecha_fin` del run completo. El LISTADO GLOBAL (`GET /api/runs`) y
    el detalle del agente omiten `salida`/`fecha_fin` y, el global, AÑADE
    `agente`/`agente_nombre`: por eso esos cuatro van como `NotRequired`. `metricas`
    es `null` si el run no produjo metricas.
    """

    id: str
    prompt: str
    modo: str
    estado: EstadoRun
    motivo: str
    fecha_inicio: str
    metricas: MetricasRun | None
    salida: NotRequired[str]
    fecha_fin: NotRequired[str]
    # Solo en el listado global `GET /api/runs` (denormalizados).
    agente: NotRequired[str]
    agente_nombre: NotRequired[str]


class RespuestaRun(TypedDict):
    """Respuesta de los endpoints que devuelven UN run (`{run}`).

    `mensaje` solo lo añade el lanzamiento INTERACTIVO (`POST .../runs` con modo
    `interactivo`): el texto legible del lanzamiento; ausente en el resto.
    """

    run: Run
    mensaje: NotRequired[str]


class RespuestaRuns(TypedDict):
    """Listado de runs. El global (`GET /api/runs`) trae `paginacion`; el del agente
    (`GET /api/agentes/{id}/runs`) no, por eso es `NotRequired`."""

    runs: list[Run]
    paginacion: NotRequired[Paginacion]


# --- Agregados de runs: `GET /api/runs/agregados` -------------------------- #


class TotalRuns(TypedDict):
    coste_usd: float
    tokens: int
    runs: int


class AgregadoPorAgente(TypedDict):
    agente: str
    agente_nombre: str
    coste_usd: float
    tokens: int
    runs: int


class AgregadoPorDia(TypedDict):
    dia: str
    coste_usd: float
    tokens: int
    runs: int


class RespuestaRunsAgregados(TypedDict):
    """Respuesta de `GET /api/runs/agregados`: totales de coste/tokens/runs."""

    total: TotalRuns
    por_agente: list[AgregadoPorAgente]
    por_dia: list[AgregadoPorDia]


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
MetricaComercial = Literal["interacciones", "alcance"]


class ActualComercial(TypedDict):
    """Valor actual de una pieza comercial (del ultimo snapshot)."""

    ts: str
    interacciones: int
    alcance: int
    engagement_pct: float


class SnapshotComercial(TypedDict):
    """Un punto de la serie temporal de una pieza comercial (acumulado)."""

    ts: str
    interacciones: int
    alcance: int


class PublicacionComercial(TypedDict):
    """Una pieza comercial monitoreada (`api/comercial._a_dict`).

    `fuente`/`es_muestra` (#124) marcan la procedencia de las cifras. `serie` solo
    viene en el detalle / al crear (`con_serie=True`), por eso es `NotRequired`.
    """

    id: str
    url: str
    titulo: str
    marca: str
    marca_nombre: str
    cliente: str
    campania: str
    red: str
    red_nombre: str
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
    # Runs (canonico + listado global + agregados).
    Run,
    RespuestaRun,
    RespuestaRuns,
    TotalRuns,
    AgregadoPorAgente,
    AgregadoPorDia,
    RespuestaRunsAgregados,
    # Generaciones: DEFERIDAS (ver bloque arriba). Se mantienen a mano en types.ts.
    # Comercial (#124: fuente/es_muestra).
    ActualComercial,
    SnapshotComercial,
    PublicacionComercial,
    RespuestaPublicacionesComercial,
    RespuestaPublicacionComercial,
    RespuestaRefrescarComercial,
    RespuestaMensaje,
    ErrorApi,
]
