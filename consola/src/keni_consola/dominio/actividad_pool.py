"""Registrar la actividad IA de una sub-llamada del POOL bajo su ETAPA explícita (fuente única).

Varias llamadas a `claude -p` no son un job propio en la cola, sino SUB-llamadas que corren dentro
del post-procesado de otro job o en el acto de un paso del pipeline (la verificación «Cotejar» y el
reparto en «Subtema» del job de Fusionar; la traducción EN EL ACTO de la admisión). Su coste se
acumula en el ejecutor síncrono (`dominio.traducir`), pero sin sellarlo quedaba HUÉRFANO: nunca
llegaba al ledger `gasto_ia`, así que la economía «por etapa» no lo veía.

Este módulo sella cada sub-llamada como una GENERACIÓN-actividad COMPLETADA con su `etapa` EXPLÍCITA
(la economía la respeta sobre la derivada del tipo) y vuelca su gasto al ledger. Es la pieza
compartida por los puntos que antes descartaban o no registraban estas métricas.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("keni_consola.dominio.actividad_pool")


def registrar_actividad_pool(
    marca: str,
    etiqueta: str,
    *,
    etapa: str,
    prompt: str = "",
    salida: str = "",
    proceso: str | None = None,
) -> None:
    """Sella una GENERACIÓN-actividad COMPLETADA de UNA sub-llamada IA del pool (best-effort).

    Toma las métricas que el ejecutor síncrono (`dominio.traducir`) acumuló en este hilo desde la
    última toma —las de la llamada que se acaba de ejecutar— y crea un registro `tipo='pipeline'`
    con la `etapa` EXPLÍCITA, volcando su gasto a `gasto_ia` (la economía «por etapa» la respeta
    sobre la derivada del tipo, así cada sub-llamada deja su propia fila). `prompt`/`salida` son los
    REALES de la llamada (transparencia en «Actividad IA»); si no se pasan, queda solo el resumen.
    `proceso` por defecto INVESTIGACION (el pool de noticias). Un fallo al registrar nunca propaga.
    """
    from .. import generaciones, presupuesto_ia
    from . import traducir

    try:
        metricas = traducir.tomar_metricas_acumuladas()
        registro: dict[str, Any] = {
            "tipo": "pipeline",
            "proceso": proceso or generaciones.PROCESO_INVESTIGACION,
            "etapa": etapa,
            "marca": marca,
            "etiqueta": etiqueta,
            "prompt": (prompt or "")[:20000],
            "salida": (salida or "")[:20000],
            "estado": generaciones.ESTADO_COMPLETADO,
            "fase": generaciones.FASE_COMPLETADO,
            "fecha_fin": generaciones.ahora_iso(),
        }
        if metricas:
            registro["metricas"] = metricas
        pub = generaciones.crear(registro)
        # `crear` no dispara el hook de cierre (sí `actualizar`): volcamos el gasto aquí, con la
        # etapa explícita. No-op sin métricas medibles (una llamada sin coste no ensucia el ledger).
        if metricas:
            presupuesto_ia.registrar_cierre(pub)
    except Exception:  # noqa: BLE001 -- la actividad es best-effort; nunca rompe el paso que la llama
        _log.warning("actividad_pool: no se pudo registrar la sub-llamada IA (%s).", etapa, exc_info=True)
