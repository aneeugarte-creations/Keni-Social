"""Config — accesores del dominio noticias. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    _VERDADEROS,
    CLUSTER_BREAKING_FUENTES_DEF,
    CLUSTER_BREAKING_VENTANA_H_DEF,
    CLUSTER_UMBRAL_DEF,
    CLUSTER_VENTANA_H_DEF,
    ENV_AFP_BASE_URL,
    ENV_AFP_CLIENT_ID,
    ENV_AFP_CLIENT_SECRET,
    ENV_AUTO_PROGRAMAR,
    ENV_AUTOGEN_ARTE,
    ENV_CLUSTER_BREAKING_FUENTES,
    ENV_CLUSTER_BREAKING_VENTANA_H,
    ENV_CLUSTER_UMBRAL,
    ENV_CLUSTER_VENTANA_H,
    ENV_FEED_SLA_MIN,
    ENV_FUENTES_BAJA_CONFIANZA,
    ENV_INGESTA,
    ENV_INGESTA_BATCH,
    ENV_INGESTA_INTERVALO_BREAKING,
    ENV_INGESTA_INTERVALO_CIENCIA_TECH,
    ENV_INGESTA_INTERVALO_DEFECTO,
    ENV_INGESTA_INTERVALO_DEPORTES,
    ENV_INGESTA_INTERVALO_GAMING,
    ENV_INGESTA_INTERVALO_INTERNACIONAL,
    ENV_INGESTA_INTERVALO_MX,
    ENV_INGESTA_INTERVALO_TENDENCIAS,
    ENV_INGESTA_MAX_ERRORES,
    ENV_INGESTA_MAX_ITEMS,
    ENV_INGESTA_WORKERS,
    ENV_PIPELINE,
    ENV_PIPELINE_INTERVALO_HORAS,
    ENV_PIPELINE_MAX,
    ENV_QA,
    ENV_REUTERS_API_KEY,
    ENV_NOTICIAS_GC,
    ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
    ENV_NOTICIAS_GC_INTERVALO_HORAS,
    ENV_NOTICIAS_GC_SCORE_UMBRAL,
    ENV_SCORE_BONUS_BREAKING,
    ENV_SCORE_PESO_CORROBORACION,
    ENV_SCORE_PESO_FRESCURA,
    ENV_SCORE_PESO_MARCA,
    ENV_SCORE_PESO_VIRALIDAD,
    ENV_REUTERS_BASE_URL,
    ENV_TRAD_LOTE,
    ENV_TRAD_MIN_SCORE,
    ENV_TRADUCCION_MAX,
    FEED_SLA_MIN_DEF,
    FUENTES_BAJA_CONFIANZA_DEF,
    INGESTA_BATCH_DEF,
    INGESTA_INTERVALO_BREAKING_DEF,
    INGESTA_INTERVALO_CIENCIA_TECH_DEF,
    INGESTA_INTERVALO_DEFECTO_DEF,
    INGESTA_INTERVALO_DEPORTES_DEF,
    INGESTA_INTERVALO_GAMING_DEF,
    INGESTA_INTERVALO_INTERNACIONAL_DEF,
    INGESTA_INTERVALO_MX_DEF,
    INGESTA_INTERVALO_TENDENCIAS_DEF,
    INGESTA_MAX_ERRORES_DEF,
    INGESTA_MAX_ITEMS_DEF,
    INGESTA_WORKERS_DEF,
    NOTICIAS_GC_INACTIVIDAD_HORAS_DEF,
    NOTICIAS_GC_INTERVALO_HORAS_DEF,
    NOTICIAS_GC_SCORE_UMBRAL_DEF,
    PIPELINE_INTERVALO_HORAS_DEF,
    PIPELINE_MAX_DEF,
    SCORE_BONUS_BREAKING_DEF,
    SCORE_PESO_CORROBORACION_DEF,
    SCORE_PESO_FRESCURA_DEF,
    SCORE_PESO_MARCA_DEF,
    SCORE_PESO_VIRALIDAD_DEF,
    TRAD_LOTE_DEF,
    TRAD_MIN_SCORE_DEF,
    _crudo,
    _entero,
    os,
)

# --------------------------------------------------------------------------- #
# Motor de ingesta persistente (Ola A)                                          #
# --------------------------------------------------------------------------- #


def ingesta_activa() -> bool:
    """True si el motor de ingesta persistente debe sondear feeds (`KENI_INGESTA`).

    Def OFF (CI/tests): sin el flag, el hilo arranca pero no sondea nada. Se ACTIVA en
    producción (deploy: `KENI_INGESTA=1`) para que el archivo de artículos esté siempre al día.
    SOLO LEE feeds públicos y persiste artículos; no genera ni publica nada.
    """
    return _crudo(ENV_INGESTA).lower() in _VERDADEROS


def ingesta_batch() -> int:
    """Máximo de feeds a sondear por barrido (`KENI_INGESTA_BATCH`, def 40, min 1)."""
    return _entero(ENV_INGESTA_BATCH, INGESTA_BATCH_DEF, minimo=1)


def ingesta_workers() -> int:
    """Descargas de feeds en paralelo por barrido (`KENI_INGESTA_WORKERS`, def 12, min 1)."""
    return _entero(ENV_INGESTA_WORKERS, INGESTA_WORKERS_DEF, minimo=1)


def ingesta_max_items() -> int:
    """Artículos a archivar por feed y sondeo (`KENI_INGESTA_MAX_ITEMS`, def 100, min 1)."""
    return _entero(ENV_INGESTA_MAX_ITEMS, INGESTA_MAX_ITEMS_DEF, minimo=1)


# Cadencia por categoría: env var + defecto de cada una (segundos), para el accesor genérico.
_INGESTA_INTERVALOS: dict[str, tuple[str, int]] = {
    "breaking": (ENV_INGESTA_INTERVALO_BREAKING, INGESTA_INTERVALO_BREAKING_DEF),
    "deportes": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "mx": (ENV_INGESTA_INTERVALO_MX, INGESTA_INTERVALO_MX_DEF),
    "internacional": (ENV_INGESTA_INTERVALO_INTERNACIONAL, INGESTA_INTERVALO_INTERNACIONAL_DEF),
    "tendencias": (ENV_INGESTA_INTERVALO_TENDENCIAS, INGESTA_INTERVALO_TENDENCIAS_DEF),
    "ciencia-tech": (ENV_INGESTA_INTERVALO_CIENCIA_TECH, INGESTA_INTERVALO_CIENCIA_TECH_DEF),
    "gaming": (ENV_INGESTA_INTERVALO_GAMING, INGESTA_INTERVALO_GAMING_DEF),
}


def ingesta_intervalo_categoria(categoria: str) -> int:
    """Cadencia (segundos) de sondeo para una categoría de feed.

    breaking/deportes ~180s, mx/internacional/tendencias ~600s, ciencia-tech/gaming ~1800s.
    Una categoría desconocida (o '') cae al defecto general (`KENI_INGESTA_INTERVALO_DEFECTO`,
    def 600s). Cada accesor es configurable por env y min 1s.
    """
    env, defecto = _INGESTA_INTERVALOS.get(
        (categoria or "").strip().lower(),
        (ENV_INGESTA_INTERVALO_DEFECTO, INGESTA_INTERVALO_DEFECTO_DEF),
    )
    return _entero(env, defecto, minimo=1)


def cluster_ventana_h() -> int:
    """Ventana reciente (horas) de agrupación de historias (`KENI_CLUSTER_VENTANA_H`, def 72, min 1).

    Clustering INCREMENTAL: solo se cargan los clusters cuya `ultimo_visto` cae en esta ventana
    para decidir a cuál unir un item nuevo. Acota el trabajo por barrido (nunca el archivo entero).
    """
    return _entero(ENV_CLUSTER_VENTANA_H, CLUSTER_VENTANA_H_DEF, minimo=1)


def cluster_umbral() -> float:
    """Umbral fuzzy de cruce de títulos para unir un item a un cluster (`KENI_CLUSTER_UMBRAL`, def 0.82).

    Ratio `SequenceMatcher` mínimo (en [0,1]) para considerar dos titulares la misma historia.
    Alto a propósito: conservador, solo une variantes claras. Valor inválido o fuera de [0,1] → def.
    """
    crudo = _crudo(ENV_CLUSTER_UMBRAL)
    if not crudo:
        return CLUSTER_UMBRAL_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return CLUSTER_UMBRAL_DEF
    if valor < 0.0 or valor > 1.0:
        return CLUSTER_UMBRAL_DEF
    return valor


def cluster_breaking_fuentes() -> int:
    """Fuentes distintas mínimas para marcar una historia "breaking" (`KENI_CLUSTER_BREAKING_FUENTES`, def 3, min 2)."""
    return _entero(ENV_CLUSTER_BREAKING_FUENTES, CLUSTER_BREAKING_FUENTES_DEF, minimo=2)


def cluster_breaking_ventana_h() -> int:
    """Ventana (horas) para la heurística de breaking (`KENI_CLUSTER_BREAKING_VENTANA_H`, def 6, min 1)."""
    return _entero(ENV_CLUSTER_BREAKING_VENTANA_H, CLUSTER_BREAKING_VENTANA_H_DEF, minimo=1)


def _peso01(env_flag: str, defecto: float) -> float:
    """Lee un peso float del store/env, acotado a [0,1]; valor inválido/ausente → `defecto`."""
    crudo = _crudo(env_flag)
    if not crudo:
        return defecto
    try:
        valor = float(crudo)
    except ValueError:
        return defecto
    return min(1.0, max(0.0, valor))


def score_pesos():
    """Pesos del algoritmo de ponderación del score de cluster, como `clustering.PesosScore`.

    Lee cada peso del store/env (clamp [0,1]; default = los de `clustering`). El daemon de ingesta
    inyecta el resultado en `clustering.puntuar` para que el equipo afine la jerarquización desde
    la consola sin tocar código. Import perezoso de `dominio.clustering` para evitar ciclos.
    """
    from .dominio.clustering import PesosScore

    return PesosScore(
        corroboracion=_peso01(ENV_SCORE_PESO_CORROBORACION, SCORE_PESO_CORROBORACION_DEF),
        frescura=_peso01(ENV_SCORE_PESO_FRESCURA, SCORE_PESO_FRESCURA_DEF),
        viralidad=_peso01(ENV_SCORE_PESO_VIRALIDAD, SCORE_PESO_VIRALIDAD_DEF),
        marca=_peso01(ENV_SCORE_PESO_MARCA, SCORE_PESO_MARCA_DEF),
        breaking=_peso01(ENV_SCORE_BONUS_BREAKING, SCORE_BONUS_BREAKING_DEF),
    )


# --------------------------------------------------------------------------- #
# GC del pool de noticias por relevancia (no por edad sola)                     #
# --------------------------------------------------------------------------- #


def noticias_gc_activo() -> bool:
    """True si el GC del pool de noticias debe BARRER (`KENI_NOTICIAS_GC`, def OFF).

    Conservador: sin el flag NO se borra ninguna noticia. Con el flag, un hilo demonio purga el
    ruido de baja relevancia (ver `db_noticias.purgar_pool_irrelevante`) cada N horas.
    """
    return _crudo(ENV_NOTICIAS_GC).lower() in _VERDADEROS


def noticias_gc_intervalo_horas() -> int:
    """Cada cuántas horas barre el GC del pool (`KENI_NOTICIAS_GC_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_NOTICIAS_GC_INTERVALO_HORAS, NOTICIAS_GC_INTERVALO_HORAS_DEF, minimo=1)


def noticias_gc_score_umbral() -> float:
    """Score por debajo del cual una historia de UNA fuente es "ruido" purgable
    (`KENI_NOTICIAS_GC_SCORE_UMBRAL`, def 0.15, clamp [0,1]). 0 = no purgar por score."""
    return _peso01(ENV_NOTICIAS_GC_SCORE_UMBRAL, NOTICIAS_GC_SCORE_UMBRAL_DEF)


def noticias_gc_inactividad_horas() -> int:
    """Horas SIN actividad para que una historia de baja relevancia sea purgable
    (`KENI_NOTICIAS_GC_INACTIVIDAD_HORAS`, def 48, min 1). Guarda contra purgar lo recién visto."""
    return _entero(
        ENV_NOTICIAS_GC_INACTIVIDAD_HORAS, NOTICIAS_GC_INACTIVIDAD_HORAS_DEF, minimo=1
    )



# --------------------------------------------------------------------------- #
# Monitor de cobertura + traducción completa + auto-verificación (Ola D)        #
# --------------------------------------------------------------------------- #


def ingesta_max_errores() -> int:
    """Errores seguidos tras los que el daemon AUTO-DESACTIVA un feed (`KENI_INGESTA_MAX_ERRORES`, def 8, min 1).

    Al alcanzar el umbral, el barrido pone `activo=0` + `desactivado_auto=1` y deja de sondear
    el feed (queda visible para reactivar). En éxito el contador se resetea.
    """
    return _entero(ENV_INGESTA_MAX_ERRORES, INGESTA_MAX_ERRORES_DEF, minimo=1)


def feed_sla_min() -> int:
    """SLA de frescura por feed en minutos (`KENI_FEED_SLA_MIN`, def 180, min 1).

    Un feed activo sin items nuevos en más de este margen cuenta como "stale" en `/salud`.
    """
    return _entero(ENV_FEED_SLA_MIN, FEED_SLA_MIN_DEF, minimo=1)


def trad_min_score() -> float:
    """Score mínimo de un cluster extranjero para entrar a traducción (`KENI_TRAD_MIN_SCORE`, def 0).

    0 = traducir TODO cluster extranjero reciente; subirlo limita la traducción a las historias
    más relevantes. Valor inválido o negativo → def.
    """
    crudo = _crudo(ENV_TRAD_MIN_SCORE)
    if not crudo:
        return TRAD_MIN_SCORE_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return TRAD_MIN_SCORE_DEF
    return max(0.0, valor)


def trad_lote() -> int:
    """Clusters extranjeros a traducir por barrido (`KENI_TRAD_LOTE`, def 40, min 1).

    Acota el trabajo por barrido para no saturar Haiku; el backlog se procesa a lo largo de
    varios barridos (sin tope artificial: lo que falte se coge en el siguiente).
    """
    return _entero(ENV_TRAD_LOTE, TRAD_LOTE_DEF, minimo=1)


def fuentes_baja_confianza() -> frozenset[str]:
    """Outlets/agregadores de baja confianza (`KENI_FUENTES_BAJA_CONFIANZA`, CSV).

    Una historia cuya ÚNICA fuente es uno de estos se marca 'dudosa'. Si la env/ajuste está
    vacía cae al default (`FUENTES_BAJA_CONFIANZA_DEF`); CSV explícito la SUSTITUYE por completo.
    Todo a minúsculas y sin espacios; se compara contra el host del item y su `fuente_nombre`.
    """
    crudo = _crudo(ENV_FUENTES_BAJA_CONFIANZA)
    if not crudo:
        return frozenset(FUENTES_BAJA_CONFIANZA_DEF)
    partes = {p.strip().lower() for p in crudo.split(",") if p.strip()}
    return frozenset(partes) if partes else frozenset(FUENTES_BAJA_CONFIANZA_DEF)


def pipeline_activo() -> bool:
    """True si el daemon del pipeline de contenido debe BARRER (`KENI_PIPELINE`).

    Def OFF (conservador): sin el flag el comportamiento existente NO cambia (nada se ingiere/
    genera por el pipeline). Con el flag a un valor afirmativo, un hilo demonio ejecuta cada N
    horas el flujo CI→CD→QA por marca y deja borradores en la cola de revision. Nada se publica
    solo (sigue gated). El hilo arranca SIEMPRE pero, gateado, solo actua con el flag activo.
    """
    return _crudo(ENV_PIPELINE).lower() in _VERDADEROS


def pipeline_intervalo_horas() -> int:
    """Cada cuantas horas barre el pipeline de contenido (`KENI_PIPELINE_INTERVALO_HORAS`, def 1, min 1)."""
    return _entero(ENV_PIPELINE_INTERVALO_HORAS, PIPELINE_INTERVALO_HORAS_DEF, minimo=1)


def pipeline_max() -> int:
    """Maximo de temas a ingerir+generar por barrido y por marca (`KENI_PIPELINE_MAX`, def 3, min 1).

    Cada item lanza un `claude -p`: el cap evita una avalancha de jobs por barrido.
    """
    return _entero(ENV_PIPELINE_MAX, PIPELINE_MAX_DEF, minimo=1)


def qa_activo() -> bool:
    """True si la ETAPA de QA del pipeline debe cribar la fuente (`KENI_QA`, "Validar (QA)").

    Def OFF (conservador, como el resto de etapas): sin el flag NO se criba y la etapa aparece
    "Saltada"; el copy se genera igual. Con el flag, antes de generar copy un `claude -p` evalúa
    la nota de origen (criba pre-copy). Toggle PROPIO por marca: 1 toggle = 1 etapa.
    """
    return _crudo(ENV_QA).lower() in _VERDADEROS


def alguna_etapa_pipeline_activa() -> bool:
    """True si ALGUNA etapa del pipeline (Noticias/QA/Copy/Arte) está activa globalmente.

    El daemon del pipeline barre si CUALQUIERA de sus etapas está encendida (no solo Copy):
    con "Noticias" sola, debe barrer para crear temas (CI) aunque Copy esté OFF. Cada fase del
    barrido se auto-gatea luego por su propio flag global + override por-marca.
    """
    return (
        ingesta_activa()
        or qa_activo()
        or pipeline_activo()
        or autogen_arte_activo()
    )


def autogen_arte_activo() -> bool:
    """True si la ETAPA de arte del pipeline debe ilustrar (`KENI_AUTOGEN_ARTE`, "Generar arte").

    Def OFF (conservador): el equipo hace el arte a mano. Con el flag, la etapa de arte del
    pipeline (tras la de copy) genera imagen por IA para los temas con copy pero sin imagen y
    la adjunta. Sin proveedor de imagen configurado, no hace nada (degrada).
    """
    return _crudo(ENV_AUTOGEN_ARTE).lower() in _VERDADEROS


def auto_programar_activo() -> bool:
    """True si una pieza APROBADA debe encolarse SOLA a su próximo hueco (`KENI_AUTO_PROGRAMAR`).

    Def ON (a diferencia de las demás etapas auto, que son OFF): programar no gasta recursos ni
    publica —solo asigna un hueco, reversible—, y "aprobado => programado" es el flujo deseado.
    Respeta precedencia store>env>defecto; `KENI_AUTO_PROGRAMAR=0`/`no`/`off` lo apaga.
    """
    crudo = _crudo(ENV_AUTO_PROGRAMAR).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


# --------------------------------------------------------------------------- #
# Accesores: agencias de noticias (item F) — gateadas por credencial            #
# --------------------------------------------------------------------------- #


# URLs por defecto de las agencias (override con su `*_BASE_URL`). Son los endpoints
# documentados; se centralizan aqui para no esparcir literales por el adaptador.
REUTERS_BASE_URL_DEF = "https://api.reutersconnect.com"
AFP_BASE_URL_DEF = "https://afp-apicore-prod.afp.com"


def reuters_api_key() -> str | None:
    """API key de Reuters Connect (`KENI_REUTERS_API_KEY`); None si no esta (fuente apagada)."""
    return _crudo(ENV_REUTERS_API_KEY) or None


def reuters_base_url() -> str:
    """URL base de Reuters Connect (`KENI_REUTERS_BASE_URL`, def el publico), sin barra final."""
    return (_crudo(ENV_REUTERS_BASE_URL) or REUTERS_BASE_URL_DEF).rstrip("/")


def reuters_configurado() -> bool:
    """True si Reuters tiene credencial: la fuente puede descargar (si no, queda pendiente)."""
    return bool(reuters_api_key())


def afp_client_id() -> str | None:
    """Client ID de AFP (`KENI_AFP_CLIENT_ID`); None si no esta."""
    return _crudo(ENV_AFP_CLIENT_ID) or None


def afp_client_secret() -> str | None:
    """Client secret de AFP (`KENI_AFP_CLIENT_SECRET`); None si no esta. SIN strip (sensible)."""
    valor = os.environ.get(ENV_AFP_CLIENT_SECRET)
    return valor if valor else None


def afp_base_url() -> str:
    """URL base de AFP (`KENI_AFP_BASE_URL`, def el publico), sin barra final."""
    return (_crudo(ENV_AFP_BASE_URL) or AFP_BASE_URL_DEF).rstrip("/")


def afp_configurado() -> bool:
    """True si AFP tiene AMBAS credenciales OAuth2 (si no, la fuente queda pendiente)."""
    return bool(afp_client_id() and afp_client_secret())



# --------------------------------------------------------------------------- #
# Accesores: traducción + tropicalización MX (Ola 4)                           #
# --------------------------------------------------------------------------- #


def traduccion_max() -> int:
    """Cap de temas extranjeros a traducir por request del Radar (`KENI_TRADUCCION_MAX`, def 15, min 1)."""
    return _entero(ENV_TRADUCCION_MAX, 15, minimo=1)
