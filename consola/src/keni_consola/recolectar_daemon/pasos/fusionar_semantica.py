"""Paso de FUSIONAR SEMÁNTICAMENTE (Fase 2b): fusiona con Haiku las historias del mismo evento."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import keni_consola.recolectar_daemon as _pkg

from ... import config, marcas, repos
from ...dominio import fusionar_semantica, traducir
from .. import _comun
from .._comun import _log


def _fresco_para_fusion(cluster: dict[str, Any], corte: datetime) -> bool:
    """True si el cluster tuvo actividad (`ultimo_visto`) en/tras `corte` (ventana de fusión).

    Lee `ultimo_visto` con `fromisoformat` (tolera el canon sin offset de `iso_utc` y el ISO con
    offset; naive se ASUME UTC, convención del sistema). Si la marca no es legible, NO excluye el
    cluster (conservador: ante la duda, se procesa).
    """
    crudo = str(cluster.get("ultimo_visto") or "").strip()
    if not crudo:
        return True
    try:
        visto = datetime.fromisoformat(crudo)
    except ValueError:
        return True
    if visto.tzinfo is None:
        visto = visto.replace(tzinfo=UTC)
    return visto >= corte


def _falta_subtema(ids: list[str], por_id: dict[str, dict[str, Any]]) -> bool:
    """True si algún cluster de la familia aún no tiene `subtema` (etiquetado incremental).

    Una familia con TODOS sus clusters ya faceteados no se reenvía a Haiku: re-proponer subtemas
    sobre una familia estable reescribiría la misma etiqueta y pagaría un Haiku por barrido.
    """
    return any(not str((por_id.get(i) or {}).get("subtema") or "").strip() for i in ids)


def _etiqueta_canonica(ids: list[str], por_id: dict[str, dict[str, Any]], propuesta: str) -> str:
    """Etiqueta ESTABLE de una familia de macro-evento: backstop determinista contra los sinónimos.

    Reúsa la `tema_macro` YA persistida que MÁS clusters de la familia comparten (así el mismo
    evento no se parte en «Mundial 2026» vs «Copa del Mundo 2026»: si Haiku agrupa ambos, gana la
    etiqueta dominante y se unifican). Cae a `propuesta` (la que propuso Haiku) solo si NINGÚN
    cluster de la familia traía etiqueta. Determinista: a empate de conteo, orden alfabético.
    """
    conteo: dict[str, int] = {}
    for i in ids:
        existente = str((por_id.get(i) or {}).get("tema_macro") or "").strip()
        if existente:
            conteo[existente] = conteo.get(existente, 0) + 1
    if not conteo:
        return propuesta
    return max(sorted(conteo), key=lambda e: conteo[e])


def _partir_en_subtemas(
    tema: str, ids: list[str], por_id: dict[str, dict[str, Any]],
    *, ejecutor: fusionar_semantica.Ejecutor | None,
) -> int:
    """Parte una familia de macro-evento en SUBTEMAS (Haiku) y los persiste. Devuelve nº etiquetados.

    Cada subtema (faceta: «Partidos», «Espectáculo»…) agrupa los clusters de un tipo, para que el
    carrusel sea coherente y la cadencia sea por subtema. Best-effort: cualquier fallo (Haiku o
    persistencia) se loguea y devuelve lo que llevara, sin abortar el paso.
    """
    familia = [por_id[i] for i in ids if i in por_id]
    if len(familia) < 2:
        return 0
    try:
        grupos = fusionar_semantica.proponer_subtemas(familia, ejecutor=ejecutor)
    except Exception:  # noqa: BLE001 -- un fallo de Haiku no aborta el etiquetado del evento
        _log.exception("recolectar_daemon: fallo proponiendo subtemas de «%s».", tema[:60])
        return 0
    etiquetados = 0
    for g in grupos:
        subtema = str(g.get("subtema") or "").strip()
        sub_ids = [str(i) for i in (g.get("ids") or []) if i]
        if not subtema or not sub_ids:
            continue
        try:
            etiquetados += repos.marcar_clusters_subtema(sub_ids, subtema) or 0
        except Exception:  # noqa: BLE001 -- persistir un subtema no aborta el paso
            _log.exception("recolectar_daemon: fallo al etiquetar el subtema «%s».", subtema[:60])
    return etiquetados


def paso_fusionar_semantica(
    *,
    ejecutor: fusionar_semantica.Ejecutor | None = None,
    recientes: list[dict[str, Any]] | None = None,
    forzar: bool = False,
) -> dict[str, Any]:
    """Fusiona con IA (Haiku) las historias del MISMO evento, por marca. Gateado `KENI_PIPELINE_FUSIONAR` (def ON).

    Por marca, manda hasta `KENI_FUSION_SEMANTICA_MAX` historias `nuevo` recientes a Haiku para que
    agrupe las del mismo acontecimiento, y fusiona cada grupo (`_fusionar_grupo`). Es la VÍA REAL de
    agrupación de historias del mismo evento con titulares distintos (la formación de clusters solo
    dedup-ea EXACTO: url canónica o hash de título). Best-effort: un fallo por marca/grupo se loguea
    y no aborta el paso. Devuelve `{grupos, fusionadas}`.

    Throttle: como mucho una pasada por `_FUSIONAR_INTERVALO_SEG` (no re-llamar a Haiku en cada tick
    de 30s); `forzar=True` lo salta (tests). `recientes` (opcional): los clusters de la ventana YA
    cargados por el paso de agrupar del MISMO barrido (evita re-leer la BD). None = leer de
    `repos.clusters_recientes`.
    """
    if not config.fusionar_semantica_activo():
        return {"grupos": 0, "fusionadas": 0}
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultimo_fusionar
        and (ahora_mono - _comun._ultimo_fusionar) < _comun._FUSIONAR_INTERVALO_SEG
    ):
        return {"grupos": 0, "fusionadas": 0}
    ventana_h = config.cluster_ventana_h()
    maximo = config.fusion_semantica_max()
    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    perfil_activo = config.priorizar_perfil_activo()
    ahora = datetime.now(UTC)

    if recientes is not None:
        recientes_todas = recientes
    else:
        try:
            recientes_todas = repos.clusters_recientes(ventana_h)
        except Exception:  # noqa: BLE001 -- sin pool legible, no se fusiona nada
            _log.exception("recolectar_daemon: no se pudieron leer historias para fusionar.")
            return {"grupos": 0, "fusionadas": 0}

    nuevos = [c for c in recientes_todas if (c.get("estado") or "nuevo") == "nuevo"]

    # Frescura del lote: solo lo VIVO entra al LLM. Un cluster `nuevo` sin actividad en la ventana
    # de fusión (más corta que la de agrupación) ya se digirió; reenviarlo a fusión/macro en cada
    # barrido reprocesaría historias de hace días sin nada que cambiar. Si recibe un item nuevo su
    # `ultimo_visto` avanza y reentra. También estabiliza la huella (no se mueve por lo rancio).
    corte_fusion = ahora - timedelta(hours=config.fusion_ventana_h())
    nuevos = [c for c in nuevos if _fresco_para_fusion(c, corte_fusion)]

    # Skip-if-unchanged: si el conjunto candidato no cambió desde la última pasada evaluada,
    # no hay nada nuevo que fusionar/etiquetar -> no se llama al LLM (ahorro de tokens). Un
    # cluster nuevo o uno con items nuevos mueve la huella y re-evalúa el LOTE COMPLETO (un
    # cluster nuevo debe poder fusionarse contra los `nuevo` ya existentes). `forzar` lo salta.
    huella = _comun._huella_lote(nuevos)
    if not forzar and _comun._ultima_huella_fusionar == huella:
        _comun._ultimo_fusionar = ahora_mono
        return {"grupos": 0, "fusionadas": 0}

    por_marca: dict[str, list[dict[str, Any]]] = {}
    for c in nuevos:
        por_marca.setdefault(c.get("marca") or "", []).append(c)

    grupos_total = 0
    fusionadas_total = 0
    macro_total = 0
    for marca_f, recientes in por_marca.items():
        if len(recientes) < 2:
            continue
        # Excepción por marca (toggle "Fusionar"): si está apagada para esta marca, no se fusiona.
        if config.marca_apagada(config.ENV_PIPELINE_FUSIONAR, marca_f):
            continue
        lote = recientes[:maximo]
        por_id = {str(c["id"]): c for c in lote}
        # Pesos y agenda POR MARCA (modelo v2): cada marca jerarquiza distinto y el encaje de
        # evento usa SU agenda. Una lectura por marca y barrido (la canónica fusionada es de esta).
        pesos = config.score_pesos(marca_f)
        eventos = _comun.eventos_proximos(marca_f)
        # Descarta métricas residuales de pasos previos del hilo: lo acumulado a partir de
        # aquí es el coste de Fusionar de ESTA marca (lo sella el registro de actividad).
        traducir.tomar_metricas_acumuladas()
        # Capturamos el PROMPT y la SALIDA reales de Haiku (para la transparencia de la actividad).
        haiku: dict[str, str] = {"prompt": "", "salida": ""}
        try:
            grupos = fusionar_semantica.proponer_fusiones(
                lote, ejecutor=ejecutor,
                al_ejecutar=lambda p, s, _h=haiku: _h.update(prompt=p, salida=s),
            )
        except Exception:  # noqa: BLE001 -- un fallo de Haiku por marca no aborta el paso
            _log.exception("recolectar_daemon: fallo proponiendo fusiones de una marca.")
            continue
        grupos_marca = 0
        fusionadas_marca = 0
        descripciones: list[str] = []
        for grupo in grupos:
            try:
                if _pkg._fusionar_grupo(
                    grupo, por_id, pesos=pesos, eventos=eventos, breaking_peso=breaking_peso,
                    breaking_ventana_h=breaking_ventana_h, fuentes_baja=fuentes_baja,
                    perfil_activo=perfil_activo, ahora=ahora,
                ):
                    grupos_total += 1
                    fusionadas_total += len(grupo) - 1
                    grupos_marca += 1
                    fusionadas_marca += len(grupo) - 1
                    titulos = [str((por_id.get(i) or {}).get("titulo") or i).strip() for i in grupo]
                    descripciones.append(" + ".join(t for t in titulos if t))
            except Exception:  # noqa: BLE001 -- un fusionado problemático no aborta el paso
                _log.exception("recolectar_daemon: fallo al fusionar un grupo de historias.")
        # Actividad IA: deja constancia VISIBLE de la dedup semántica por marca, con el Haiku REAL
        # (prompt + salida) y un resumen humano de qué historias se unieron.
        if grupos_marca:
            resumen = (
                "Historias del mismo acontecimiento unidas por IA (dedup semántico):\n"
                + "\n".join(f"• {d}" for d in descripciones)
            )
            salida_real = haiku["salida"].strip()
            salida = (f"{salida_real}\n\n— — —\n{resumen}" if salida_real else resumen)
            _pkg._registrar_actividad_ia(
                marca_f,
                f"Fusionar historias — {marcas.etiqueta_de(marca_f)}: "
                f"{fusionadas_marca} absorbida(s) en {grupos_marca} grupo(s)",
                salida,
                prompt=haiku["prompt"],
                etapa="Fusionar",
            )

        # Etiquetado INCREMENTAL: el LLM de macro-evento solo se invoca si hay algo que CAMBIAR —
        # un cluster SIN `tema_macro` (familia nueva por formar) o ≥2 etiquetas distintas en el lote
        # (posible sinónimo que el backstop de `_etiqueta_canonica` debe unificar a la dominante).
        # Si TODO el lote ya comparte una sola etiqueta no hay familia nueva ni split que reconciliar,
        # y `marcar_clusters_tema_macro`/`_subtema` cuentan filas EMPAREJADAS (no cambiadas): re-correr
        # reescribiría la misma etiqueta y pagaría un Haiku de macro + uno de subtema por familia en
        # CADA barrido. El bloque macro es lo último del cuerpo: `continue` lo omite.
        temas_lote = {str(c.get("tema_macro") or "").strip() for c in lote}
        if "" not in temas_lote and len(temas_lote) == 1:
            continue

        # MACRO-EVENTO (Fase A): además de FUNDIR duplicados, ETIQUETA familias de clusters
        # DISTINTOS que cubren un mismo gran evento (cumbre, desastre, torneo…) SIN fusionarlos:
        # cada sub-historia conserva su cluster y su corroboración real. Producción usa `tema_macro`
        # para armar un carrusel del evento. Best-effort: un fallo de Haiku/persistencia no aborta.
        traducir.tomar_metricas_acumuladas()  # aísla el coste del macro-evento del paso anterior
        haiku_macro: dict[str, str] = {"prompt": "", "salida": ""}
        try:
            familias = fusionar_semantica.proponer_macro_eventos(
                lote, ejecutor=ejecutor,
                al_ejecutar=lambda p, s, _h=haiku_macro: _h.update(prompt=p, salida=s),
            )
        except Exception:  # noqa: BLE001 -- un fallo de Haiku por marca no aborta el paso
            _log.exception("recolectar_daemon: fallo proponiendo macro-eventos de una marca.")
            familias = []
        etiquetadas = 0
        familias_desc: list[str] = []
        for familia in familias:
            tema_propuesto = str(familia.get("tema") or "").strip()
            ids = [str(i) for i in (familia.get("ids") or []) if i]
            if not tema_propuesto or len(ids) < 2:
                continue
            # Backstop determinista: si la familia ya tiene una etiqueta persistida, reúsala (la
            # dominante) en vez de la propuesta, para que el evento no se parta en sinónimos.
            tema = _etiqueta_canonica(ids, por_id, tema_propuesto)
            try:
                n = repos.marcar_clusters_tema_macro(ids, tema)
            except Exception:  # noqa: BLE001 -- persistir una etiqueta no aborta el paso
                _log.exception("recolectar_daemon: fallo al etiquetar el macro-evento '%s'.", tema)
                continue
            if n:
                etiquetadas += 1
                familias_desc.append(f"{tema} ({n})")
            # SUBTEMA (Fase A.2): parte la familia en facetas coherentes (partidos, espectáculo…)
            # para que cada carrusel sea de un tipo y la cadencia sea por subtema, no por evento.
            # Incremental: solo si ALGÚN cluster de la familia aún no tiene subtema (una familia ya
            # faceteada no se reenvía a Haiku). Best-effort: un fallo no aborta el etiquetado macro.
            if _falta_subtema(ids, por_id):
                _partir_en_subtemas(tema, ids, por_id, ejecutor=ejecutor)
        if etiquetadas:
            macro_total += etiquetadas
            resumen_macro = (
                "Historias agrupadas por macro-evento (NO fusionadas; cada una conserva su cluster):\n"
                + "\n".join(f"• {d}" for d in familias_desc)
            )
            salida_macro = haiku_macro["salida"].strip()
            salida_m = f"{salida_macro}\n\n— — —\n{resumen_macro}" if salida_macro else resumen_macro
            _pkg._registrar_actividad_ia(
                marca_f,
                f"Macro-evento — {marcas.etiqueta_de(marca_f)}: {etiquetadas} familia(s)",
                salida_m,
                prompt=haiku_macro["prompt"],
                etapa="Macro-evento",
            )
    _comun._ultimo_fusionar = ahora_mono
    _comun._ultima_huella_fusionar = huella
    if grupos_total:
        _log.info(
            "recolectar_daemon: fusionar semántico: %d grupo(s), %d historia(s) absorbida(s).",
            grupos_total, fusionadas_total,
        )
    if macro_total:
        _log.info("recolectar_daemon: macro-evento: %d familia(s) etiquetada(s).", macro_total)
    return {"grupos": grupos_total, "fusionadas": fusionadas_total}
