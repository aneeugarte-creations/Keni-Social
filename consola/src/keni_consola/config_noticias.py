"""Config — accesores del dominio noticias. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    _VERDADEROS,
    CLUSTER_BREAKING_FUENTES_DEF,
    BREAKING_EXTRA_DIA_DEF,
    CLUSTER_BREAKING_PESO_DEF,
    CLUSTER_BREAKING_VENTANA_H_DEF,
    CLUSTER_VENTANA_H_DEF,
    ENV_AFP_BASE_URL,
    ENV_AFP_CLIENT_ID,
    ENV_AFP_CLIENT_SECRET,
    ENV_CRITICA_IA,
    ENV_MARCAS_ACTIVAS,
    ENV_MARCA_NOTICIAS,
    MARCA_NOTICIAS_DEF,
    ENV_CLUSTER_BREAKING_FUENTES,
    ENV_BREAKING_EXTRA_DIA,
    ENV_CLUSTER_BREAKING_PESO,
    ENV_CLUSTER_BREAKING_VENTANA_H,
    ENV_CLUSTER_VENTANA_H,
    ENV_FEED_SLA_MIN,
    ENV_FUENTES_BAJA_CONFIANZA,
    ENV_FUSION_SEMANTICA_MAX,
    ENV_FUSION_VENTANA_H,
    ENV_FUSION_INTERVALO_SEG,
    ENV_FUSION_MIN_SCORE,
    ENV_FUSION_COTEJAR,
    ENV_INGESTA_BATCH,
    ENV_INGESTA_INTERVALO_BREAKING,
    ENV_INGESTA_INTERVALO_DEFECTO,
    ENV_INGESTA_INTERVALO_DEPORTES,
    ENV_INGESTA_INTERVALO_GAMING,
    ENV_INGESTA_INTERVALO_INTERNACIONAL,
    ENV_INGESTA_INTERVALO_MX,
    ENV_INGESTA_INTERVALO_EVERGREEN,
    ENV_INGESTA_MAX_ERRORES,
    ENV_INGESTA_MAX_ITEMS,
    ENV_INGESTA_WORKERS,
    ENV_NOTICIAS_GC,
    ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
    ENV_NOTICIAS_GC_INTERVALO_HORAS,
    ENV_NOTICIAS_GC_SCORE_UMBRAL,
    ENV_PERFIL_EDITORIAL_TTL_HORAS,
    ENV_PIPELINE_ILUSTRAR,
    ENV_PIPELINE_DECISOR,
    ENV_PIPELINE_TRADUCIR,
    ENV_PIPELINE_ADMITIR,
    ENV_PORTAL_COPY_AUTO,
    ENV_PIPELINE_SUGERIR_HASHTAGS,
    ENV_PIPELINE_REVISAR,
    ENV_PIPELINE_REDACTAR,
    ENV_PIPELINE_EN_PROCESO_MAX,
    ENV_PIPELINE_FETCH_FUENTE,
    ENV_PIPELINE_TEMA_TTL_HORAS,
    ENV_PIPELINE_FUSIONAR,
    ENV_PIPELINE_MAX,
    ENV_PIPELINE_RECOLECTAR,
    ENV_PIPELINE_VERIFICAR,
    ENV_VERIFICACION_EN_CURSO_TTL_MIN,
    ENV_VERIFICACION_FUENTE_ESFUERZO,
    ENV_VERIFICACION_FUENTE_MODELO,
    ENV_VERIFICACION_FUENTE_TIMEOUT,
    ENV_PEXELS_API_KEY,
    ENV_PIPELINE_STOCK,
    ENV_PIXABAY_API_KEY,
    ENV_STOCK_FUENTES,
    ENV_PRIORIZAR_PERFIL_IA,
    ENV_RENDIMIENTO_MIN_PIEZAS,
    ENV_RENDIMIENTO_RANKING,
    ENV_RENDIMIENTO_TOP_N,
    ENV_REUTERS_API_KEY,
    ENV_REUTERS_BASE_URL,
    ENV_SCORE_BONUS_BREAKING,
    ENV_STOCK_MAX_BARRIDO,
    ENV_TRAD_LOTE,
    ENV_TRAD_MIN_SCORE,
    ENV_TRADUCCION_MAX,
    FEED_SLA_MIN_DEF,
    FUENTES_BAJA_CONFIANZA_DEF,
    FUSION_SEMANTICA_MAX_DEF,
    FUSION_VENTANA_H_DEF,
    FUSION_INTERVALO_SEG_DEF,
    FUSION_MIN_SCORE_DEF,
    INGESTA_BATCH_DEF,
    INGESTA_INTERVALO_BREAKING_DEF,
    INGESTA_INTERVALO_DEFECTO_DEF,
    INGESTA_INTERVALO_DEPORTES_DEF,
    INGESTA_INTERVALO_GAMING_DEF,
    INGESTA_INTERVALO_INTERNACIONAL_DEF,
    INGESTA_INTERVALO_MX_DEF,
    INGESTA_INTERVALO_EVERGREEN_DEF,
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
    VERIFICACION_EN_CURSO_TTL_MIN_DEF,
    VERIFICACION_FUENTE_TIMEOUT_DEF,
    RENDIMIENTO_MIN_PIEZAS_DEF,
    RENDIMIENTO_TOP_N_DEF,
    SCORE_BONUS_BREAKING_DEF,
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


def marcas_activas() -> list[str]:
    """Marcas de NOTICIAS candidatas del encaje automático de marca.

    Por defecto son las marcas con `tipo='noticias'` del catálogo —el flag noticias /
    contenido-propio que se edita en la página Marcas—: activar una marca como noticias basta
    para que entre al encaje, sin tocar variables de entorno ni listas hardcodeadas. Las de
    contenido propio (`tipo='propio'`) quedan fuera hasta que se activen ahí.

    `KENI_MARCAS_ACTIVAS` (CSV de ids) sigue disponible como override explícito (pruebas /
    escenarios acotados). Orden estable y sin duplicados.
    """
    crudo = (_crudo(ENV_MARCAS_ACTIVAS) or "").strip()
    if not crudo:
        from keni_shared import marcas as _marcas  # perezoso: evita el ciclo config <- marcas

        return _marcas.noticias()
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


# Cadencia por categoría: env var + defecto de cada una (segundos), para el accesor genérico.
_INGESTA_INTERVALOS: dict[str, tuple[str, int]] = {
    "breaking": (ENV_INGESTA_INTERVALO_BREAKING, INGESTA_INTERVALO_BREAKING_DEF),
    "deportes": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "futbol": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "motor": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "otros-deportes": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "mx": (ENV_INGESTA_INTERVALO_MX, INGESTA_INTERVALO_MX_DEF),
    "internacional": (ENV_INGESTA_INTERVALO_INTERNACIONAL, INGESTA_INTERVALO_INTERNACIONAL_DEF),
    "gaming": (ENV_INGESTA_INTERVALO_GAMING, INGESTA_INTERVALO_GAMING_DEF),
    # Cadencia EVERGREEN (~30 min): ciencia y tecnología + temáticas de misión de la Fundación.
    "ciencia-tech": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
    "salud": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
    "medio-ambiente": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
    "cultura": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
    "educacion": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
    "impacto-social": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
}


def ingesta_intervalo_categoria(categoria: str) -> int:
    """Cadencia (segundos) de sondeo para una categoría de feed.

    breaking y las categorías de deporte (futbol/motor/otros-deportes, knob común
    `KENI_INGESTA_INTERVALO_DEPORTES`) ~180s; mx/internacional ~600s; gaming ~1800s.
    Una categoría desconocida (o '') cae al defecto general (`KENI_INGESTA_INTERVALO_DEFECTO`,
    def 600s). Cada accesor es configurable por env y min 1s.
    """
    env, defecto = _INGESTA_INTERVALOS.get(
        (categoria or "").strip().lower(),
        (ENV_INGESTA_INTERVALO_DEFECTO, INGESTA_INTERVALO_DEFECTO_DEF),
    )
    return _entero(env, defecto, minimo=1)


# Cadencia de una LÍNEA -> env var + defecto (segundos). La línea dicta el ritmo de sus
# fuentes; reusa los mismos knobs que las categorías (deporte/general/evergreen).
_INTERVALOS_CADENCIA: dict[str, tuple[str, int]] = {
    "rapida": (ENV_INGESTA_INTERVALO_DEPORTES, INGESTA_INTERVALO_DEPORTES_DEF),
    "normal": (ENV_INGESTA_INTERVALO_DEFECTO, INGESTA_INTERVALO_DEFECTO_DEF),
    "evergreen": (ENV_INGESTA_INTERVALO_EVERGREEN, INGESTA_INTERVALO_EVERGREEN_DEF),
}


def intervalo_de_cadencia(cadencia: str) -> int:
    """Cadencia (segundos) de sondeo de las fuentes de una LÍNEA según su `cadencia`.

    'rapida' ~180s (deporte en vivo), 'normal' ~600s (noticia general), 'evergreen' ~1800s
    (cambio lento). Una cadencia desconocida (o '') cae a 'normal'. Configurable por env, min 1s.
    """
    env, defecto = _INTERVALOS_CADENCIA.get(
        (cadencia or "").strip().lower(),
        _INTERVALOS_CADENCIA["normal"],
    )
    return _entero(env, defecto, minimo=1)


def cluster_ventana_h() -> int:
    """Ventana reciente (horas) de agrupación de historias (`KENI_CLUSTER_VENTANA_H`, def 72, min 1).

    Agrupación INCREMENTAL: solo se cargan los clusters cuya `ultimo_visto` cae en esta ventana
    para decidir a cuál unir un item nuevo. Acota el trabajo por barrido (nunca el archivo entero).
    """
    return _entero(ENV_CLUSTER_VENTANA_H, CLUSTER_VENTANA_H_DEF, minimo=1)


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


# Perfiles de MÉRITO por marca (modelo v2: score = mérito × confianza). Cada marca pondera
# distinto las señales: Claro Sports es agenda+velocidad (Mundial); UnoTV frescura+velocidad
# (nacional, breaking); Nación Gamer y Piso 15 marca+viralidad (cultura/entretenimiento);
# Fundación marca+rendimiento (evergreen, menos urgente). `vida_h` afina la vida media de la
# frescura (un resultado deportivo caduca en horas; un reportaje dura días) y `piso` la
# confianza de una historia SIN corroborar (UnoTV más estricta con rumores; Fundación más laxa).
# Los 6 pesos de mérito se RENORMALIZAN a sumar 1.0 (mérito honesto: el techo alcanzable es 1.0).
SCORE_PERFILES_MARCA: dict[str, dict[str, float]] = {
    "claro-sports": {"frescura": 0.20, "marca": 0.15, "evento": 0.30, "viralidad": 0.10,
                     "velocidad": 0.20, "rendimiento": 0.05, "vida_h": 24.0, "piso": 0.50},
    "unotv": {"frescura": 0.30, "marca": 0.20, "evento": 0.10, "viralidad": 0.10,
              "velocidad": 0.25, "rendimiento": 0.05, "vida_h": 36.0, "piso": 0.45},
    "nacion-gamer": {"frescura": 0.20, "marca": 0.30, "evento": 0.10, "viralidad": 0.25,
                     "velocidad": 0.05, "rendimiento": 0.10, "vida_h": 72.0, "piso": 0.55},
    "piso-15": {"frescura": 0.15, "marca": 0.30, "evento": 0.10, "viralidad": 0.25,
                "velocidad": 0.05, "rendimiento": 0.15, "vida_h": 96.0, "piso": 0.60},
    "fundacion": {"frescura": 0.15, "marca": 0.35, "evento": 0.10, "viralidad": 0.10,
                  "velocidad": 0.05, "rendimiento": 0.25, "vida_h": 120.0, "piso": 0.60},
}
SCORE_PERFIL_DEF: dict[str, float] = {
    "frescura": 0.25, "marca": 0.25, "evento": 0.15, "viralidad": 0.15,
    "velocidad": 0.20, "rendimiento": 0.0, "vida_h": 72.0, "piso": 0.50,
}
_SCORE_PESOS_MERITO = ("frescura", "marca", "evento", "viralidad", "velocidad", "rendimiento")


def score_pesos(marca: str = ""):
    """Pesos y forma del score (modelo v2) para una marca, como `agrupar.PesosScore`.

    El score es `mérito × confianza`: `mérito` combina las señales de valor editorial (frescura,
    marca, evento, viralidad, velocidad, rendimiento) y se MULTIPLICA por la confianza derivada
    de la corroboración. Cada marca tiene su perfil (`SCORE_PERFILES_MARCA`; `SCORE_PERFIL_DEF`
    para marcas sin perfil). Import perezoso de `dominio.agrupar` para evitar ciclos.

    RENDIMIENTO (Fase 2c): solo cuenta si `KENI_RENDIMIENTO_RANKING` está ON; si está OFF su peso
    es 0 y el resto del mérito se renormaliza a sumar 1.0 (el techo alcanzable sigue siendo 1.0,
    sin hueco muerto). El bonus aditivo de breaking (`KENI_SCORE_BONUS_BREAKING`) sigue editable.
    """
    from .dominio.agrupar import PesosScore

    perfil = dict(SCORE_PERFILES_MARCA.get(marca) or SCORE_PERFIL_DEF)
    if not rendimiento_ranking_activo():
        perfil["rendimiento"] = 0.0
    suma = sum(perfil[k] for k in _SCORE_PESOS_MERITO)
    factor = (1.0 / suma) if suma > 0 else 0.0
    return PesosScore(
        frescura=perfil["frescura"] * factor,
        marca=perfil["marca"] * factor,
        evento=perfil["evento"] * factor,
        viralidad=perfil["viralidad"] * factor,
        velocidad=perfil["velocidad"] * factor,
        rendimiento=perfil["rendimiento"] * factor,
        breaking=_peso01(ENV_SCORE_BONUS_BREAKING, SCORE_BONUS_BREAKING_DEF),
        piso_confianza=float(perfil["piso"]),
        frescura_vida_h=float(perfil["vida_h"]),
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


def promover_min_score() -> float:
    """Score mínimo [0,1] para que una historia dispare producción automática
    (`KENI_PROMOVER_MIN_SCORE`, def 0.35). `0` desactiva el umbral de score. Valor inválido → def."""
    from .dominio.agrupar import UMBRAL_MIN_SCORE_DEF

    return _peso01(ENV_PROMOVER_MIN_SCORE, UMBRAL_MIN_SCORE_DEF)


# --------------------------------------------------------------------------- #
# Volumen de producción automática (el PLAN EDITORIAL por marca es el gate)     #
# --------------------------------------------------------------------------- #

# Admitir sin plan produciría al ritmo de Recolectar (cientos de noticias/día → cientos de
# temas/día), muy por encima de lo que una marca publica de verdad. El PLAN EDITORIAL DIARIO
# por marca (`plan_dia`) reparte el objetivo del día en cupos POR CATEGORÍA («lo mejor de cada
# tipo», con slots explícitos para breaking) Y ES EL GATE: sin plan, la marca no auto-produce.
ENV_PROMOVER_MADURACION_MIN = "KENI_PROMOVER_MADURACION_MIN"
PROMOVER_MADURACION_MIN_DEF = 45
ENV_PLAN_DIA = "KENI_PLAN_DIA"
ENV_PLAN_REDES = "KENI_PLAN_REDES"


def promover_maduracion_min() -> int:
    """Minutos mínimos de una historia en el pool antes de poder promoverse
    (`KENI_PROMOVER_MADURACION_MIN`, def 45, min 0; `0` desactiva). Exentas las curadas y las
    breaking corroboradas (regla en `agrupar.evaluar_umbral`): la urgencia real no espera.
    Dedicar este tiempo a "elegir" deja que la corroboración se acumule y que Admitir
    compare historias maduras, no primeras llegadas."""
    return _entero(ENV_PROMOVER_MADURACION_MIN, PROMOVER_MADURACION_MIN_DEF, minimo=0)


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
    """PLAN EDITORIAL DIARIO de una marca: cupos por CATEGORÍA (`KENI_PLAN_DIA::marca`).

    Formato "categoria:n,…" (p. ej. "mx:4,internacional:4,breaking:2,entretenimiento:2,
    evergreen:1" = el objetivo diario de UnoTV). El plan es EL GATE de auto-producción: con
    plan, Admitir llena cada cupo con LAS MEJORES historias de esa categoría (las breaking
    corroboradas consumen el cupo 'breaking' sea cual sea su categoría de feed). Categorías sin
    pool (p. ej. 'evergreen') reservan el hueco para el flujo manual. {} = SIN PLAN = no se
    auto-produce nada para esa marca. El plan se edita POR MARCA en Programación → «Plan y
    horarios» (`KENI_PLAN_DIA::marca`); no hay plan global por defecto."""
    if not marca:
        return {}
    return parsear_plan(_crudo(f"{ENV_PLAN_DIA}::{marca}"))


def parsear_redes(crudo: str) -> list[str]:
    """Parsea una CSV de ids de red a lista de ids CANÓNICOS, en el orden de aparición. PURA.

    Filtra con `redes.es_red`: los ids desconocidos se IGNORAN. Tolera espacios sueltos y
    duplicados (se conserva la primera aparición). [] si el texto no aporta ninguna red válida.
    """
    from . import redes  # perezoso: evita el ciclo config <- redes

    salida: list[str] = []
    for trozo in (crudo or "").split(","):
        rid = trozo.strip().lower()
        if rid and redes.es_red(rid) and rid not in salida:
            salida.append(rid)
    return salida


def plan_redes(marca: str = "") -> list[str]:
    """REDES que el plan diario de una marca espera por slot (`KENI_PLAN_REDES[::marca]`).

    CSV de ids de red canónicos (`facebook,instagram`, …). Solo DECLARA las redes esperadas:
    el calendario las usa para pintar huecos por red; no cambia cómo se generan las piezas.
    El override por marca SUSTITUYE al global. [] = sin selección. Filtra ids no-red."""
    if marca:
        propio = _crudo(f"{ENV_PLAN_REDES}::{marca}")
        if propio:
            return parsear_redes(propio)
    return parsear_redes(_crudo(ENV_PLAN_REDES))


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
# El TTL del pool se DESACOPLA de la vida de la frescura del score (72h): la frescura caduca el
# RANKING (una historia vieja deja de subir), pero no debe expulsar la historia del pool antes de
# que un humano pueda rescatarla. Un slow-burn (tema que cuaja despacio, o que espera cupo) sigue
# vivo en el ranking pero podría caducar a `descartado` por inactividad antes de usarse. 7 días da
# margen para esa recuperación manual sin reabrir la decisión de ranking.
NOTICIAS_TTL_H_DEF = 168  # 7 días sin actividad: techo de vida en el pool (no la vida de la frescura)
ENV_NOTICIAS_RETENCION_H = "KENI_NOTICIAS_RETENCION_H"
NOTICIAS_RETENCION_H_DEF = 336  # 14 días: margen sobrado para auditar qué caducó


def noticias_ttl_horas() -> int:
    """Horas sin actividad para que una historia `nuevo` no usada CADUQUE sola
    (`KENI_NOTICIAS_TTL_H`, def 168 = 7 días; 0 = sin caducidad). Soft: pasa a `descartado`."""
    return _entero(ENV_NOTICIAS_TTL_H, NOTICIAS_TTL_H_DEF, minimo=0)


def noticias_retencion_horas() -> int:
    """Horas tras las que lo CADUCADO sin usar se borra de verdad (techo del archivo)
    (`KENI_NOTICIAS_RETENCION_H`, def 336 = 14 días; 0 = no borrar nunca)."""
    return _entero(ENV_NOTICIAS_RETENCION_H, NOTICIAS_RETENCION_H_DEF, minimo=0)


# Retención de lo USADO cuyo tema ya NO existe: la caducidad de arriba nunca toca `usado`
# (lo ligado al tablero se conserva mientras su publicación viva), pero si la publicación se
# borró, la historia usada queda huérfana para siempre y el archivo crece sin techo.
ENV_NOTICIAS_USADOS_RETENCION_DIAS = "KENI_NOTICIAS_USADOS_RETENCION_DIAS"
NOTICIAS_USADOS_RETENCION_DIAS_DEF = 60  # 2 meses de margen para auditar temas ya borrados
# Retención de `rss_items_vistos` (marcas «item de feed ya convertido a copy»). Hoy NINGÚN
# camino de producción la relee (la dedup de re-ingesta vive en UNIQUE(fuente_id, clave) de
# `noticias_items` + lápidas), así que la ventana solo acota una tabla de solo-escritura.
ENV_RSS_VISTOS_RETENCION_DIAS = "KENI_RSS_VISTOS_RETENCION_DIAS"
RSS_VISTOS_RETENCION_DIAS_DEF = 180


def noticias_usados_retencion_dias() -> int:
    """Días tras los que una historia `usado` HUÉRFANA (su publicación ya no existe) se purga
    (`KENI_NOTICIAS_USADOS_RETENCION_DIAS`, def 60; 0 = no purgar nunca).

    CONSERVADOR: solo toca clusters/items `usado` cuyo `publicacion_id` NO resuelve a ninguna
    fila de `publicacion` (el detalle del tema y la mesa navegan siempre desde la publicación:
    mientras exista, sus fuentes se conservan intactas). Los items purgables quedan como lápida
    `descartado` (anti-reaparición) y los borra después la retención normal del pool
    (`KENI_NOTICIAS_RETENCION_H`), el mismo camino que lo caducado. Ver
    `db_noticias.purgar_usados_huerfanos`.
    """
    return _entero(
        ENV_NOTICIAS_USADOS_RETENCION_DIAS, NOTICIAS_USADOS_RETENCION_DIAS_DEF, minimo=0
    )


def rss_vistos_retencion_dias() -> int:
    """Días que se conserva cada marca de `rss_items_vistos` antes de purgarla
    (`KENI_RSS_VISTOS_RETENCION_DIAS`, def 180; 0 = no purgar nunca).

    La tabla anota «este item del feed ya generó copy» (una fila por copy RSS exitoso) y hoy
    es de SOLO ESCRITURA en producción: la dedup contra re-ingesta vive en
    UNIQUE(fuente_id, clave) de `noticias_items` y sus lápidas, no aquí. 180 días es margen
    sobradísimo frente a la ventana real de vida de un item de feed (horas/días). Solo se
    purgan filas CON fecha (`visto_en`); las legadas sin fecha las sella la migración 0072.
    Ver `db_noticias.purgar_rss_vistos`.
    """
    return _entero(ENV_RSS_VISTOS_RETENCION_DIAS, RSS_VISTOS_RETENCION_DIAS_DEF, minimo=0)


# --------------------------------------------------------------------------- #
# Perfil editorial por marca (Haiku desde libprompts) — Fase 2                    #
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
    """True si se funden con IA las historias del mismo evento (`KENI_PIPELINE_FUSIONAR`, def ON).

    Def ON: la fusión semántica (Haiku) ES la vía de agrupación de historias del mismo evento con
    titulares distintos —la formación de clusters solo dedup-ea EXACTO (url canónica o hash de
    título)—, así que va encendida por defecto (en la era de la IA el léxico a medias sobra: o
    apagado o encendido). `KENI_PIPELINE_FUSIONAR=0`/`no`/`off` la apaga. Conservador: ante duda no
    fusiona. Idiom default-ON (vacío → True), a diferencia de `recolectar`/`verificar` que son
    def OFF.
    """
    crudo = _crudo(ENV_PIPELINE_FUSIONAR).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


def fusion_semantica_max() -> int:
    """Máx. historias por marca y barrido que se mandan a Haiku a agrupar
    (`KENI_FUSION_SEMANTICA_MAX`, def 80, min 2). Acota coste y tamaño de contexto."""
    return _entero(ENV_FUSION_SEMANTICA_MAX, FUSION_SEMANTICA_MAX_DEF, minimo=2)


def fusion_ventana_h() -> int:
    """Ventana de FRESCURA (horas) del lote de fusión/macro-evento (`KENI_FUSION_VENTANA_H`, def 24, min 1).

    Más corta que la ventana de agrupación (`KENI_CLUSTER_VENTANA_H`, 72h): solo los clusters con
    actividad (`ultimo_visto`) dentro de esta ventana entran al LLM de fusión/macro. Un cluster ya
    digerido y sin items nuevos sale del lote (no se reprocesa en cada barrido); si recibe un item
    nuevo su `ultimo_visto` avanza y reentra. Acota el lote a lo VIVO, no a todo el feed reciente.
    """
    return _entero(ENV_FUSION_VENTANA_H, FUSION_VENTANA_H_DEF, minimo=1)


def fusion_intervalo_seg() -> float:
    """Segundos mínimos entre pasadas de encolado de Fusionar (`KENI_FUSION_INTERVALO_SEG`, def 300, min 60).

    Throttle del paso `paso_fusionar_semantica`: como mucho una pasada por este intervalo. Espaciarlo
    reduce el número de jobs de Fusionar (y con ellos las sub-llamadas de Cotejar/Subtema, el grueso
    del gasto Sonnet), sin perder agrupación: las historias del mismo evento aparecen despacio. Valor
    inválido → def; se acota a un mínimo de 60s (por debajo el throttle deja de tener efecto útil).
    """
    crudo = _crudo(ENV_FUSION_INTERVALO_SEG)
    if not crudo:
        return FUSION_INTERVALO_SEG_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return FUSION_INTERVALO_SEG_DEF
    return max(60.0, valor)


def fusion_min_score() -> float:
    """Score mínimo [0,1] de un cluster para entrar al lote de Fusionar (`KENI_FUSION_MIN_SCORE`, def 0.3).

    Filtra fuera del candidato a fusión los clusters con `score` por debajo del umbral: no gastar
    fusión (ni sus sub-llamadas) en noticias que no se publicarían. Mismo campo `score` que usa el
    umbral de promoción (`KENI_PROMOVER_MIN_SCORE`). `0` desactiva el filtro. Valor inválido → def.
    """
    return _peso01(ENV_FUSION_MIN_SCORE, FUSION_MIN_SCORE_DEF)


def fusion_cotejar_activo() -> bool:
    """True si Fusionar VERIFICA cada grupo propuesto («Cotejar») antes de fundir (`KENI_FUSION_COTEJAR`).

    Def OFF: los grupos que propone la pasada principal (Sonnet) se aceptan tal cual, SIN la
    sub-llamada de cotejo por grupo (0 jobs Cotejar). Con ON se re-pregunta cada grupo con solo esas
    historias antes de fundirlo (comportamiento conservador previo). Idiom default-OFF (vacío → False).
    """
    return _crudo(ENV_FUSION_COTEJAR).lower() in _VERDADEROS


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


# FLUJO CONTINUO: el pipeline no tiene intervalo configurable (tick corto constante en
# `pipeline_contenido._barrido`) ni topes por etapa (Verificar/Redactar/Ilustrar/Revisar): el volumen lo
# regulan los DOS knobs de Admitir de abajo + el backpressure de la cola (`KENI_MAX_JOBS`).


def pipeline_max() -> int:
    """Máximo de historias que Admitir admite por marca en cada pasada
    (`KENI_PIPELINE_MAX`, def 3, min 1). Cada admisión acaba en `claude -p` (coste)."""
    return _entero(ENV_PIPELINE_MAX, PIPELINE_MAX_DEF, minimo=1)


def pipeline_en_proceso_max(marca: str = "") -> int:
    """WIP del gate SERIAL: piezas EN CURSO por marca (`KENI_PIPELINE_EN_PROCESO_MAX`, def 8, min 1).

    ES el regulador del flujo continuo (in=out): Admitir no admite más historias de una
    marca mientras ésta tenga >= esto sin terminar (Verificar pendiente o verificado sin copy); primero se
    COMPLETA lo que entró, luego entran nuevas. El RITMO del ámbito (`ritmo(marca)`, marca=""=global)
    escala el tope hacia abajo: bajar el ritmo de una marca frena también cuánta verificación
    (la etapa cara) entra en proceso, sin apagar la etapa (ritmo 100 = tope de fábrica).
    """
    from . import config_produccion  # perezoso: evita el ciclo entre submódulos de config

    base = _entero(ENV_PIPELINE_EN_PROCESO_MAX, PIPELINE_EN_PROCESO_MAX_DEF, minimo=1)
    return max(1, round(base * config_produccion.ritmo(marca) / 100))


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


def verificacion_fuente_modelo() -> str:
    """Modelo de claude de la VERIFICACIÓN de la fuente (`KENI_VERIFICACION_FUENTE_MODELO`, def "sonnet").

    Verificar es LA compuerta editorial: abre las fuentes y corrobora con la web antes de redactar.
    Sonnet 5 es el modelo por defecto de toda la consola (ver `copy_modelo`); el resto de etapas
    —inferencias, tareas mecánicas— van con haiku. Mismas semanticas que `insumos_modelo`:
    var no fijada -> "sonnet"; fijada a "" -> sin `--model` (default de claude); fijada a un valor
    (p. ej. "opus" si la verificación necesita más margen de precisión) -> ese modelo.
    """
    raw = os.environ.get(ENV_VERIFICACION_FUENTE_MODELO)
    if raw is None:
        return "sonnet"
    return raw.strip()


def verificacion_fuente_esfuerzo() -> str:
    """Esfuerzo (thinking) de la verificación de la fuente (`KENI_VERIFICACION_FUENTE_ESFUERZO`, def "high").

    Verificar razona sobre fuentes abiertas con la web: corre con esfuerzo alto. "" (explicito) = sin
    override (cae a la preferencia global). El valor se valida contra `preferencias.ESFUERZOS_VALIDOS`
    en el armado del argv (un valor invalido se ignora).
    """
    raw = os.environ.get(ENV_VERIFICACION_FUENTE_ESFUERZO)
    if raw is None:
        return "high"
    return raw.strip()


def verificacion_fuente_timeout() -> int:
    """Wall-timeout (s) de la verificación de la fuente (`KENI_VERIFICACION_FUENTE_TIMEOUT`, def 600, min 0).

    Holgado: Verificar abre fuentes y busca en la web. 0 = sin override (se usa el global
    `KENI_CLAUDE_TIMEOUT`). El override solo ENDURECE: el runner lo topa con `min(global, override)`.
    """
    return _entero(ENV_VERIFICACION_FUENTE_TIMEOUT, VERIFICACION_FUENTE_TIMEOUT_DEF, minimo=0)


def verificacion_en_curso_ttl_seg() -> int:
    """TTL (s) del limpiador de temas `verificacion_fuente='en_curso'` sueltos (`KENI_VERIFICACION_EN_CURSO_TTL_MIN`).

    Def 30 min (muy superior al timeout de la verificación, asi nunca toca una verificación viva). El recolector
    resetea a "" los `en_curso` mas viejos para que vuelvan a la re-verificación del barrido.
    """
    return _entero(ENV_VERIFICACION_EN_CURSO_TTL_MIN, VERIFICACION_EN_CURSO_TTL_MIN_DEF, minimo=5) * 60


def alguna_etapa_investigacion_activa() -> bool:
    """Gate del loop de INVESTIGACIÓN (ADR 0011): True si hay trabajo de investigación que
    considerar bajo la máquina.

    El loop de investigación (caducidad + Admitir + Verificar) solo tiene sentido si ALGUNA marca
    tiene su admisión o su verificación encendidas: con Recolectar Y Verificar apagadas en todas
    las marcas no entra nada nuevo ni se verifica, y el loop duerme (la caducidad de lo ya en curso
    retoma en cuanto se reactive). Basta UNA marca activa para que el loop barra; el override por
    marca se aplica DENTRO del barrido (`etapa_activa`). Las etapas de Fusionar/Priorizar viven en
    el daemon de Recolectar, no en este loop.
    """
    return alguna_marca_con_etapa(ENV_PIPELINE_RECOLECTAR) or alguna_marca_con_etapa(
        ENV_PIPELINE_VERIFICAR
    )


def alguna_etapa_produccion_activa() -> bool:
    """Gate del loop de PRODUCCIÓN (ADR 0011): siempre True bajo la máquina.

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
    la revision (`listo`→`revisar`) y deja una nota para que el humano decida.
    """
    return _crudo(ENV_PIPELINE_REVISAR).lower() in _VERDADEROS


def ilustrar_activo() -> bool:
    """True si la ETAPA de Ilustrar del pipeline debe ilustrar (`KENI_PIPELINE_ILUSTRAR`, "Ilustrar").

    Def OFF (conservador): el equipo hace la imagen a mano. Con el flag, la etapa de Ilustrar del
    pipeline (tras la de Redactar) genera imagen por IA para los temas con copy pero sin imagen y
    la adjunta. Sin proveedor de imagen configurado, no hace nada (degrada).
    """
    return _crudo(ENV_PIPELINE_ILUSTRAR).lower() in _VERDADEROS


def decisor_activo() -> bool:
    """True si la ETAPA de Decisor de formato debe correr (`KENI_PIPELINE_DECISOR`, "Decisor").

    Def OFF (conservador): sin el flag, Redactar decide el formato (foto vs carrusel) dentro de su
    propio prompt, como hoy. Con el flag, una etapa previa (Haiku barato) fija el camino del tema
    antes de redactar. Ver `dominio/decisor.py` y el gate en `pipeline_contenido/_barrido.py`.
    """
    return _crudo(ENV_PIPELINE_DECISOR).lower() in _VERDADEROS


def traducir_activo() -> bool:
    """True si la ETAPA de Traducir debe traducir (`KENI_PIPELINE_TRADUCIR`).

    Def ON: el daemon de Recolectar encola la traducción a ES de los clusters extranjeros recientes
    sin traducir. Se apaga con un valor falsy explícito (`KENI_PIPELINE_TRADUCIR=0`, global o
    `::marca`): los clusters de esa marca se quedan sin traducir (`paso_traducir` respeta `etapa_activa`).
    """
    crudo = _crudo(ENV_PIPELINE_TRADUCIR).strip().lower()
    if not crudo:
        return True
    return crudo in _VERDADEROS


def admitir_activo() -> bool:
    """True si la ETAPA de Admitir debe materializar temas (`KENI_PIPELINE_ADMITIR`).

    Def ON: la admisión promueve las historias verificadas del pool a temas (con copy pendiente).
    Es ADITIVA sobre Recolectar: el barrido admite para una marca solo si Recolectar Y Admitir
    están encendidas para ella (`etapa_activa`). Se apaga con un valor falsy explícito (global o
    `::marca`).
    """
    crudo = _crudo(ENV_PIPELINE_ADMITIR).strip().lower()
    if not crudo:
        return True
    return crudo in _VERDADEROS


def portal_copy_auto() -> bool:
    """True si el canal PORTAL debe redactar copy AUTOMÁTICO (`KENI_PORTAL_COPY_AUTO`, legado).

    Def OFF: un tema `origen='portal'` nace con su pieza mecánica (foto del artículo + titular
    como copy-in) y CERO `claude -p`; el copy lo lanza un humano con «Generar» desde el feed
    Portal. Con un valor verdadero, la producción vuelve a redactar los temas del Portal sola
    (decisor + copy + hashtags), como antes. Lee vía `_crudo` (store > env > defecto): editable
    en caliente desde la API admin.
    """
    return _crudo(ENV_PORTAL_COPY_AUTO).lower() in _VERDADEROS


def sugerir_hashtags_activo() -> bool:
    """True si la ETAPA de Sugerir hashtags debe proponer (`KENI_PIPELINE_SUGERIR_HASHTAGS`).

    Def ON (a diferencia del resto de etapas de coste): la sugerencia es READ-ONLY, barata y NO
    toca el copy ni publica nada —solo deja una propuesta en gris que un humano acepta o descarta—,
    así que el piloto la quiere encendida de salida. Se apaga con un valor falsy explícito.
    """
    crudo = _crudo(ENV_PIPELINE_SUGERIR_HASHTAGS).strip().lower()
    if not crudo:
        return True
    return crudo in _VERDADEROS


# --------------------------------------------------------------------------- #
# Toggle ÚNICO «Generar» (noticia → copy)                                       #
# --------------------------------------------------------------------------- #

def _accesor_default_de_etapa(env_flag: str):
    """Accesor del DEFAULT DE FÁBRICA de una etapa del pipeline por su env (`KENI_PIPELINE_<ETAPA>`).

    Mapa ÚNICO etapa→accesor: el valor por defecto de cada etapa cuando una marca no tiene su
    propio override (`::marca`). NO es un maestro editable: solo el suelo de fábrica (Traducir/
    Admitir/Stock/Fusionar/Keywords ON; el resto OFF). `ValueError` si la env no es una etapa
    del pipeline (error de programación, no de datos).
    """
    try:
        return {
            ENV_PIPELINE_FUSIONAR: fusionar_semantica_activo,
            ENV_PRIORIZAR_PERFIL_IA: priorizar_perfil_activo,
            ENV_PIPELINE_RECOLECTAR: recolectar_activo,
            ENV_PIPELINE_VERIFICAR: verificar_activo,
            ENV_PIPELINE_SUGERIR_HASHTAGS: sugerir_hashtags_activo,
            ENV_PIPELINE_REDACTAR: pipeline_activo,
            ENV_PIPELINE_DECISOR: decisor_activo,
            ENV_PIPELINE_TRADUCIR: traducir_activo,
            ENV_PIPELINE_ADMITIR: admitir_activo,
            ENV_PIPELINE_ILUSTRAR: ilustrar_activo,
            ENV_PIPELINE_STOCK: stock_busca_activo,
            ENV_PIPELINE_REVISAR: revisar_activo,
            ENV_CRITICA_IA: critica_ia_activa,
        }[env_flag]
    except KeyError:
        raise ValueError(f"'{env_flag}' no es una etapa del pipeline de contenido.") from None


def etapa_default(env_flag: str) -> bool:
    """Default DE FÁBRICA de la etapa `env_flag` (el suelo cuando una marca no tiene override)."""
    return _accesor_default_de_etapa(env_flag)()


def etapa_activa(env_flag: str, marca: str) -> bool:
    """FUENTE ÚNICA de «¿la etapa `env_flag` está encendida para `marca`?». SIEMPRE por marca.

    Lee el toggle POR MARCA `KENI_PIPELINE_<ETAPA>::marca` del store (lo que pone la UI); sin
    override, cae al DEFAULT DE FÁBRICA de la etapa (`etapa_default`). NO hay maestro global
    editable: cada marca se gobierna por separado. La marca vacía (feed compartido sin marca)
    sigue el default de fábrica (nunca se apaga por marca). La MISMA lectura la usan el daemon
    (qué barre), la vista Pipeline (qué pinta «saltada») y el catálogo (qué muestra el toggle).
    """
    from . import ajustes  # perezoso: evita el ciclo config <- ajustes
    from .config_produccion import clave_por_marca

    if marca:
        crudo = ajustes.obtener(clave_por_marca(env_flag, marca))
        if crudo is not None and crudo.strip():
            return crudo.strip().lower() in _VERDADEROS
    return etapa_default(env_flag)


def alguna_marca_con_etapa(env_flag: str) -> bool:
    """¿ALGUNA marca de noticias tiene la etapa `env_flag` encendida? Gate de LOOP: el daemon
    corre si al menos una marca la usa. Sin marcas, cae al default de fábrica de la etapa."""
    from . import marcas

    ids = list(marcas.noticias())
    if not ids:
        return etapa_default(env_flag)
    return any(etapa_activa(env_flag, mid) for mid in ids)


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


def _cred_agencia(agencia: str, campo: str) -> str | None:
    """Credencial de agencia guardada por la UI (almacen de secretos), o None si no hay.

    Import PEREZOSO de `secretos` (evita el ciclo config <- secretos), igual que `_clave_stock`.
    """
    from . import secretos

    return secretos.obtener_credencial_agencia(agencia, campo)


def reuters_api_key() -> str | None:
    """API key de Reuters Connect; None si no esta (fuente apagada).

    Precedencia: el SECRETO guardado por la UI (Sistema → Proveedores) gana; si no, la env
    `KENI_REUTERS_API_KEY`.
    """
    return _cred_agencia("reuters", "api_key") or _crudo(ENV_REUTERS_API_KEY) or None


def reuters_base_url() -> str:
    """URL base de Reuters Connect (secreto UI > `KENI_REUTERS_BASE_URL` > def publico), sin barra final."""
    return (
        _cred_agencia("reuters", "base_url")
        or _crudo(ENV_REUTERS_BASE_URL)
        or REUTERS_BASE_URL_DEF
    ).rstrip("/")


def reuters_configurado() -> bool:
    """True si Reuters tiene credencial: la fuente puede descargar (si no, queda pendiente)."""
    return bool(reuters_api_key())


def pexels_api_key() -> str | None:
    """API key GLOBAL de Pexels; None si no está (proveedor de stock apagado).

    Pexels es una agencia genérica: una sola clave sirve a todas las marcas. Precedencia:
    el SECRETO guardado por la UI (Sistema → Proveedores) gana; si no, la global por
    entorno (`KENI_PEXELS_API_KEY`).
    """
    return _clave_stock("pexels") or _crudo(ENV_PEXELS_API_KEY) or None


def pixabay_api_key() -> str | None:
    """API key GLOBAL de Pixabay; None si no está (proveedor de stock apagado).

    Misma precedencia que Pexels: secreto de la UI > global por entorno
    (`KENI_PIXABAY_API_KEY`).
    """
    return _clave_stock("pixabay") or _crudo(ENV_PIXABAY_API_KEY) or None


def _clave_stock(proveedor: str) -> str | None:
    """Clave GLOBAL de stock guardada por la UI (almacen de secretos), o None si no hay."""
    from . import secretos

    return secretos.obtener_clave_stock(proveedor)


def fuentes_stock_activas(marca: str = "") -> set[str] | None:
    """Proveedores de stock HABILITADOS para una marca, o None si no hay filtro (todos).

    Lee `KENI_STOCK_FUENTES[::marca]` (CSV de ids de proveedor). Vacío/ausente = sin filtro:
    se usan todas las fuentes disponibles. Un valor no vacío ACOTA a los ids listados.
    """
    crudo = _crudo(f"{ENV_STOCK_FUENTES}::{marca}") if marca else ""
    if not crudo:
        crudo = _crudo(ENV_STOCK_FUENTES)
    ids = {t.strip().lower() for t in crudo.split(",") if t.strip()}
    return ids or None


def stock_busca_activo() -> bool:
    """True si la ETAPA de Stock del pipeline debe buscar (`KENI_PIPELINE_STOCK`).

    Def ON: a los temas con copy pero SIN imagen les baja una foto de ayuda (1º la ORIGINAL del
    RSS, fallback a una API gratuita) para que el feed no salga en gris. La foto es solo ayuda
    visual (atenuada/"SIN LICENCIA", nunca publicable sin autorizar), así que es segura por
    defecto. Se apaga con un valor falsy explícito (`KENI_PIPELINE_STOCK=0`).
    """
    crudo = _crudo(ENV_PIPELINE_STOCK).strip().lower()
    if not crudo:
        return True
    return crudo in _VERDADEROS


def stock_max_por_barrido() -> int:
    """Cuántos temas ilustra con stock por barrido (`KENI_STOCK_MAX_BARRIDO`, def 3; acota coste/rate)."""
    try:
        return max(1, int(_crudo(ENV_STOCK_MAX_BARRIDO) or "3"))
    except ValueError:
        return 3


def afp_client_id() -> str | None:
    """Client ID de AFP; None si no esta.

    Precedencia: el SECRETO guardado por la UI gana; si no, la env `KENI_AFP_CLIENT_ID`.
    """
    return _cred_agencia("afp", "client_id") or _crudo(ENV_AFP_CLIENT_ID) or None


def afp_client_secret() -> str | None:
    """Client secret de AFP; None si no esta.

    Precedencia: el SECRETO guardado por la UI gana; si no, la env `KENI_AFP_CLIENT_SECRET`
    (esta SIN strip, sensible).
    """
    secreto = _cred_agencia("afp", "client_secret")
    if secreto:
        return secreto
    valor = os.environ.get(ENV_AFP_CLIENT_SECRET)
    return valor if valor else None


def afp_base_url() -> str:
    """URL base de AFP (secreto UI > `KENI_AFP_BASE_URL` > def publico), sin barra final."""
    return (
        _cred_agencia("afp", "base_url") or _crudo(ENV_AFP_BASE_URL) or AFP_BASE_URL_DEF
    ).rstrip("/")


def afp_configurado() -> bool:
    """True si AFP tiene AMBAS credenciales OAuth2 (si no, la fuente queda pendiente)."""
    return bool(afp_client_id() and afp_client_secret())



# --------------------------------------------------------------------------- #
# Accesores: Traducir + tropicalización MX (Ola 4)                             #
# --------------------------------------------------------------------------- #


def traduccion_max() -> int:
    """Cap de temas extranjeros a traducir por request del Radar (`KENI_TRADUCCION_MAX`, def 15, min 1)."""
    return _entero(ENV_TRADUCCION_MAX, 15, minimo=1)
