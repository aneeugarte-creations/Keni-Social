"""Umbral de PRODUCCIÓN AUTOMÁTICA de noticias — fuente única de la decisión.

PROBLEMA QUE RESUELVE
=====================
El panel lista el pool jerarquizado completo, pero PROMOVER una historia a tema dispara la
cadena verificación→copy (`claude -p` ×2: coste real de tokens de la suscripción). Antes la promoción
CI cogía el top-N por score SIN umbral: con un pool lleno de basura, esa basura se promovía igual
(garbage in → tokens out). Este módulo concentra la decisión «¿esta historia merece
producción automática?» para que la promoción (pipeline), el panel (API `promovible`) y
cualquier otro consumidor respondan EXACTAMENTE igual:

  - la regla PURA vive en `dominio.agrupar.evaluar_umbral` (verificación no dudosa +
    score recalculado ≥ mínimo + encaje de marca por vocabulario, con exenciones para lo
    curado por el equipo y las breaking corroboradas);
  - los umbrales vivos vienen de `config` (`KENI_PROMOVER_MIN_SCORE` /
    `KENI_PROMOVER_MIN_MARCA`, editables en caliente desde la consola);
  - el vocabulario de marca es el MISMO que usa el ranking (perfil editorial Haiku si la
    etapa Priorizar está activa para la marca; si no, la base de `relevancia_marca`).

Siempre devuelve el MOTIVO legible (también al superar): la decisión es explicable ante el
equipo, no una caja negra.
"""

from __future__ import annotations

from datetime import datetime

from . import config, relevancia_marca
from .dominio import agrupar, perfil_editorial


def palabras_relevancia(marca: str, perfil_activo: bool | None = None) -> frozenset[str]:
    """Vocabulario EFECTIVO de una marca: perfil editorial (Haiku) si está activo; si no, base.

    Centraliza la elección perfil-vs-base (la misma que usa el daemon de ingesta al puntuar).
    Respeta el toggle POR MARCA de `KENI_PRIORIZAR_PERFIL_IA`: una marca con el perfil de Priorizar
    apagado vuelve al vocabulario BASE aunque tenga un perfil Haiku cacheado. `perfil_activo`
    admite el valor ya leído (el daemon lo lee una vez por barrido); None = leer de config.
    """
    if perfil_activo is None:
        perfil_activo = config.priorizar_perfil_activo()
    if (
        perfil_activo and marca
        and not config.marca_apagada(config.ENV_PRIORIZAR_PERFIL_IA, marca)
    ):
        perfil = perfil_editorial.palabras(marca)
        if perfil:
            return perfil
    return relevancia_marca.palabras_de_marca(marca or None)


def evaluar(
    cluster: dict[str, object],
    *,
    ahora: datetime | None = None,
    palabras_marca: frozenset[str] | None = None,
) -> tuple[bool, str]:
    """¿`cluster` supera el umbral de producción automática AHORA? `(supera, motivo)`.

    Lee los umbrales vivos de config y el vocabulario efectivo de la marca del cluster, y
    delega la regla en `agrupar.evaluar_umbral` (pura). `ahora` inyectable para tests.
    `palabras_marca` admite el vocabulario YA resuelto (un llamante que evalúa un LOTE — la
    API del panel — lo memoiza por marca para no releer el cache del perfil por historia);
    None = resolverlo aquí.
    """
    marca = str(cluster.get("marca") or "")
    if palabras_marca is None:
        palabras_marca = palabras_relevancia(marca)
    return agrupar.evaluar_umbral(
        cluster,
        palabras_marca=palabras_marca,
        min_score=config.promover_min_score(),
        min_marca=config.promover_min_marca(),
        min_maduracion_min=config.promover_maduracion_min(),
        ahora=ahora,
        breaking_peso=config.cluster_breaking_peso(),
        breaking_ventana_h=config.cluster_breaking_ventana_h(),
    )
