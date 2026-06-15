"""Config — accesores del dominio noticias. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    _VERDADEROS,
    CLUSTER_BREAKING_FUENTES_DEF,
    BREAKING_EXTRA_DIA_DEF,
    CLUSTER_BREAKING_PESO_DEF,
    CLUSTER_BREAKING_VENTANA_H_DEF,
    CLUSTER_UMBRAL_DEF,
    CLUSTER_UMBRAL_MERGE_DEF,
    CLUSTER_VENTANA_H_DEF,
    ENV_AFP_BASE_URL,
    ENV_AFP_CLIENT_ID,
    ENV_AFP_CLIENT_SECRET,
    ENV_AUTO_PROGRAMAR,
    ENV_CRITICA_IA,
    ENV_CLASIFICAR_MARCA_IA,
    ENV_MARCAS_ACTIVAS,
    ENV_MARCA_NOTICIAS,
    MARCAS_ACTIVAS_DEF,
    MARCA_NOTICIAS_DEF,
    ENV_CLUSTER_BREAKING_FUENTES,
    ENV_BREAKING_EXTRA_DIA,
    ENV_CLUSTER_BREAKING_PESO,
    ENV_CLUSTER_BREAKING_VENTANA_H,
    ENV_CLUSTER_UMBRAL,
    ENV_CLUSTER_UMBRAL_MERGE,
    ENV_CLUSTER_VENTANA_H,
    ENV_FEED_SLA_MIN,
    ENV_FUENTES_BAJA_CONFIANZA,
    ENV_FUSION_SEMANTICA_MAX,
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
    ENV_NOTICIAS_GC,
    ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
    ENV_NOTICIAS_GC_INTERVALO_HORAS,
    ENV_NOTICIAS_GC_SCORE_UMBRAL,
    ENV_PERFIL_EDITORIAL_TTL_HORAS,
    ENV_PIPELINE_ILUSTRAR,
    ENV_PIPELINE_REVISAR,
    ENV_PIPELINE_REDACTAR,
    ENV_PIPELINE_EN_PROCESO_MAX,
    ENV_PIPELINE_FETCH_FUENTE,
    ENV_PIPELINE_TEMA_TTL_HORAS,
    ENV_PIPELINE_FUSIONAR,
    ENV_PIPELINE_MAX,
    ENV_PIPELINE_RECOLECTAR,
    ENV_PIPELINE_VERIFICAR,
    ENV_QA_EN_CURSO_TTL_MIN,
    ENV_QA_FUENTE_ESFUERZO,
    ENV_QA_FUENTE_MODELO,
    ENV_QA_FUENTE_TIMEOUT,
    ENV_PRIORIZAR_PERFIL_IA,
    ENV_RENDIMIENTO_MIN_PIEZAS,
    ENV_RENDIMIENTO_RANKING,
    ENV_RENDIMIENTO_TOP_N,
    ENV_REUTERS_API_KEY,
    ENV_REUTERS_BASE_URL,
    ENV_SCORE_BONUS_BREAKING,
    ENV_SCORE_PESO_CORROBORACION,
    ENV_SCORE_PESO_FRESCURA,
    ENV_SCORE_PESO_MARCA,
    ENV_SCORE_PESO_RENDIMIENTO,
    ENV_SCORE_PESO_VELOCIDAD,
    ENV_SCORE_PESO_VIRALIDAD,
    ENV_TRAD_LOTE,
    ENV_TRAD_MIN_SCORE,
    ENV_TRADUCCION_MAX,
    FEED_SLA_MIN_DEF,
    FUENTES_BAJA_CONFIANZA_DEF,
    FUSION_SEMANTICA_MAX_DEF,
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
    PERFIL_EDITORIAL_TTL_HORAS_DEF,
    PIPELINE_EN_PROCESO_MAX_DEF,
    PIPELINE_TEMA_TTL_HORAS_DEF,
    PIPELINE_MAX_DEF,
    QA_EN_CURSO_TTL_MIN_DEF,
    QA_FUENTE_TIMEOUT_DEF,
    RENDIMIENTO_MIN_PIEZAS_DEF,
    RENDIMIENTO_TOP_N_DEF,
    SCORE_BONUS_BREAKING_DEF,
    SCORE_PESO_CORROBORACION_DEF,
    SCORE_PESO_FRESCURA_DEF,
    SCORE_PESO_MARCA_DEF,
    SCORE_PESO_RENDIMIENTO_DEF,
    SCORE_PESO_VELOCIDAD_DEF,
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


def recolectar_activo() -> bool:
    """True si el motor de ingesta persistente debe sondear feeds (`KENI_PIPELINE_RECOLECTAR`).

    Def OFF (CI/tests): sin el flag, el hilo arranca pero no sondea nada. Se ACTIVA en
    producción (deploy: `KENI_PIPELINE_RECOLECTAR=1`) para que el archivo de artículos esté siempre al día.
    SOLO LEE feeds públicos y persiste artículos; no genera ni publica nada.
    """
    return _crudo(ENV_PIPELINE_RECOLECTAR).lower() in _VERDADEROS


def clasificar_marca_ia() -> bool:
    """True si un BREAKING sin marca se clasifica con Haiku (`KENI_CLASIFICAR_MARCA_IA`).

    Def OFF: la clasificación por IA gasta tokens, así que se activa a propósito. Con OFF el
    comportamiento es el de siempre (solo encaje por vocabulario); los breakings que no casen
    siguen sin marca hasta encenderlo.
    """
    return _crudo(ENV_CLASIFICAR_MARCA_IA).lower() in _VERDADEROS


def marcas_activas() -> list[str]:
    """Marcas CANDIDATAS del encaje automático (`KENI_MARCAS_ACTIVAS`, CSV de ids; def piloto).

    Orden estable y sin duplicados. NO valida contra el catálogo (lo hace quien la usa): así
    este módulo no importa `marcas` y evita ciclos.
    """
    crudo = _crudo(ENV_MARCAS_ACTIVAS) or MARCAS_ACTIVAS_DEF
    vistas: list[str] = []
    for parte in crudo.split(","):
        m = parte.strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas


def marca_noticias() -> str:
    """Marca de NOTICIAS GENERALES (catch-all del encaje) (`KENI_MARCA_NOTICIAS`, def 'unotv')."""
    return (_crudo(ENV_MARCA_NOTICIAS) or MARCA_NOTICIAS_DEF).strip()


def ingesta_batch() -> int:
    """Máximo de feeds a sondear por barrido (`KENI_INGESTA_BATCH`, def 40, min 1)."""
    return _entero(ENV_INGESTA_BATCH, INGESTA_BATCH_DEF, minimo=1)


def ingesta_workers() -> int:
    """Descargas de feeds en paralelo por barrido (`KENI_INGESTA_WORKERS`, def 12, min 1)."""
    return _entero(ENV_INGESTA_WORKERS, INGESTA_WORKERS_DEF, minimo=1)


def ingesta_max_items() -> int:
    """Artículos a archivar por feed y sondeo (`KENI_INGESTA_MAX_ITEMS`, def 100, min 1)."""
    return _entero(ENV_INGESTA_MAX_ITEMS, INGESTA_MAX_ITEMS_DEF, minimo=1)


# FILTRO DE ENTRADA por vocabulario de marca (la puerta del pool). Def ON: un feed asignado a
# una marca solo archiva items que casan >= 1 término de la agenda de esa marca. Exentos los
# feeds PROPIOS, los compartidos (sin marca) y las marcas sin vocabulario (sin criterio no se
# filtra). Lo descartado se CUENTA por sondeo (`ultimo_filtrados`, visible en /salud).
ENV_INGESTA_FILTRO = "KENI_INGESTA_FILTRO"


def ingesta_filtro_activo() -> bool:
    """True si el filtro de ENTRADA por vocabulario está activo (`KENI_INGESTA_FILTRO`, def ON).

    Def ON (a diferencia de las etapas IA): no gasta recursos ni borra nada ya archivado, solo
    deja de ARCHIVAR contenido irrelevante nuevo. `0`/`no`/`off` lo apaga (se archiva todo, como antes).
    """
    crudo = _crudo(ENV_INGESTA_FILTRO).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


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

    Agrupación INCREMENTAL: solo se cargan los clusters cuya `ultimo_visto` cae en esta ventana
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


def cluster_umbral_merge() -> float:
    """Umbral fuzzy del MERGE LÉXICO TARDÍO (`KENI_CLUSTER_UMBRAL_MERGE`, def 0.86; 0 apaga).

    Fundir dos historias YA formadas pide más certeza que unir un item suelto, por eso el
    default es más estricto que `cluster_umbral` (0.86 vs 0.82). Valor inválido/fuera de
    [0,1] → def.
    """
    crudo = _crudo(ENV_CLUSTER_UMBRAL_MERGE)
    if not crudo:
        return CLUSTER_UMBRAL_MERGE_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return CLUSTER_UMBRAL_MERGE_DEF
    if valor < 0.0 or valor > 1.0:
        return CLUSTER_UMBRAL_MERGE_DEF
    return valor


def cluster_breaking_fuentes() -> int:
    """Umbral breaking por conteo de fuentes (`KENI_CLUSTER_BREAKING_FUENTES`, def 3, min 2)."""
    return _entero(ENV_CLUSTER_BREAKING_FUENTES, CLUSTER_BREAKING_FUENTES_DEF, minimo=2)


def cluster_breaking_peso() -> float:
    """Masa PONDERADA mínima (Σ peso por outlet) en la ventana actual para marcar "breaking".

    (`KENI_CLUSTER_BREAKING_PESO`, def 3.0, min 1.0.) Con los pesos por defecto: 3 fuentes
    normales, 1 potente + 1 normal, o 2 potentes. COMPATIBILIDAD: si el peso NO está fijado
    pero el umbral legado por conteo (`KENI_CLUSTER_BREAKING_FUENTES`) sí, se mapea
    (peso = conteo) para no cambiar el comportamiento de un despliegue ya configurado.
    """
    crudo = _crudo(ENV_CLUSTER_BREAKING_PESO).strip()
    if not crudo and _crudo(ENV_CLUSTER_BREAKING_FUENTES).strip():
        return float(cluster_breaking_fuentes())
    if not crudo:
        return CLUSTER_BREAKING_PESO_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return CLUSTER_BREAKING_PESO_DEF
    return max(1.0, valor)


def cluster_breaking_ventana_h() -> int:
    """Ventana (horas) para la heurística de breaking (`KENI_CLUSTER_BREAKING_VENTANA_H`, def 6, min 1)."""
    return _entero(ENV_CLUSTER_BREAKING_VENTANA_H, CLUSTER_BREAKING_VENTANA_H_DEF, minimo=1)


def breaking_extra_dia() -> int:
    """Tope EXTRA diario de breaking sobre el plan (`KENI_BREAKING_EXTRA_DIA`, def 4, min 0).

    Una última hora corroborada sale al feed aunque su línea del plan esté llena: el cupo es
    techo para lo normal, no para la última hora. Este tope acota el exceso (un día muy
    movido no se desboca); `0` = el plan vuelve a ser techo duro también para breaking.
    """
    return _entero(ENV_BREAKING_EXTRA_DIA, BREAKING_EXTRA_DIA_DEF, minimo=0)


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


# Peso AUTOMÁTICO de la señal de rendimiento cuando `KENI_RENDIMIENTO_RANKING` está ON pero
# `KENI_SCORE_PESO_RENDIMIENTO` no se fijó explícitamente. Los demás pesos se RENORMALIZAN
# por (1 - auto) para que la combinación lineal siga sumando ~1.
SCORE_PESO_RENDIMIENTO_AUTO = 0.10


def score_pesos():
    """Pesos del algoritmo de ponderación del score de cluster, como `agrupar.PesosScore`.

    Lee cada peso del store/env (clamp [0,1]; default = los de `clustering`). El daemon de Recolectar
    inyecta el resultado en `agrupar.puntuar` para que el equipo afine la jerarquización desde
    la consola sin tocar código. Import perezoso de `dominio.agrupar` para evitar ciclos.

    Señal de RENDIMIENTO (Fase 2c): si el flag `KENI_RENDIMIENTO_RANKING` está ON y el peso NO
    se fijó explícitamente, se aplica `SCORE_PESO_RENDIMIENTO_AUTO` (0.10) renormalizando la
    combinación lineal (corroboración/frescura/viralidad/marca × 0.90): encender el flag SIEMPRE
    tiene efecto. Un peso explícito (store/env) manda y no renormaliza nada.
    """
    from .dominio.agrupar import PesosScore

    corroboracion = _peso01(ENV_SCORE_PESO_CORROBORACION, SCORE_PESO_CORROBORACION_DEF)
    velocidad = _peso01(ENV_SCORE_PESO_VELOCIDAD, SCORE_PESO_VELOCIDAD_DEF)
    frescura = _peso01(ENV_SCORE_PESO_FRESCURA, SCORE_PESO_FRESCURA_DEF)
    viralidad = _peso01(ENV_SCORE_PESO_VIRALIDAD, SCORE_PESO_VIRALIDAD_DEF)
    marca = _peso01(ENV_SCORE_PESO_MARCA, SCORE_PESO_MARCA_DEF)
    rendimiento = _peso01(ENV_SCORE_PESO_RENDIMIENTO, SCORE_PESO_RENDIMIENTO_DEF)
    if rendimiento_ranking_activo() and not _crudo(ENV_SCORE_PESO_RENDIMIENTO).strip():
        rendimiento = SCORE_PESO_RENDIMIENTO_AUTO
        factor = 1.0 - rendimiento
        corroboracion *= factor
        velocidad *= factor
        frescura *= factor
        viralidad *= factor
        marca *= factor
    return PesosScore(
        corroboracion=corroboracion,
        velocidad=velocidad,
        frescura=frescura,
        viralidad=viralidad,
        marca=marca,
        breaking=_peso01(ENV_SCORE_BONUS_BREAKING, SCORE_BONUS_BREAKING_DEF),
        rendimiento=rendimiento,
    )


# Umbral de DIVERSIDAD de la admisión a tema (MMR suave sobre el top-N de historias): dos títulos
# con ratio fuzzy >= umbral se consideran el mismo macro-tema y el segundo cede su plaza (si
# quedan plazas libres al final, se rellenan igual). 0 desactiva. Activado SUAVE por defecto.
ENV_PROMOVER_DIVERSIDAD_UMBRAL = "KENI_PROMOVER_DIVERSIDAD_UMBRAL"
PROMOVER_DIVERSIDAD_UMBRAL_DEF = 0.80


def promover_diversidad_umbral() -> float:
    """Umbral [0,1] de similitud de título para la admisión DIVERSA a tema.

    (`KENI_PROMOVER_DIVERSIDAD_UMBRAL`, def 0.80.) `0` desactiva la diversidad (top-N puro por
    score). Valor inválido → def. Suave: nunca reduce el número de historias promovidas.
    """
    return _peso01(ENV_PROMOVER_DIVERSIDAD_UMBRAL, PROMOVER_DIVERSIDAD_UMBRAL_DEF)


# UMBRAL de producción automática: el panel LISTA todo el pool jerarquizado, pero PROMOVER una
# historia a tema (que acaba en Verificar+Redactar con `claude -p`: coste real de tokens) exige un umbral
# más alto y explicable. Defaults en `dominio.agrupar` (capa pura); editables en caliente.
ENV_PROMOVER_MIN_SCORE = "KENI_PROMOVER_MIN_SCORE"
ENV_PROMOVER_MIN_MARCA = "KENI_PROMOVER_MIN_MARCA"


def promover_min_score() -> float:
    """Score mínimo [0,1] para que una historia dispare producción automática
    (`KENI_PROMOVER_MIN_SCORE`, def 0.35). `0` desactiva el umbral de score. Valor inválido → def."""
    from .dominio.agrupar import UMBRAL_MIN_SCORE_DEF

    return _peso01(ENV_PROMOVER_MIN_SCORE, UMBRAL_MIN_SCORE_DEF)


def promover_min_marca() -> float:
    """Encaje de marca mínimo [0,1] (relevancia por vocabulario) para la producción automática
    (`KENI_PROMOVER_MIN_MARCA`, def 0.2 ≈ 1 término del vocabulario). `0` desactiva el umbral de
    marca. Exentas: historias curadas por el equipo y breaking corroboradas (ver
    `agrupar.evaluar_umbral`). Valor inválido → def."""
    from .dominio.agrupar import UMBRAL_MIN_MARCA_DEF

    return _peso01(ENV_PROMOVER_MIN_MARCA, UMBRAL_MIN_MARCA_DEF)


# --------------------------------------------------------------------------- #
# Cupos de producción automática (volumen ≈ cadencia real de cada marca)       #
# --------------------------------------------------------------------------- #

# Admitir sin cupo produce al ritmo de Recolectar (cientos de noticias/día → cientos de
# temas/día), muy por encima de lo que una marca publica de verdad. El PLAN EDITORIAL DIARIO
# (`plan_dia`) reparte el objetivo del día en cupos POR CATEGORÍA («lo mejor de cada tipo»,
# con slots explícitos para breaking); para marcas sin plan, `cupo_dia` pone un techo simple.
ENV_PROMOVER_MADURACION_MIN = "KENI_PROMOVER_MADURACION_MIN"
PROMOVER_MADURACION_MIN_DEF = 45
ENV_CUPO_DIA = "KENI_CUPO_DIA"
CUPO_DIA_DEF = 16
ENV_PLAN_DIA = "KENI_PLAN_DIA"


def promover_maduracion_min() -> int:
    """Minutos mínimos de una historia en el pool antes de poder promoverse
    (`KENI_PROMOVER_MADURACION_MIN`, def 45, min 0; `0` desactiva). Exentas las curadas y las
    breaking corroboradas (regla en `agrupar.evaluar_umbral`): la urgencia real no espera.
    Dedicar este tiempo a "elegir" deja que la corroboración se acumule y que Admitir
    compare historias maduras, no primeras llegadas."""
    return _entero(ENV_PROMOVER_MADURACION_MIN, PROMOVER_MADURACION_MIN_DEF, minimo=0)


def _entero_marca(env_flag: str, marca: str, defecto: int, *, minimo: int) -> int:
    """Entero con override POR MARCA: lee `ENV::marca` y cae a `ENV` (mismo sufijo `::` que
    los toggles de etapa). El override hereda el valor global si falta o no parsea."""
    base = _entero(env_flag, defecto, minimo=minimo)
    if not marca:
        return base
    return _entero(f"{env_flag}::{marca}", base, minimo=minimo)


def cupo_dia(marca: str = "") -> int:
    """Máx. temas AUTO-PRODUCIDOS por marca en 24 h móviles (`KENI_CUPO_DIA`, def 16, min 0).

    `0` = sin cupo diario. Override por marca: `KENI_CUPO_DIA::<marca>`. Ventana MÓVIL de
    24 h (no día calendario): sin efecto frontera a medianoche (UTC ≠ CDMX) y sin ráfaga al
    cambiar de día. Calibrado con la cadencia real de publicación de la marca (Metricool):
    cada tema abre ~3 piezas (IG/X/FB), así que cupo_dia≈24 ≈ 70-75 posts/día."""
    return _entero_marca(ENV_CUPO_DIA, marca, CUPO_DIA_DEF, minimo=0)


def parsear_plan(crudo: str) -> dict[str, int]:
    """Parsea un plan editorial "categoria:n, categoria:n, …" a dict. PURA y tolerante.

    Segmentos malformados o con n<=0 se IGNORAN (un plan a medias vale más que ninguno).
    Las categorías se normalizan a minúsculas. {} si el texto no aporta ningún cupo.
    """
    plan: dict[str, int] = {}
    for trozo in (crudo or "").split(","):
        if ":" not in trozo:
            continue
        cat, _, n = trozo.partition(":")
        cat = cat.strip().lower()
        try:
            cupo = int(n.strip())
        except ValueError:
            continue
        if cat and cupo > 0:
            plan[cat] = cupo
    return plan


def plan_dia(marca: str = "") -> dict[str, int]:
    """PLAN EDITORIAL DIARIO de una marca: cupos por CATEGORÍA (`KENI_PLAN_DIA[::marca]`).

    Formato "categoria:n,…" (p. ej. "mx:4,internacional:4,breaking:2,entretenimiento:2,
    evergreen:1" = el objetivo diario de UnoTV). Con plan, Admitir llena cada cupo
    con LAS MEJORES historias de esa categoría (las breaking corroboradas consumen el cupo
    'breaking' sea cual sea su categoría de feed) y Recolectar salta los feeds de categorías
    fuera del plan. Categorías sin pool (p. ej. 'evergreen') reservan el hueco para el flujo
    manual ('evergreen' lo llena su automatismo diario). {} = sin plan (cae al cupo diario
    global, `cupo_dia`). El override por marca SUSTITUYE al global (no se mezclan)."""
    if marca:
        propio = _crudo(f"{ENV_PLAN_DIA}::{marca}")
        if propio:
            return parsear_plan(propio)
    return parsear_plan(_crudo(ENV_PLAN_DIA))


# --------------------------------------------------------------------------- #
# Señal de rendimiento en la priorización (líneas que mejor funcionan) — Fase 2c #
# --------------------------------------------------------------------------- #


def rendimiento_ranking_activo() -> bool:
    """True si la priorización sube las historias de las líneas que mejor rinden (`KENI_RENDIMIENTO_RANKING`).

    Def OFF: sin el flag, el daemon no calcula la señal de rendimiento (queda inerte aunque tenga
    peso). Con el flag, calcula las líneas top por engagement (Metricool) y empuja las historias
    de esas líneas. Anti-sesgo: muestra mínima por línea + tope N (ver accesores).
    """
    return _crudo(ENV_RENDIMIENTO_RANKING).lower() in _VERDADEROS


def rendimiento_top_n() -> int:
    """Cuántas líneas top se premian (`KENI_RENDIMIENTO_TOP_N`, def 3, min 1)."""
    return _entero(ENV_RENDIMIENTO_TOP_N, RENDIMIENTO_TOP_N_DEF, minimo=1)


def rendimiento_min_piezas() -> int:
    """Muestra mínima de piezas medidas para que una línea cuente como top (anti-sesgo)
    (`KENI_RENDIMIENTO_MIN_PIEZAS`, def 5, min 1): evita encaramar una línea que 'funcionó una vez'."""
    return _entero(ENV_RENDIMIENTO_MIN_PIEZAS, RENDIMIENTO_MIN_PIEZAS_DEF, minimo=1)


# --------------------------------------------------------------------------- #
# GC del pool de noticias por relevancia (no por edad sola)                     #
# --------------------------------------------------------------------------- #


def noticias_gc_activo() -> bool:
    """True si el GC del pool de noticias debe BARRER (`KENI_NOTICIAS_GC`, def OFF).

    Conservador: sin el flag NO se borra ninguna noticia. Con el flag, un hilo demonio purga el
    contenido irrelevante de baja relevancia (ver `db_noticias.purgar_pool_irrelevante`) cada N horas.
    """
    return _crudo(ENV_NOTICIAS_GC).lower() in _VERDADEROS


def noticias_gc_intervalo_horas() -> int:
    """Cada cuántas horas barre el GC del pool (`KENI_NOTICIAS_GC_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_NOTICIAS_GC_INTERVALO_HORAS, NOTICIAS_GC_INTERVALO_HORAS_DEF, minimo=1)


def noticias_gc_score_umbral() -> float:
    """Score por debajo del cual una historia de UNA fuente es "irrelevante" purgable
    (`KENI_NOTICIAS_GC_SCORE_UMBRAL`, def 0.15, clamp [0,1]). 0 = no purgar por score."""
    return _peso01(ENV_NOTICIAS_GC_SCORE_UMBRAL, NOTICIAS_GC_SCORE_UMBRAL_DEF)


def noticias_gc_inactividad_horas() -> int:
    """Horas SIN actividad para que una historia de baja relevancia sea purgable
    (`KENI_NOTICIAS_GC_INACTIVIDAD_HORAS`, def 48, min 1). Guarda contra purgar lo recién visto."""
    return _entero(
        ENV_NOTICIAS_GC_INACTIVIDAD_HORAS, NOTICIAS_GC_INACTIVIDAD_HORAS_DEF, minimo=1
    )


# CADUCIDAD del pool (TTL + retención): a diferencia del GC por relevancia (selectivo y
# gateado, def OFF), la caducidad es el RELOJ del feed y va encendida por defecto — una
# noticia sin actividad en días no es feed, es archivo muerto. El TTL solo cambia ESTADO
# (reversible); la retención sí borra (lo ya caducado, tras un margen largo).
ENV_NOTICIAS_TTL_H = "KENI_NOTICIAS_TTL_H"
NOTICIAS_TTL_H_DEF = 72  # = vida de la frescura del score: sin frescura, fuera del feed
ENV_NOTICIAS_RETENCION_H = "KENI_NOTICIAS_RETENCION_H"
NOTICIAS_RETENCION_H_DEF = 336  # 14 días: margen sobrado para auditar qué caducó


def noticias_ttl_horas() -> int:
    """Horas sin actividad para que una historia `nuevo` no usada CADUQUE sola
    (`KENI_NOTICIAS_TTL_H`, def 72; 0 = sin caducidad). Soft: pasa a `descartado`."""
    return _entero(ENV_NOTICIAS_TTL_H, NOTICIAS_TTL_H_DEF, minimo=0)


def noticias_retencion_horas() -> int:
    """Horas tras las que lo CADUCADO sin usar se borra de verdad (techo del archivo)
    (`KENI_NOTICIAS_RETENCION_H`, def 336 = 14 días; 0 = no borrar nunca)."""
    return _entero(ENV_NOTICIAS_RETENCION_H, NOTICIAS_RETENCION_H_DEF, minimo=0)


# --------------------------------------------------------------------------- #
# Perfil editorial por marca (Haiku desde libtexto) — Fase 2                    #
# --------------------------------------------------------------------------- #


def priorizar_perfil_activo() -> bool:
    """True si la priorización usa el perfil de relevancia extraído con Haiku (`KENI_PRIORIZAR_PERFIL_IA`).

    Def OFF (conservador, IA en prod): sin el flag la priorización usa el vocabulario base
    (`relevancia_marca`). Con el flag, el daemon refresca el perfil por marca (Haiku, TTL) y el
    score usa esas keywords derivadas de la línea editorial de la página texto.
    """
    return _crudo(ENV_PRIORIZAR_PERFIL_IA).lower() in _VERDADEROS


def perfil_editorial_ttl_horas() -> int:
    """Cada cuántas horas se re-extrae el perfil editorial con Haiku
    (`KENI_PERFIL_EDITORIAL_TTL_HORAS`, def 24, min 1). También se refresca si cambia la editorial."""
    return _entero(ENV_PERFIL_EDITORIAL_TTL_HORAS, PERFIL_EDITORIAL_TTL_HORAS_DEF, minimo=1)


# --------------------------------------------------------------------------- #
# Fusionar (semántica) historias (Haiku) — Fase 2b                             #
# --------------------------------------------------------------------------- #


def fusionar_semantica_activo() -> bool:
    """True si se funden con IA las historias del mismo evento (`KENI_PIPELINE_FUSIONAR`, def OFF).

    Def OFF (IA que MUTA el pool en prod): sin el flag, la agrupación se queda en el léxico. Con el
    flag, el daemon manda a Haiku las historias recientes por marca y funde los grupos del mismo
    acontecimiento (conservador: ante duda no fusiona).
    """
    return _crudo(ENV_PIPELINE_FUSIONAR).lower() in _VERDADEROS


def fusion_semantica_max() -> int:
    """Máx. historias por marca y barrido que se mandan a Haiku a agrupar
    (`KENI_FUSION_SEMANTICA_MAX`, def 40, min 2). Acota coste y tamaño de contexto."""
    return _entero(ENV_FUSION_SEMANTICA_MAX, FUSION_SEMANTICA_MAX_DEF, minimo=2)



# --------------------------------------------------------------------------- #
# Monitor de cobertura + Traducir completo + auto-verificación (Ola D)          #
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

    0 = traducir TODO cluster extranjero reciente; subirlo limita Traducir a las historias
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
    """True si el daemon del pipeline de contenido debe BARRER (`KENI_PIPELINE_REDACTAR`).

    Def OFF (conservador): sin el flag el comportamiento existente NO cambia (nada se recolecta/
    genera por el pipeline). Con el flag a un valor afirmativo, un hilo demonio ejecuta cada N
    horas el flujo Admitir→Redactar→Revisar por marca y deja borradores en la cola de revision. Nada se publica
    solo (sigue gated). El hilo arranca SIEMPRE pero, gateado, solo actua con el flag activo.
    """
    return _crudo(ENV_PIPELINE_REDACTAR).lower() in _VERDADEROS


# FLUJO CONTINUO: el pipeline ya no tiene intervalo configurable (tick corto constante en
# `pipeline_contenido._barrido`) ni topes por etapa (Verificar/Redactar/Ilustrar/Revisar): el volumen lo
# regulan los DOS knobs de Admitir de abajo + el backpressure de la cola (`KENI_MAX_JOBS`).


def pipeline_max() -> int:
    """Máximo de historias que Admitir admite por marca en cada pasada
    (`KENI_PIPELINE_MAX`, def 3, min 1). Cada admisión acaba en `claude -p` (coste)."""
    return _entero(ENV_PIPELINE_MAX, PIPELINE_MAX_DEF, minimo=1)


def pipeline_en_proceso_max() -> int:
    """WIP del gate SERIAL: piezas EN CURSO por marca (`KENI_PIPELINE_EN_PROCESO_MAX`, def 8, min 1).

    ES el regulador del flujo continuo (in=out): Admitir no admite más historias de una
    marca mientras ésta tenga >= esto sin terminar (Verificar pendiente o verificado sin copy); primero se
    COMPLETA lo que entró, luego entran nuevas.
    """
    return _entero(ENV_PIPELINE_EN_PROCESO_MAX, PIPELINE_EN_PROCESO_MAX_DEF, minimo=1)


def pipeline_fetch_fuente() -> bool:
    """True si la ingesta debe DESCARGAR el cuerpo del artículo para la nota (`KENI_PIPELINE_FETCH_FUENTE`).

    Def OFF (conservador): sin el flag la nota de origen es título+resumen (snippet RSS) como
    hasta ahora. Con el flag, antes de encolar el copy el daemon baja el cuerpo del/los
    artículo(s) y, en clusters, agrega el texto de CADA fuente —no solo sus URLs—, dándole a
    `claude -p` material real para sintetizar sin gastar turnos en WebFetch. Best-effort: un
    fetch que falle cae a título+resumen.
    """
    return _crudo(ENV_PIPELINE_FETCH_FUENTE).lower() in _VERDADEROS


def pipeline_tema_ttl_horas() -> int:
    """TTL (horas) de un tema EN CURSO del pipeline (`KENI_PIPELINE_TEMA_TTL_HORAS`, def 24, min 1).

    El pipeline es una VENTANA DESLIZANTE sobre la priorización de noticias frescas, sin colas
    intermedias: lo que no completó sus fases dentro del TTL CADUCA (libera su hueco del gate
    serial y no genera copy). Lo de ayer no entra hoy; hoy entra lo de hoy.
    """
    return _entero(ENV_PIPELINE_TEMA_TTL_HORAS, PIPELINE_TEMA_TTL_HORAS_DEF, minimo=1)


def verificar_activo() -> bool:
    """True si la ETAPA de Verificar del pipeline debe verificar la fuente (`KENI_PIPELINE_VERIFICAR`, "Verificar").

    Def OFF (conservador, como el resto de etapas): sin el flag NO se verificación y la etapa aparece
    "Saltada"; el copy se genera igual. Con el flag, antes de redactar el copy un `claude -p` evalúa
    la nota de origen (verificación pre-copy). Toggle PROPIO por marca: 1 toggle = 1 etapa.
    """
    return _crudo(ENV_PIPELINE_VERIFICAR).lower() in _VERDADEROS


def qa_fuente_modelo() -> str:
    """Modelo de claude de la VERIFICACIÓN de la fuente (`KENI_QA_FUENTE_MODELO`, def "haiku").

    La verificación de Verificar es un filtro PERMISIVO (no redaccion): por defecto corre con un modelo
    rapido/economico. Mismas semanticas que `insumos_modelo`: var no fijada -> "haiku";
    fijada a "" -> sin `--model` (default de claude); fijada a un valor -> ese modelo.
    """
    raw = os.environ.get(ENV_QA_FUENTE_MODELO)
    if raw is None:
        return "haiku"
    return raw.strip()


def qa_fuente_esfuerzo() -> str:
    """Esfuerzo (thinking) de la verificación de la fuente (`KENI_QA_FUENTE_ESFUERZO`, def "low").

    "" (explicito) = sin override (cae a la preferencia global). El valor se valida contra
    `preferencias.ESFUERZOS_VALIDOS` en el armado del argv (un valor invalido se ignora).
    """
    raw = os.environ.get(ENV_QA_FUENTE_ESFUERZO)
    if raw is None:
        return "low"
    return raw.strip()


def qa_fuente_timeout() -> int:
    """Wall-timeout (s) de la verificación de la fuente (`KENI_QA_FUENTE_TIMEOUT`, def 180, min 0).

    0 = sin override (se usa el global `KENI_CLAUDE_TIMEOUT`). El override solo ENDURECE:
    el runner lo topa con `min(global, override)`.
    """
    return _entero(ENV_QA_FUENTE_TIMEOUT, QA_FUENTE_TIMEOUT_DEF, minimo=0)


def qa_en_curso_ttl_seg() -> int:
    """TTL (s) del limpiador de temas `verificar_veredicto='en_curso'` sueltos (`KENI_QA_EN_CURSO_TTL_MIN`).

    Def 30 min (muy superior al timeout de la verificación, asi nunca toca una verificación viva). El recolector
    resetea a "" los `en_curso` mas viejos para que vuelvan a la re-verificación del barrido.
    """
    return _entero(ENV_QA_EN_CURSO_TTL_MIN, QA_EN_CURSO_TTL_MIN_DEF, minimo=5) * 60


def alguna_etapa_investigacion_activa() -> bool:
    """Gate del loop de INVESTIGACIÓN (ADR 0011 F3): True si hay trabajo de investigación que
    considerar bajo la máquina.

    El loop de investigación (caducidad + Admitir + Verificar) solo tiene sentido si su admisión o su verificación
    están encendidas: con Recolectar Y Verificar globales OFF no entra nada nuevo ni se verificación, y
    el loop duerme (la caducidad de lo ya en curso retoma en cuanto se reactive). El override por
    marca se aplica DENTRO del barrido (`etapa_activa`), no aquí: basta una marca activa para que
    el loop barra. Las etapas de Fusionar/Priorizar viven en el daemon de Recolectar, no en este loop.
    """
    return etapa_global_activa(ENV_PIPELINE_RECOLECTAR) or etapa_global_activa(ENV_PIPELINE_VERIFICAR)


def alguna_etapa_produccion_activa() -> bool:
    """Gate del loop de PRODUCCIÓN (ADR 0011 F3): siempre True bajo la máquina.

    La etapa de AVANCE (borradores completos → cola de revisión) corre INCONDICIONALMENTE, así
    que siempre hay trabajo de producción que considerar y el loop nunca debe quedarse dormido
    mientras la máquina esté ON. Las fases que sí gastan `claude -p` (Redactar/Ilustrar) se auto-gatean
    DENTRO del barrido por su propio flag global + override por-marca: si están OFF no hacen
    nada, pero el barrido igual corre para drenar los borradores completos a revisión.
    """
    return True


alguna_etapa_pipeline_activa = alguna_etapa_produccion_activa


def revisar_activo() -> bool:
    """True si la ETAPA de Revisar el copy debe verificar antes del avance (`KENI_PIPELINE_REVISAR`).

    Def OFF (conservador, como el resto de etapas): sin el flag el avance a revisión no cambia.
    Con el flag, antes de mover un borrador completo a la cola de revisión la IA "hacia adentro"
    verifica la VOZ del copy contra los patrones medidos de la marca (+ coherencia barata con la
    nota de origen). ADVISORY/safe-by-default: nunca bloquea ni descarta; si detecta algo, degrada
    el veredicto (`listo`→`revisar`) y deja una nota para que el humano decida.
    """
    return _crudo(ENV_PIPELINE_REVISAR).lower() in _VERDADEROS


def ilustrar_activo() -> bool:
    """True si la ETAPA de Ilustrar del pipeline debe ilustrar (`KENI_PIPELINE_ILUSTRAR`, "Ilustrar").

    Def OFF (conservador): el equipo hace la imagen a mano. Con el flag, la etapa de Ilustrar del
    pipeline (tras la de Redactar) genera imagen por IA para los temas con copy pero sin imagen y
    la adjunta. Sin proveedor de imagen configurado, no hace nada (degrada).
    """
    return _crudo(ENV_PIPELINE_ILUSTRAR).lower() in _VERDADEROS


# --------------------------------------------------------------------------- #
# Toggle ÚNICO «Generar» (noticia → copy)                                       #
# --------------------------------------------------------------------------- #

# CLAVE VIRTUAL del catálogo/UI: el equipo enciende/apaga UN solo interruptor «Generar»
# («o llega copy o no empieza») y la capa de ajustes lo TRADUCE a las cinco etapas internas
# de la fase noticia→copy. Las etapas siguen existiendo como mecanismo (daemons, vista
# Pipelines, tests) pero dejan de ser botones: la única etapa con interruptor propio es
# Ilustrar (la única con coste externo real). Estas claves VIRTUALES nunca se leen en runtime:
# las lecturas siguen siendo por etapa; la API de ajustes escribe las claves físicas a la vez.
#
# DOS PROCESOS (ADR 0011): la máquina se gobierna con dos maestros, no con un único «Generar».
#   - INVESTIGACIÓN: noticia recolectada, deduplicada, priorizada y VERIFICADA (el pool listo).
#   - PRODUCCIÓN: la noticia verificada se convierte en pieza (copy). Ilustrar conserva su propio
#     interruptor (única etapa con coste externo real); el AVANCE a revisión corre siempre.
ENV_INVESTIGACION = "KENI_INVESTIGACION"
ENV_PRODUCCION = "KENI_PRODUCCION"

# Etapas que agrupa cada maestro (orden de pipeline). Solo las que admiten override por marca
# (`etapa_activa`) entran en el fan-out, para que el toggle por marca sea simétrico. La
# Clasificar marca IA y la priorización por rendimiento son flags propios de Investigación
# (no per-marca) y se muestran aparte, no en el fan-out del maestro.
ETAPAS_INVESTIGACION: tuple[str, ...] = (
    ENV_PIPELINE_RECOLECTAR,
    ENV_PIPELINE_FUSIONAR,
    ENV_PRIORIZAR_PERFIL_IA,
    ENV_PIPELINE_VERIFICAR,
)
ETAPAS_PRODUCCION: tuple[str, ...] = (ENV_PIPELINE_REDACTAR,)


def _accesor_global_de_etapa(env_flag: str):
    """Accesor del maestro GLOBAL de una etapa del pipeline por su env (`KENI_PIPELINE_<ETAPA>`).

    Mapa ÚNICO etapa→accesor: lo comparten el resolver de abajo y el catálogo de ajustes
    (que usa el global como defecto del toggle por marca). `ValueError` si la env no es
    una etapa del pipeline (error de programación, no de datos).
    """
    try:
        return {
            ENV_PIPELINE_FUSIONAR: fusionar_semantica_activo,
            ENV_PRIORIZAR_PERFIL_IA: priorizar_perfil_activo,
            ENV_PIPELINE_RECOLECTAR: recolectar_activo,
            ENV_PIPELINE_VERIFICAR: verificar_activo,
            ENV_PIPELINE_REDACTAR: pipeline_activo,
            ENV_PIPELINE_ILUSTRAR: ilustrar_activo,
        }[env_flag]
    except KeyError:
        raise ValueError(f"'{env_flag}' no es una etapa del pipeline de contenido.") from None


def etapa_global_activa(env_flag: str) -> bool:
    """Maestro GLOBAL de la etapa `env_flag` (ON/OFF para todas las marcas). Lectura única."""
    return _accesor_global_de_etapa(env_flag)()


def etapa_activa(env_flag: str, marca: str) -> bool:
    """FUENTE ÚNICA de verdad de «¿la etapa `env_flag` está encendida para `marca`?».

    Una etapa corre para una marca si su maestro global está ON y la marca NO está excluida
    a mano (override `KENI_PIPELINE_<ETAPA>::marca` falsy en el store). La MISMA lectura la
    usan el daemon (qué barre), la vista Pipelines (qué se pinta «saltada») y el catálogo de
    ajustes (qué muestra el toggle): si una de las tres dijera otra cosa, sería un bug aquí,
    no tres semánticas paralelas.
    """
    from .config_produccion import marca_apagada  # local: evita ciclo de import en el barrel

    return etapa_global_activa(env_flag) and not marca_apagada(env_flag, marca)


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


def critica_ia_activa() -> bool:
    """True si la cadena del feed lleva el nivel "Crítica IA" al final (`KENI_CRITICA_IA`).

    Def OFF (conservador): sin el flag, el flujo es el de hoy (dos OK humanos → programado). Con
    el flag, `enviar_a_revision` añade un tercer nivel automático tras los humanos; al cerrar los
    humanos su parte, se encola un `claude -p` con visión que critica la pieza y vota ese nivel.
    Respeta precedencia store>env>defecto; `KENI_CRITICA_IA=1`/`on`/`sí` lo enciende.
    """
    return _crudo(ENV_CRITICA_IA).lower() in _VERDADEROS


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
# Accesores: Traducir + tropicalización MX (Ola 4)                             #
# --------------------------------------------------------------------------- #


def traduccion_max() -> int:
    """Cap de temas extranjeros a traducir por request del Radar (`KENI_TRADUCCION_MAX`, def 15, min 1)."""
    return _entero(ENV_TRADUCCION_MAX, 15, minimo=1)
