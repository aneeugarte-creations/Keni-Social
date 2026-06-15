"""CD — creación de contenido: lanza copy de los temas con QA `no_verificado`.

Por cada tema cuya QA de la fuente salió `no_verificado` y que aún no tiene copy, lanza la
generación por el camino PROBADO (`dominio.generar.lanzar_copy`) con los parámetros que CI guardó
en `copy_pendiente`. Incluye también la selección del news-pool (orígenes autogen) que la etapa
de Redactar del pipeline redacta (fundido de `autogen_redactar`).
"""

from __future__ import annotations

from typing import Any

from .. import config, generaciones, marcas, redes, repos
from ..dominio import generar as gen_dom
from ..estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN
from ._comun import (
    _FORMATO_PIPELINE,
    ETAPA_REDACTAR,
    QA_SALTADA,
    TIPO_PIPELINE,
    VERDICTO_NO_VERIFICADO,
    _copy_pendiente_leido,
    _log,
    _tiene_copy,
    registrar_etapa,
    temas_pipeline,
)

__all__ = [
    "lanzar_redactar_de_tema",
    "temas_para_redactar",
    "temas_autogen_sin_copy",
    "encadenar_redactar_tras_verificar",
    "encadenar_ilustrar_tras_redactar",
]


def lanzar_redactar_de_tema(tema: dict[str, Any], *, autor: dict[str, str] | None) -> dict[str, Any] | None:
    """CD — lanza la generación de copy de UN tema cuya QA de la fuente salió `no_verificado`.

    Reutiliza el lanzador PROBADO `dominio.generar.lanzar_copy` con los parámetros que CI guardó
    en `copy_pendiente` (nota, redes, imagen ya resuelta, fuente, clave). El borrador resultante
    cuelga del tema (`contenido_id`) y hereda su origen. Para marca PROPIA con `og:image`, la
    pieza nace con esa imagen (`tipo_contenido='fuente'`). Registra la etapa CD. None si se
    omite (sin parámetros / marca inválida).

    DEDUP AL ÉXITO (no al lanzar): `copy_pendiente` lo limpia el POST-PROCESADO del copy al
    completar con éxito (`limpiar_pendiente=True`), no este lanzador. Mientras el job está en
    curso no hay doble lanzamiento: la clave de idempotencia de `dominio.generar.lanzar` devuelve
    el run en curso, y `temas_para_redactar` además excluye los temas que ya tienen piezas.
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
    # CARRUSEL EDITORIAL: cuántas SUB-HISTORIAS agrupa la historia (con 2+, el prompt ofrece
    # al modelo decidir entre post y carrusel) y el catálogo de fotos propias por nota (para
    # que asigne foto a cada slide). Pendientes anteriores sin estos campos: n_notas=1 (sin
    # carrusel), comportamiento de siempre.
    fotos_notas = [
        {"titulo": str(f.get("titulo") or ""), "imagen": str(f.get("imagen") or "").strip()}
        for f in (pend.get("fotos_notas") or [])
        if isinstance(f, dict) and str(f.get("imagen") or "").strip()
    ]
    try:
        n_notas = max(1, int(pend.get("n_notas") or 1))
    except (TypeError, ValueError):
        n_notas = 1
    tipo_contenido = "fuente" if imagen else ""
    fuente_id = (pend.get("fuente_id") or "").strip() or None
    clave = (pend.get("clave") or "").strip() or None
    gen = gen_dom.lanzar_copy(
        # `pipeline`: la generación REAL (claude -p) queda etiquetada como pipeline y reporta
        # sus tokens/coste/tiempo en Actividad IA (el resto del flujo —CI/QA— no cuesta).
        tipo=TIPO_PIPELINE,
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
        fotos_notas=fotos_notas,
        n_notas=n_notas,
        tipo_contenido=tipo_contenido,
        # La fuente pasó como `no_verificado` (verificación permisiva, sin verificación a fondo): las
        # piezas heredan ese aviso (⚠️) en su veredicto, para que la parrilla y Pipelines lo
        # muestren. Si el copy trajera un veredicto propio, ese manda; aquí da el por defecto.
        veredicto_inicial=VERDICTO_NO_VERIFICADO,
        # Dedup al ÉXITO: el post-procesado limpia `copy_pendiente` cuando los borradores ya
        # existen. Un copy fallido conserva la marca y el barrido lo reintenta.
        limpiar_pendiente=True,
    )
    registrar_etapa(
        ETAPA_REDACTAR,
        marca,
        f"Generación de copy+arte de marca — '{titulo[:120]}'",
        contenido_id=tema_id,
        # Ata el marcador CD a la generación REAL de copy: su STREAM (proceso del agente)
        # se muestra en el detalle del pipeline.
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def temas_para_redactar(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas listos para CD: QA `no_verificado` (o `saltada`), con `copy_pendiente` y SIN copy aún.

    La guarda de DOS niveles (copy_pendiente no vacío + sin piezas) hace la fase CD idempotente:
    un tema cuyo copy ya se lanzó no se relanza aunque su `copy_pendiente` no se hubiera limpiado.
    Un tema con QA `saltada` (etapa QA desactivada para la marca) fluye a CD igual que uno
    `no_verificado`; un `problema` sí bloquea.
    """
    listos: list[dict[str, Any]] = []
    for tema in temas_pipeline(marca):
        if (tema.get("verificar_veredicto") or "") not in (VERDICTO_NO_VERIFICADO, QA_SALTADA):
            continue
        if not (tema.get("copy_pendiente") or "").strip():
            continue
        if _tiene_copy(tema.get("id", "") or ""):
            continue
        listos.append(tema)
        # SIN recorte: el volumen lo acota la ADMISIÓN (gate serial en curso por marca) y el
        # backpressure de la cola (`ColaLlenaError` corta la fase; el siguiente tick reintenta).
    return listos


