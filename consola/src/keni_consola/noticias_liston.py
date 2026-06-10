"""Listón de PRODUCCIÓN AUTOMÁTICA de noticias — fuente única de la decisión.

PROBLEMA QUE RESUELVE
=====================
El panel lista el pool jerarquizado completo, pero PROMOVER una historia a tema dispara la
cadena QA→copy (`claude -p` ×2: coste real de tokens de la suscripción). Antes la promoción
CI cogía el top-N por score SIN listón: con un pool ruidoso, el ruido se promovía igual
(garbage in → tokens out). Este módulo concentra la decisión «¿esta historia merece
producción automática?» para que la promoción (pipeline), el panel (API `promovible`) y
cualquier otro consumidor respondan EXACTAMENTE igual:

  - la regla PURA vive en `dominio.clustering.evaluar_liston` (verificación no dudosa +
    score recalculado ≥ mínimo + encaje de marca por vocabulario, con exenciones para lo
    curado por el equipo y las breaking corroboradas);
  - los umbrales vivos vienen de `config` (`KENI_PROMOVER_MIN_SCORE` /
    `KENI_PROMOVER_MIN_MARCA`, editables en caliente desde la consola);
  - el vocabulario de marca es el MISMO que usa el ranking (perfil editorial Haiku si la
    etapa Editorial está activa para la marca; si no, la semilla de `relevancia_marca`).

Siempre devuelve el MOTIVO legible (también al superar): la decisión es explicable ante el
equipo, no una caja negra.
"""

from __future__ import annotations

from datetime import datetime

from . import config, relevancia_marca
from .dominio import clustering, perfil_editorial


def palabras_relevancia(marca: str, perfil_activo: bool | None = None) -> frozenset[str]:
    """Vocabulario EFECTIVO de una marca: perfil editorial (Haiku) si está activo; si no, semilla.

    Centraliza la elección perfil-vs-semilla (la misma que usa el daemon de ingesta al puntuar).
    Respeta el toggle POR MARCA de `KENI_PIPELINE_EDITORIAL`: una marca con el Editorial apagado
    vuelve al vocabulario SEMILLA aunque tenga un perfil Haiku cacheado. `perfil_activo` admite
    el valor ya leído (el daemon lo lee una vez por barrido); None = leer de config.
    """
    if perfil_activo is None:
        perfil_activo = config.perfil_editorial_activo()
    if (
        perfil_activo and marca
        and not config.marca_apagada(config.ENV_PIPELINE_EDITORIAL, marca)
    ):
        perfil = perfil_editorial.palabras(marca)
        if perfil:
            return perfil
    return relevancia_marca.palabras_de_marca(marca or None)


def evaluar(
    cluster: dict[str, object], *, ahora: datetime | None = None
) -> tuple[bool, str]:
    """¿`cluster` supera el listón de producción automática AHORA? `(supera, motivo)`.

    Lee los umbrales vivos de config y el vocabulario efectivo de la marca del cluster, y
    delega la regla en `clustering.evaluar_liston` (pura). `ahora` inyectable para tests.
    """
    marca = str(cluster.get("marca") or "")
    return clustering.evaluar_liston(
        cluster,
        palabras_marca=palabras_relevancia(marca),
        min_score=config.promover_min_score(),
        min_marca=config.promover_min_marca(),
        ahora=ahora,
    )
