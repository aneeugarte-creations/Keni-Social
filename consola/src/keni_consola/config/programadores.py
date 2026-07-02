"""Config — accesores del dominio programadores. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._comun import (
    _VERDADEROS,
    ALERTAS_INTERVALO_HORAS_DEF,
    ALERTAS_REVISION_HORAS_DEF,
    ALERTAS_UMBRAL_ENGAGEMENT_DEF,
    ALGORITMOS_INTERVALO_HORAS_DEF,
    ENV_ALERTAS_ACTIVAS,
    ENV_ALERTAS_INTERVALO_HORAS,
    ENV_ALERTAS_REVISION_HORAS,
    ENV_ALERTAS_UMBRAL_ENGAGEMENT,
    ENV_ALGORITMOS_AUTO,
    ENV_ALGORITMOS_INTERVALO_HORAS,
    ENV_AUTO_PREAPROBACION,
    ENV_METRICAS_HISTORICO_RETENCION_DIAS,
    ENV_METRICAS_PIEZAS_REFRESCO_HORAS,
    ENV_METRICAS_REFRESCO_HORAS,
    ENV_MIN_APROBACIONES,
    ENV_PATRONES_AUTO,
    ENV_PUBLICAR_REAL,
    ENV_TRENDS,
    ENV_TRENDS_GEOS,
    ENV_TRENDS_INTERVALO_MIN,
    METRICAS_HISTORICO_RETENCION_DIAS_DEF,
    METRICAS_PIEZAS_REFRESCO_HORAS_DEF,
    METRICAS_REFRESCO_HORAS_DEF,
    MIN_APROBACIONES_DEF,
    TRENDS_GEOS_DEF,
    TRENDS_INTERVALO_MIN_DEF,
    _crudo,
    _entero,
    os,
)
from .produccion import (
    marca_apagada,
)

# --------------------------------------------------------------------------- #
# Accesores: programadores en segundo plano                                    #
# --------------------------------------------------------------------------- #


def metricas_refresco_horas() -> int:
    """Cada cuantas horas refresca la cache de metricas el daemon (`KENI_METRICAS_REFRESCO_HORAS`, def 6, min 1)."""
    return _entero(ENV_METRICAS_REFRESCO_HORAS, METRICAS_REFRESCO_HORAS_DEF, minimo=1)


def metricas_piezas_refresco_horas() -> int:
    """Cada cuantas horas refresca el daemon la cache POR PIEZA del tablero.

    `KENI_METRICAS_PIEZAS_REFRESCO_HORAS`, def 4, min 1. Fase 3 auto-operativa: refresca
    proactivamente el rendimiento de las piezas publicadas recientes (con `id_post_metricool`)
    para que el tablero vea datos frescos sin lazy-fill en la apertura.
    """
    return _entero(
        ENV_METRICAS_PIEZAS_REFRESCO_HORAS, METRICAS_PIEZAS_REFRESCO_HORAS_DEF, minimo=1
    )


def metricas_historico_retencion_dias() -> int:
    """Días de retención del HISTÓRICO de métricas por pieza (`metricas_pieza_snapshots`).

    `KENI_METRICAS_HISTORICO_RETENCION_DIAS`, def 90, min 1. El daemon de refresco borra los
    snapshots más antiguos que esta ventana para acotar el crecimiento de la tabla (ADR 0007).
    """
    return _entero(
        ENV_METRICAS_HISTORICO_RETENCION_DIAS, METRICAS_HISTORICO_RETENCION_DIAS_DEF, minimo=1
    )


def alertas_rendimiento_horas() -> int:
    """Cada cuantas horas corre el barrido de alertas de rendimiento.

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


def alertas_revision_horas() -> int:
    """Horas de espera en la cola de revisión sin decisión que marcan una pieza ESTANCADA.

    `KENI_ALERTAS_REVISION_HORAS`, def 24, min 1. Lo consume el barrido de alertas para el
    aviso agregado por marca «N piezas llevan >X h esperando revisión».
    """
    return _entero(ENV_ALERTAS_REVISION_HORAS, ALERTAS_REVISION_HORAS_DEF, minimo=1)


def publicar_real() -> bool:
    """True si `KENI_PUBLICAR_REAL` esta a un valor afirmativo (gate de pieza real).

    Por defecto OFF (False): el botón de publicar solo PREVISUALIZA el cuerpo. Pon
    `KENI_PUBLICAR_REAL=1` (o `true`/`yes`/`on`) para autorizar el posteo real a
    Metricool/Postproxy. El humano sigue aprobando y disparando la publicación.
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


def canal_publicacion_para(marca: str) -> str:
    """Canal de publicación de `marca` (id canónico slug-guion): "metricool" | "postproxy".

    DEFAULT "metricool" (cero cambio de comportamiento histórico): es el canal que usa
    el programador salvo que la marca elija "postproxy" en `[postproxy.marcas.<id>].canal`
    del config.toml de métricas. Coherente con `publicar_real_para`: un accesor puro que
    el programador consulta para decidir a qué adaptador entrega el borrador.

    Traduce el `id` canónico (slug-guion) al `id_metricas` (guion_bajo) que indexa la
    config de Postproxy. Degrada a "metricool" ante CUALQUIER fallo (keni_metricas no
    disponible, config rota): el despacho nunca rompe por no poder resolver el canal.
    """
    try:
        from keni_metricas.config import cargar_config
        from keni_shared.marcas import id_metricas_de
    except ImportError:
        return "metricool"
    try:
        cfg = cargar_config()
    except Exception:  # noqa: BLE001 -- config rota no debe romper el despacho
        return "metricool"
    return cfg.postproxy.canal_marca(id_metricas_de(marca))


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


def patrones_auto_activo() -> bool:
    """True si el daemon de re-derivación de patrones debe correr (`KENI_PATRONES_AUTO`).

    Def OFF (conservador): la re-derivación reescribe los artefactos de patrones por marca
    (perfil runtime + doc 'patrones'); Voz/Reglas (criterio humano) jamás se tocan. Lee via
    `_crudo` (precedencia store > env > defecto) para que el toggle del catálogo aplique en
    caliente, como el resto de gates de daemons.
    """
    return _crudo(ENV_PATRONES_AUTO).lower() in _VERDADEROS


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