def temas_autogen_sin_copy() -> list[dict[str, Any]]:
    """Temas del news-pool/tablero sin copy que la etapa de Redactar debe redactar.

    La etapa de Redactar del pipeline es el ÚNICO motor de copy: además de los temas que el propio
    pipeline ingiere (origen `pipeline`, vía QA→CD), también redacta los temas que las FUENTES
    de noticias meten al tablero (`estados.ORIGENES_AUTOGEN`: import-calendario, radar-auto,
    radar, rss, equipo) y que aún no tienen copy. La selección vive en esta función; en
    `autogen_redactar` solo el LANZADOR `lanzar_para_topic` + el dedup por etiqueta. Reglas:
      - clase 'contenido', origen en `ORIGENES_AUTOGEN`, estado != 'hecha',
      - con marca válida y título no vacío,
      - per-marca: salta las marcas apagadas a mano para «Generar copy» (`ENV_PIPELINE_REDACTAR`),
      - dedup: salta los ya encolados (etiqueta `autogen`, vía `autogen_redactar.ids_ya_generados`) y
        los que ya tienen copy.
    SIN cap propio: el backpressure lo pone la cola de generación. Best-effort: una lectura
    fallida devuelve [].
    """
    from .. import autogen_redactar

    try:
        items = repos.listar_contenido_origenes(
            sorted(ORIGENES_AUTOGEN), excluir_estado="hecha"
        )
    except Exception:  # noqa: BLE001 -- sin tablero legible, la etapa no actúa sobre el pool
        return []
    ya_generados = autogen_redactar.ids_ya_generados()
    elegidos: list[dict[str, Any]] = []
    for item in items:
        if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            continue
        if (item.get("origen") or "") not in ORIGENES_AUTOGEN:
            continue
        if (item.get("estado") or "") == "hecha":
            continue
        marca = item.get("marca") or ""
        if not marca or not marcas.es_marca(marca):
            continue
        if config.marca_apagada(config.ENV_PIPELINE_REDACTAR, marca):
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if item.get("id") in ya_generados:
            continue
        if _tiene_copy(item.get("id", "") or ""):
            continue
        elegidos.append(item)
    return elegidos


# --------------------------------------------------------------------------- #
# Encadenado por EVENTOS (QA -> copy -> arte), sin esperar al siguiente barrido #
# --------------------------------------------------------------------------- #


