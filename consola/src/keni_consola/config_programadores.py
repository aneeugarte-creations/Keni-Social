"""Config — accesores del dominio programadores. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _VERDADEROS,
    ALERTAS_INTERVALO_HORAS_DEF,
    ALERTAS_UMBRAL_ENGAGEMENT_DEF,
    ALGORITMOS_INTERVALO_HORAS_DEF,
    ENV_ALERTAS_ACTIVAS,
    ENV_ALERTAS_INTERVALO_HORAS,
    ENV_ALERTAS_UMBRAL_ENGAGEMENT,
    ENV_ALGORITMOS_AUTO,
    ENV_ALGORITMOS_INTERVALO_HORAS,
    ENV_AUTO_PREAPROBACION,
    ENV_COMERCIAL_INTERVALO_HORAS,
    ENV_COMERCIAL_INTERVALO_SEGUNDOS,
    ENV_EVENTOS_INTERVALO_SEGUNDOS,
    ENV_EVENTOS_VENCIMIENTOS,
    ENV_INVESTIGADOR,
    ENV_INVESTIGADOR_INTERVALO_HORAS,
    ENV_METRICAS_HISTORICO_RETENCION_DIAS,
    ENV_METRICAS_PIEZAS_REFRESCO_HORAS,
    ENV_METRICAS_REFRESCO_HORAS,
    ENV_MIN_APROBACIONES,
    ENV_PRIORIZA_METRICAS,
    ENV_PRIORIZA_METRICAS_RANGO,
    ENV_PROGRAMADOR_INTERVALO_SEGUNDOS,
    ENV_PUBLICAR_REAL,
    ENV_SUGERENCIAS_EDITORIALES,
    ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS,
    ENV_SUGERENCIAS_EDITORIALES_MAX,
    ENV_TRENDS,
    ENV_TRENDS_GEOS,
    ENV_TRENDS_INTERVALO_MIN,
    EVENTOS_INTERVALO_SEGUNDOS_DEF,
    INVESTIGADOR_INTERVALO_HORAS_DEF,
    METRICAS_HISTORICO_RETENCION_DIAS_DEF,
    METRICAS_PIEZAS_REFRESCO_HORAS_DEF,
    METRICAS_REFRESCO_HORAS_DEF,
    MIN_APROBACIONES_DEF,
    SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF,
    SUGERENCIAS_EDITORIALES_MAX_DEF,
    TRENDS_GEOS_DEF,
    TRENDS_INTERVALO_MIN_DEF,
    _crudo,
    _entero,
    os,
)
from .config_produccion import (
    marca_apagada,
)

# --------------------------------------------------------------------------- #
# Accesores: programadores en segundo plano                                    #
# --------------------------------------------------------------------------- #


def comercial_intervalo_segundos() -> float | None:
    """Intervalo de la captura comercial en s (`KENI_COMERCIAL_INTERVALO_SEGUNDOS`, min 1.0).

    None si ausente/invalido (el llamante cae a horas/def). Tiene PRIORIDAD sobre horas.
    """
    crudo = os.environ.get(ENV_COMERCIAL_INTERVALO_SEGUNDOS)
    if not crudo:
        return None
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return None


def comercial_intervalo_horas() -> float | None:
    """Intervalo de la captura comercial en HORAS (`KENI_COMERCIAL_INTERVALO_HORAS`).

    Devuelve las horas crudas (float, >0); None si ausente/invalido. El minimo de 60 s lo
    aplica el llamante al convertir a segundos (comportamiento historico).
    """
    crudo = os.environ.get(ENV_COMERCIAL_INTERVALO_HORAS)
    if not crudo:
        return None
    try:
        return float(crudo)
    except ValueError:
        return None


def programador_intervalo_segundos() -> float | None:
    """Intervalo del barrido del programador en s (`KENI_PROGRAMADOR_INTERVALO_SEGUNDOS`, min 1.0).

    None si ausente/invalido (el llamante cae al default del modulo).
    """
    crudo = os.environ.get(ENV_PROGRAMADOR_INTERVALO_SEGUNDOS)
    if not crudo:
        return None
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return None


def metricas_refresco_horas() -> int:
    """Cada cuantas horas refresca la cache de metricas el daemon (`KENI_METRICAS_REFRESCO_HORAS`, def 4, min 1)."""
    return _entero(ENV_METRICAS_REFRESCO_HORAS, METRICAS_REFRESCO_HORAS_DEF, minimo=1)


def metricas_piezas_refresco_horas() -> int:
    """Cada cuantas horas refresca el daemon la cache POR PIEZA del tablero.

    `KENI_METRICAS_PIEZAS_REFRESCO_HORAS`, def 4, min 1. Fase 3 auto-operativa: refresca
    proactivamente el rendimiento de las piezas publicadas recientes (con `id_post_metricool`)
    para que el tablero y el reciclaje vean datos frescos sin lazy-fill en la apertura.
    """
    return _entero(
        ENV_METRICAS_PIEZAS_REFRESCO_HORAS, METRICAS_PIEZAS_REFRESCO_HORAS_DEF, minimo=1
    )


def metricas_historico_retencion_dias() -> int:
    """Días de retención del HISTÓRICO de métricas por pieza (`metricas_pieza_snapshots`).

    `KENI_METRICAS_HISTORICO_RETENCION_DIAS`, def 90, min 1. El daemon de refresco poda los
    snapshots más antiguos que esta ventana para acotar el crecimiento de la tabla (ADR 0007).
    """
    return _entero(
        ENV_METRICAS_HISTORICO_RETENCION_DIAS, METRICAS_HISTORICO_RETENCION_DIAS_DEF, minimo=1
    )


def alertas_rendimiento_horas() -> int:
    """Cada cuantas horas corre el barrido de alertas de rendimiento/reciclaje.

    `KENI_ALERTAS_RENDIMIENTO_HORAS`, def 6, min 1.
    """
    return _entero(ENV_ALERTAS_INTERVALO_HORAS, ALERTAS_INTERVALO_HORAS_DEF, minimo=1)


def alertas_rendimiento_activas() -> bool:
    """True (def) si el barrido de alertas debe arrancar. `KENI_ALERTAS_RENDIMIENTO=0` lo apaga.

    Solo controla el HILO; la emision de eventos por transicion del tablero no depende de esto.
    """
    crudo = _crudo(ENV_ALERTAS_ACTIVAS)
    if not crudo:
        return True
    return crudo.lower() in _VERDADEROS


def alertas_umbral_engagement() -> float:
    """Umbral de engagement (%) para la alerta de bajo rendimiento.

    `KENI_ALERTAS_UMBRAL_ENGAGEMENT`, def 1.0. Una pieza publicada con engagement REAL
    (Metricool) por debajo de este valor dispara `pieza.bajo_rendimiento`. Valor invalido
    o <=0 -> def (no tiene sentido un umbral nulo).
    """
    crudo = _crudo(ENV_ALERTAS_UMBRAL_ENGAGEMENT)
    if not crudo:
        return ALERTAS_UMBRAL_ENGAGEMENT_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return ALERTAS_UMBRAL_ENGAGEMENT_DEF
    return valor if valor > 0 else ALERTAS_UMBRAL_ENGAGEMENT_DEF


def eventos_intervalo_segundos() -> float:
    """Intervalo del barrido de vencimientos del tablero en s (`KENI_EVENTOS_INTERVALO_SEGUNDOS`, min 1.0, def 300)."""
    crudo = os.environ.get(ENV_EVENTOS_INTERVALO_SEGUNDOS)
    if not crudo:
        return EVENTOS_INTERVALO_SEGUNDOS_DEF
    try:
        return max(1.0, float(crudo))
    except ValueError:
        return EVENTOS_INTERVALO_SEGUNDOS_DEF


def eventos_vencimientos_activos() -> bool:
    """True (def) si el barrido de vencimientos debe arrancar. `KENI_EVENTOS_VENCIMIENTOS=0` lo apaga.

    Solo controla el HILO que escanea el reloj; la emision de eventos por transicion
    (pieza aprobada/publicada) NO depende de esto.
    """
    crudo = _crudo(ENV_EVENTOS_VENCIMIENTOS)
    if not crudo:
        return True
    return crudo.lower() in _VERDADEROS


def publicar_real() -> bool:
    """True si `KENI_PUBLICAR_REAL` esta a un valor afirmativo (gate de publicacion real).

    Por defecto OFF (False): el programador opera en DRY-RUN. Pon `KENI_PUBLICAR_REAL=1`
    (o `true`/`yes`/`on`) para activar el posteo real al scheduler de Metricool.
    El humano sigue aprobando; esta flag solo autoriza al sistema a enviar lo ya
    programado a Metricool cuando vence la fecha.
    """
    return _crudo(ENV_PUBLICAR_REAL).lower() in _VERDADEROS


def publicar_real_para(marca: str) -> bool:
    """True si las piezas de `marca` deben publicarse DE VERDAD.

    Mismo patrón maestro+excepción que las etapas de auto-producción: el MAESTRO global
    `KENI_PUBLICAR_REAL` debe estar ON y la marca NO debe estar EXCLUIDA (override falsy por
    marca, `KENI_PUBLICAR_REAL::marca`). Con el maestro OFF, todas van a dry-run; con el maestro
    ON, una marca excluida sigue en dry-run mientras el resto publica. `marca` vacía sigue al
    maestro (sin override no está excluida).
    """
    return publicar_real() and not marca_apagada(ENV_PUBLICAR_REAL, marca)


def auto_preaprobacion() -> bool:
    """True si la pre-aprobacion de piezas de bajo riesgo esta activa (`KENI_AUTO_PREAPROBACION`).

    Def OFF (False, conservador): la cadena de aprobacion nace toda `pendiente`. Con el flag
    a un valor afirmativo, al crear la cadena de una pieza de bajo riesgo se auto-aprueban
    los niveles inferiores (nunca el ultimo, que queda a un humano). Trazable como "auto".
    """
    return _crudo(ENV_AUTO_PREAPROBACION).lower() in _VERDADEROS


def min_aprobaciones() -> int:
    """Minimo de aprobaciones acumuladas para PROGRAMAR una pieza (`KENI_MIN_APROBACIONES`).

    Def 2 (item A: "cuatro ojos" reales). `0` (o negativo) DESACTIVA el gate (cualquier pieza
    aprobada se puede programar, comportamiento legado). Valor no entero -> def. Min 0.
    """
    return _entero(ENV_MIN_APROBACIONES, MIN_APROBACIONES_DEF, minimo=0)


def investigador_activo() -> bool:
    """True si el Investigador (snapshot del Radar por marca) debe materializar (`KENI_INVESTIGADOR`).

    Def OFF (conservador): sin el flag, el daemon arranca pero NO materializa, y los endpoints
    (Radar/Parrilla) NUNCA leen del snapshot (siguen en vivo, comportamiento de Fase 0 intacto).
    Con el flag a un valor afirmativo, el daemon escribe el snapshot por marca y los endpoints
    lo sirven (rapido, sin re-descargar fuentes) mientras este fresco.
    """
    return _crudo(ENV_INVESTIGADOR).lower() in _VERDADEROS


def investigador_intervalo_horas() -> int:
    """Cada cuantas horas barre el Investigador (`KENI_INVESTIGADOR_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_INVESTIGADOR_INTERVALO_HORAS, INVESTIGADOR_INTERVALO_HORAS_DEF, minimo=1)


def prioriza_metricas_activo() -> bool:
    """True si el score de priorizacion debe usar las metricas historicas (`KENI_PRIORIZA_METRICAS`).

    Def OFF (conservador): la lista del dia ordena EXACTAMENTE como hoy. Con el flag a un valor
    afirmativo, las piezas de marcas que historicamente RINDEN mas reciben un pequeño bonus de
    score. Aditivo y DEGRADABLE: si la fachada de metricas no esta disponible, se omite sin romper.
    """
    return _crudo(ENV_PRIORIZA_METRICAS).lower() in _VERDADEROS


def prioriza_metricas_rango() -> str:
    """Rango de metricas para el bonus de priorizacion (`KENI_PRIORIZA_METRICAS_RANGO`, def "mes").

    Es uno de los rangos que entiende la fachada de metricas ("semana"/"mes"/...). Si el valor
    es invalido, el llamante lo trata best-effort (degrada a sin bonus); no se valida aqui.
    """
    return _crudo(ENV_PRIORIZA_METRICAS_RANGO) or "mes"


def algoritmos_auto_activo() -> bool:
    """True si el daemon de auto-refresco de Algoritmos debe ingerir (`KENI_ALGORITMOS_AUTO`).

    Def OFF (conservador): la pagina Algoritmos tiene un boton "Refrescar" manual. Con el flag
    a un valor afirmativo, un hilo demonio ingiere los feeds cada N horas (solo LEE feeds RSS
    publicos y persiste noticias clasificadas; no publica ni genera nada).
    """
    return _crudo(ENV_ALGORITMOS_AUTO).lower() in _VERDADEROS


def algoritmos_intervalo_horas() -> int:
    """Cada cuantas horas ingiere el daemon de Algoritmos (`KENI_ALGORITMOS_INTERVALO_HORAS`, def 6, min 1)."""
    return _entero(ENV_ALGORITMOS_INTERVALO_HORAS, ALGORITMOS_INTERVALO_HORAS_DEF, minimo=1)


def sugerencias_editoriales_activo() -> bool:
    """True si el digest diario de sugerencias editoriales debe correr (`KENI_SUGERENCIAS_EDITORIALES`).

    Def OFF (conservador): cada barrido encola uno o varios `claude -p` (coste). Con el flag a
    un valor afirmativo, un hilo demonio propone 1 vez/dia cambios a las fichas/limites a partir
    de las noticias importantes. Las propuestas son REVISABLES; nunca se aplican solas.
    """
    return _crudo(ENV_SUGERENCIAS_EDITORIALES).lower() in _VERDADEROS


def sugerencias_editoriales_intervalo_horas() -> int:
    """Cada cuantas horas corre el digest (`KENI_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS`, def 24, min 1)."""
    return _entero(
        ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS,
        SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF,
        minimo=1,
    )


def sugerencias_editoriales_max() -> int:
    """Maximo de plataformas a procesar por barrido (`KENI_SUGERENCIAS_EDITORIALES_MAX`, def 3, min 1).

    Cada plataforma cuesta un `claude -p`: el tope acota el gasto por dia.
    """
    return _entero(ENV_SUGERENCIAS_EDITORIALES_MAX, SUGERENCIAS_EDITORIALES_MAX_DEF, minimo=1)


def trends_activo() -> bool:
    """True si el daemon de Google Trends debe ingerir al pool (`KENI_TRENDS`, def OFF).

    Conservador: sin el flag el hilo arranca pero NO toca la red ni el pool. Con el flag, cada
    N min descarga el RSS de tendencias por geo y vuelca sus noticias a `noticias_items`.
    """
    return _crudo(ENV_TRENDS).lower() in _VERDADEROS


def trends_intervalo_min() -> int:
    """Cada cuántos minutos ingiere el daemon de Trends (`KENI_TRENDS_INTERVALO_MIN`, def 30, min 5)."""
    return _entero(ENV_TRENDS_INTERVALO_MIN, TRENDS_INTERVALO_MIN_DEF, minimo=5)


def trends_geos() -> tuple[str, ...]:
    """Geos a ingerir (`KENI_TRENDS_GEOS`, CSV; def `MX`). Vacío/ausente => el default."""
    crudo = _crudo(ENV_TRENDS_GEOS)
    geos = tuple(g.strip().upper() for g in crudo.split(",") if g.strip())
    return geos or TRENDS_GEOS_DEF
