"""CD — creación de contenido: lanza copy de los temas con QA `no_verificado`.

Por cada tema cuya QA de la fuente salió `no_verificado` y que aún no tiene copy, lanza la
generación por el camino PROBADO (`dominio.generar.lanzar_copy`) con los parámetros que CI guardó
en `copy_pendiente`. Incluye también la selección del news-pool (orígenes autogen) que la etapa
de copy del pipeline redacta (fundido de `autogen_copy`).
"""

from __future__ import annotations

from typing import Any

from .. import config, marcas, redes, repos
from ..dominio import generar as gen_dom
from ..estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN
from ._comun import (
    _AUTOGEN_LANZAR_MAX,
    _FORMATO_PIPELINE,
    ETAPA_CD,
    QA_SALTADA,
    TIPO_COPY,
    VERDICTO_NO_VERIFICADO,
    _QA_REVISAR_MAX,
    _copy_pendiente_leido,
    _log,
    _tiene_copy,
    registrar_etapa,
    temas_pipeline,
)

__all__ = [
    "lanzar_copy_de_tema",
    "temas_para_copy",
    "temas_autogen_sin_copy",
]


def lanzar_copy_de_tema(tema: dict[str, Any], *, autor: dict[str, str] | None) -> dict[str, Any] | None:
    """CD — lanza la generación de copy de UN tema cuya QA de la fuente salió `no_verificado`.

    Reutiliza el lanzador PROBADO `dominio.generar.lanzar_copy` con los parámetros que CI guardó
    en `copy_pendiente` (nota, redes, imagen ya resuelta, fuente, clave). El borrador resultante
    cuelga del tema (`contenido_id`) y hereda su origen. Para marca PROPIA con `og:image`, la
    pieza nace con esa imagen (`tipo_contenido='fuente'`). Registra la etapa CD y limpia
    `copy_pendiente` (evita relanzar). None si se omite (sin parámetros / marca inválida).
    """
    tema_id = (tema.get("id") or "").strip()
    marca = (tema.get("marca") or "").strip()
    if not tema_id or not marca or not marcas.es_marca(marca):
        return None
    pend = _copy_pendiente_leido(tema)
    nota = (pend.get("nota") or tema.get("descripcion") or "").strip()
    if not nota:
        return None
    titulo = (tema.get("titulo") or "").strip()
    redes_ids = [r for r in (pend.get("redes_ids") or []) if redes.es_red(r)] or list(
        redes.redes_de_formato(_FORMATO_PIPELINE)
    )
    imagen = (pend.get("imagen") or "").strip()
    tipo_contenido = "fuente" if imagen else ""
    fuente_id = (pend.get("fuente_id") or "").strip() or None
    clave = (pend.get("clave") or "").strip() or None
    gen = gen_dom.lanzar_copy(
        # `pipeline`: la generación REAL (claude -p) queda etiquetada como pipeline y reporta
        # sus tokens/coste/tiempo en Actividad IA (el resto del flujo —CI/QA— no cuesta).
        tipo=TIPO_COPY,
        marca=marca,
        contexto=nota,
        redes_ids=redes_ids,
        titulo=titulo,
        titulo_dado=titulo,
        texto_base=nota,
        autor=autor,
        fuente_id=fuente_id,
        clave=clave,
        contenido_id=tema_id,
        imagen_fuente=imagen,
        tipo_contenido=tipo_contenido,
        # La fuente pasó como `no_verificado` (criba permisiva, sin verificación a fondo): las
        # piezas heredan ese aviso (⚠️) en su veredicto, para que la parrilla y Pipelines lo
        # muestren. Si el copy trajera un veredicto propio, ese manda; aquí da el por defecto.
        veredicto_inicial=VERDICTO_NO_VERIFICADO,
    )
    # Limpia `copy_pendiente`: el copy ya se lanzó; la fase CD no debe relanzarlo (idempotencia).
    try:
        repos.actualizar_contenido(tema_id, {"copy_pendiente": ""})
    except Exception:  # noqa: BLE001 -- best-effort; sin esto, la guarda "sin copy" lo evita igual
        _log.warning("pipeline: no se pudo limpiar copy_pendiente (%s)", tema_id, exc_info=True)
    registrar_etapa(
        ETAPA_CD,
        marca,
        f"Generación de copy+arte de marca — '{titulo[:120]}'",
        contenido_id=tema_id,
        # Ata el marcador CD a la generación REAL de copy: su STREAM (proceso del agente)
        # se muestra en el detalle del pipeline.
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def temas_para_copy(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas listos para CD: QA `no_verificado` (o `saltada`), con `copy_pendiente` y SIN copy aún.

    La guarda de DOS niveles (copy_pendiente no vacío + sin piezas) hace la fase CD idempotente
    y auto-curativa: un tema cuyo copy ya se lanzó no se relanza aunque su `copy_pendiente` no se
    hubiera limpiado (p. ej. tras un fallo). Best-effort. Un tema con QA `saltada` (etapa QA
    desactivada para la marca) fluye a CD igual que uno `no_verificado`; un `problema` sí bloquea.
    """
    listos: list[dict[str, Any]] = []
    for tema in temas_pipeline(marca):
        if (tema.get("qa_veredicto") or "") not in (VERDICTO_NO_VERIFICADO, QA_SALTADA):
            continue
        if not (tema.get("copy_pendiente") or "").strip():
            continue
        if _tiene_copy(tema.get("id", "") or ""):
            continue
        listos.append(tema)
        # Recorte SOBRE LOS LISTOS (no sobre la lista cruda): así un backlog grande no deja
        # fuera de la ventana a los temas nuevos, y se acota el nº de `_tiene_copy` (1 query/tema).
        if len(listos) >= _QA_REVISAR_MAX:
            break
    return listos


def temas_autogen_sin_copy() -> list[dict[str, Any]]:
    """Temas del news-pool/tablero sin copy que la etapa de copy debe redactar (FUNDE autogen_copy).

    La etapa de copy del pipeline es el ÚNICO motor de copy: además de los temas que el propio
    pipeline ingiere (origen `pipeline`, vía QA→CD), también redacta los temas que las FUENTES
    de noticias meten al tablero (`estados.ORIGENES_AUTOGEN`: import-calendario, radar-auto,
    radar, rss, equipo) y que aún no tienen copy. Reglas (espejo de `autogen_copy.topics_pendientes`):
      - clase 'contenido', origen en `ORIGENES_AUTOGEN`, estado != 'hecha',
      - con marca válida y título no vacío,
      - per-marca: salta las marcas apagadas a mano para «Generar copy» (`ENV_PIPELINE`),
      - dedup: salta los ya encolados (etiqueta `autogen`) y los que ya tienen copy,
      - cap `_AUTOGEN_LANZAR_MAX` por barrido.
    Best-effort: una lectura fallida devuelve []. Import diferido de `autogen_copy` para reusar su
    dedup por etiqueta sin acoplar la carga del módulo.
    """
    from .. import autogen_copy

    try:
        items = repos.listar_contenido()
    except Exception:  # noqa: BLE001 -- sin tablero legible, la etapa no actúa sobre el pool
        return []
    ya_generados = autogen_copy.ids_ya_generados()
    elegidos: list[dict[str, Any]] = []
    for item in items:
        if len(elegidos) >= _AUTOGEN_LANZAR_MAX:
            break
        if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            continue
        if (item.get("origen") or "") not in ORIGENES_AUTOGEN:
            continue
        if (item.get("estado") or "") == "hecha":
            continue
        marca = item.get("marca") or ""
        if not marca or not marcas.es_marca(marca):
            continue
        if config.marca_apagada(config.ENV_PIPELINE, marca):
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if item.get("id") in ya_generados:
            continue
        if _tiene_copy(item.get("id", "") or ""):
            continue
        elegidos.append(item)
    return elegidos
