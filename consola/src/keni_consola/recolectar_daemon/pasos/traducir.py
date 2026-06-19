"""Paso de TRADUCIR (Ola D): traduce a ES los clusters extranjeros recientes sin traducir."""

from __future__ import annotations

from typing import Any

import keni_consola.recolectar_daemon as _pkg

from ... import config, repos
from ...dominio import traducir
from .._comun import _log


def paso_traducir(*, ejecutor: traducir.Ejecutor | None = None) -> dict[str, Any]:
    """Traduce a ES los clusters EXTRANJEROS recientes sin traducir. Best-effort, ACOTADO.

    Selecciona hasta `KENI_TRAD_LOTE` clusters con `idioma != es`, `score >= KENI_TRAD_MIN_SCORE`,
    `traducido=0` dentro de la ventana reciente; los traduce+tropicaliza a MX con UNA sola
    llamada a Haiku (`traducir.traducir_items`) y persiste `titulo_es`/`resumen_es` +
    `titulo_original` + `traducido=1` por cluster. Sin tope artificial total: cada barrido
    procesa un lote del backlog; lo que falte se coge en barridos sucesivos.

    `ejecutor` inyectable (tests): si es None se usa el subproceso real. Devuelve
    `{traducidos, candidatos}`. Un fallo de Traducir NO aborta el barrido.
    """
    ventana_h = config.cluster_ventana_h()
    min_score = config.trad_min_score()
    lote = config.trad_lote()
    candidatos = repos.clusters_extranjeros_sin_traducir(
        ventana_h, min_score=min_score, limite=lote
    )
    if not candidatos:
        return {"traducidos": 0, "candidatos": 0}

    # Payload para Haiku: id + titulo + resumen ORIGINALES (en idioma extranjero).
    items = [
        {"id": c["id"], "titulo": c.get("titulo") or "", "resumen": c.get("resumen") or ""}
        for c in candidatos
    ]
    traducciones = traducir.traducir_items(items, ejecutor=ejecutor)
    # Traducir es POOL-WIDE (un lote de varias marcas en una llamada Haiku): registra SU propia
    # actividad con etapa "Traducir" y marca "" (agregado del pool), tomando las métricas
    # acumuladas de ESTA llamada. Así su coste aparece en la economía por etapa en vez de
    # filtrarse al siguiente paso que registra (Fusionar/Priorizar del próximo barrido).
    _pkg._registrar_actividad_ia(
        "",
        f"Traducir historias — {len(candidatos)} cluster(s) a ES (MX)",
        "",
        etapa="Traducir",
    )
    por_id = {str(t.get("id") or ""): t for t in traducciones}
    originales = {c["id"]: c for c in candidatos}

    traducidos = 0
    for cid, original in originales.items():
        t = por_id.get(cid)
        # Solo se persiste una traducción REAL (`ok`): un fallo de Haiku NO marca el cluster
        # `traducido=1` con el título extranjero (lo dejaría en idioma original para siempre).
        # Sin marcar, vuelve a ser candidato en el próximo barrido (reintento).
        if not t or not t.get("ok"):
            continue
        titulo_es = str(t.get("titulo_es") or "").strip()
        if not titulo_es:
            continue
        try:
            repos.marcar_cluster_traducido(
                cid,
                titulo_es=titulo_es,
                resumen_es=str(t.get("resumen_es") or ""),
                titulo_original=str(original.get("titulo") or ""),
            )
            traducidos += 1
        except Exception:  # noqa: BLE001 -- persistir una traducción no aborta el paso
            _log.exception("recolectar_daemon: fallo al guardar la traducción del cluster %s.", cid)

    return {"traducidos": traducidos, "candidatos": len(candidatos)}