def encadenar_redactar_tras_verificar(
    contenido_id: str, *, autor: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """Dispara el copy de UN tema justo tras persistirse su veredicto de QA (por eventos).

    Lo llama el POST-PROCESADO de la QA de la fuente (worker) cuando el veredicto sale
    `no_verificado`: antes cada etapa esperaba al siguiente barrido de 20 min (40-60 min en
    total para 3-8 min de LLM). El barrido queda como RED DE SEGURIDAD (recoge lo que el
    encadenado pierda). Respeta los MISMOS gates que la fase CD: toggle global de copy
    (`KENI_PIPELINE_REDACTAR`), exclusión por marca y las guardas de dedup (`copy_pendiente`
    presente + sin piezas aún). `ColaLlenaError` NO rompe el procesar de la QA: se loguea y
    el barrido lo reintenta. Devuelve la generación lanzada o None si se omite.
    """
    if not contenido_id or not config.pipeline_activo():
        return None
    try:
        tema = repos.obtener_contenido(contenido_id)
    except Exception:  # noqa: BLE001 -- sin tema legible, el barrido lo recogerá
        return None
    if not tema:
        return None
    if (tema.get("verificar_veredicto") or "") not in (VERDICTO_NO_VERIFICADO, QA_SALTADA):
        return None
    if not (tema.get("copy_pendiente") or "").strip():
        return None
    if config.marca_apagada(config.ENV_PIPELINE_REDACTAR, tema.get("marca") or ""):
        return None
    if _tiene_copy(tema.get("id", "") or ""):
        return None
    try:
        return lanzar_redactar_de_tema(tema, autor=autor)
    except generaciones.ColaLlenaError:
        # SEGURO perderlo aquí: el tema conserva veredicto apto + `copy_pendiente` y sigue sin
        # piezas, así que `temas_para_redactar` lo selecciona en el siguiente tick del barrido.
        _log.warning(
            "pipeline: cola llena al encadenar copy del tema %s (marca %s); el barrido lo recogerá.",
            contenido_id, tema.get("marca", ""),
        )
        return None


def encadenar_ilustrar_tras_redactar(contenido_id: str) -> dict[str, Any] | None:
    """Dispara la etapa de Ilustrar de UN tema justo tras crearse sus borradores (por eventos).

    Lo llama el POST-PROCESADO del copy (worker) cuando el copy nidó piezas bajo un tema:
    ilustra ESE tema al instante en vez de esperar al barrido. MISMOS gates que
    `ejecutar_ilustrar`: toggle "Generar arte" + máquina (`gate_maquina`), proveedor de imagen
    configurado, exclusión por marca y dedup por etiqueta `autogen-arte`. Best-effort: un
    fallo se loguea y lo recogerá el barrido. Devuelve lo adjuntado o None si se omite.
    """
    if not contenido_id:
        return None
    if not config.gate_maquina(config.ilustrar_activo)():
        return None
    from .. import autogen_ilustrar, media

    try:
        if not media.proveedor_configurado():
            return None
        tema = repos.obtener_contenido(contenido_id)
        if not tema:
            return None
        if (tema.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            return None
        if (tema.get("estado") or "") == "hecha":
            return None
        if not (tema.get("titulo") or "").strip():
            return None
        if config.marca_apagada(config.ENV_PIPELINE_ILUSTRAR, tema.get("marca") or ""):
            return None
        if (tema.get("id") or "") in autogen_ilustrar.ids_ya_procesados():
            return None
        return autogen_ilustrar.lanzar_para_topic(tema)
    except Exception:  # noqa: BLE001 -- el barrido de arte lo recogerá
        # SEGURO perderlo aquí (incluida `ColaLlenaError`): la etiqueta `autogen-arte` (el dedup
        # que consulta `topics_sin_arte`) solo se asigna AL ÉXITO dentro de `lanzar_para_topic`;
        # un fallo deja el tema SIN etiqueta y el barrido de arte lo vuelve a elegir con certeza.
        _log.warning(
            "pipeline: fallo el encadenado copy->arte del tema %s; el barrido lo recogerá.",
            contenido_id, exc_info=True,
        )
        return None
