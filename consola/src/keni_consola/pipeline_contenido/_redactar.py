"""CD — creación de contenido: lanza copy de los temas con verificación `verificado`.

Por cada tema cuya verificación de la fuente salió `verificado` y que aún no tiene copy, lanza la
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
    VERIFICACION_SALTADA,
    TIPO_PIPELINE,
    VERIFICACION_VERIFICADO,
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
    "preview_redactar_por_marca",
    "encadenar_ilustrar_tras_redactar",
]

# Revisión INICIAL de la pieza auto-producida. Es un eje DISTINTO del veredicto de FUENTE: si la
# fuente se VERIFICÓ a fondo (`verificado`), la pieza nace sin aviso (sujeta al chequeo de voz); si
# la verificación se SALTÓ (`saltada`, fuente propia que la IA no verificó), hereda el ⚠️
# `no_verificado` para que la parrilla y Pipelines lo muestren.
_REVISION_PIEZA_VERIFICADA = "listo"
_REVISION_PIEZA_SIN_VERIFICAR = "no_verificado"


def lanzar_redactar_de_tema(tema: dict[str, Any], *, autor: dict[str, str] | None) -> dict[str, Any] | None:
    """CD — lanza la generación de copy de UN tema cuya verificación de la fuente salió `verificado`.

    Reutiliza el lanzador PROBADO `dominio.generar.lanzar_copy` con los parámetros que CI guardó
    en `copy_pendiente` (nota, redes, imagen ya resuelta, fuente, clave). El borrador resultante
    cuelga del tema (`publicacion_id`) y hereda su origen. Para marca PROPIA con `og:image`, la
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
    # que asigne foto a cada slide). Pendientes sin estos campos: n_notas=1 (sin carrusel).
    fotos_notas = [
        {"titulo": str(f.get("titulo") or ""), "imagen": str(f.get("imagen") or "").strip()}
        for f in (pend.get("fotos_notas") or [])
        if isinstance(f, dict) and str(f.get("imagen") or "").strip()
    ]
    try:
        n_notas = max(1, int(pend.get("n_notas") or 1))
    except (TypeError, ValueError):
        n_notas = 1
    # CAMINO elegido por el Decisor (etapa previa): "foto"|"carrusel". Lo guardó el Decisor en
    # `copy_pendiente`. "" (sin Decisor / flag OFF) = Redactar decide el formato dentro de su prompt
    # (comportamiento de hoy).
    camino = (pend.get("camino") or "").strip()
    tipo_contenido = "fuente" if imagen else ""
    fuente_id = (pend.get("fuente_id") or "").strip() or None
    clave = (pend.get("clave") or "").strip() or None
    # ORIGEN real de la IMAGEN del artículo (id de `fuentes_rss` del item que la traía): viaja
    # hasta el catálogo de esa foto para distinguir portal-propio de RSS-externo.
    origen_fuente_id = (pend.get("origen_fuente_id") or "").strip()
    gen = gen_dom.lanzar_copy(
        # `pipeline`: la generación REAL (claude -p) queda etiquetada como pipeline y reporta
        # sus tokens/coste/tiempo en Actividad IA (el resto del flujo —CI/verificación— no cuesta).
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
        publicacion_id=tema_id,
        imagen_fuente=imagen,
        origen_fuente_id=origen_fuente_id,
        fotos_notas=fotos_notas,
        n_notas=n_notas,
        camino=camino,
        tipo_contenido=tipo_contenido,
        # Revisión inicial según el veredicto de FUENTE: `verificado` (la IA la confirmó a fondo)
        # -> pieza sin aviso (sujeta al chequeo de voz); `saltada` (fuente propia, sin verificar por
        # IA) -> ⚠️ `no_verificado`. Si el copy trae su propio veredicto, ese manda.
        revision_inicial=(
            _REVISION_PIEZA_VERIFICADA
            if (tema.get("verificacion_fuente") or "") == VERIFICACION_VERIFICADO
            else _REVISION_PIEZA_SIN_VERIFICAR
        ),
        # Dedup al ÉXITO: el post-procesado limpia `copy_pendiente` cuando los borradores ya
        # existen. Un copy fallido conserva la marca y el barrido lo reintenta.
        limpiar_pendiente=True,
    )
    registrar_etapa(
        ETAPA_REDACTAR,
        marca,
        f"Generación de copy+arte de marca — '{titulo[:120]}'",
        publicacion_id=tema_id,
        # Ata el marcador CD a la generación REAL de copy: su STREAM (proceso del agente)
        # se muestra en el detalle del pipeline.
        gen_id=gen.get("id", "") if isinstance(gen, dict) else "",
    )
    return gen


def temas_para_redactar(marca: str | None = None) -> list[dict[str, Any]]:
    """Temas listos para CD: verificación `verificado` (o `saltada`), con `copy_pendiente` y SIN copy aún.

    La guarda de DOS niveles (copy_pendiente no vacío + sin piezas) hace la fase CD idempotente:
    un tema cuyo copy ya se lanzó no se relanza aunque su `copy_pendiente` no se hubiera limpiado.
    Un tema con verificación `saltada` (fuente propia, sin verificar por IA) fluye a CD igual que uno
    `verificado`; `requiere_humano`/`rechazado` sí bloquean.
    """
    listos: list[dict[str, Any]] = []
    for tema in temas_pipeline(marca):
        if (tema.get("verificacion_fuente") or "") not in (VERIFICACION_VERIFICADO, VERIFICACION_SALTADA):
            continue
        if not (tema.get("copy_pendiente") or "").strip():
            continue
        if _tiene_copy(tema.get("id", "") or ""):
            continue
        listos.append(tema)
        # Carril 1 (temas del propio pipeline): el volumen lo acota la ADMISIÓN (gate serial en
        # curso por marca) y el backpressure de la cola (`ColaLlenaError` corta la fase; el
        # siguiente tick reintenta). El tope por marca/barrido vive en el carril 2
        # (`temas_autogen_sin_copy`, vía `config.autogen_copy_max`), no aquí.
    return listos


def temas_autogen_sin_copy() -> list[dict[str, Any]]:
    """Temas del news-pool/tablero sin copy que la etapa de Redactar debe redactar.

    La etapa de Redactar del pipeline es el ÚNICO motor de copy: además de los temas que el propio
    pipeline ingiere (origen `pipeline`, vía verificación→CD), también redacta los temas que las FUENTES
    de noticias meten al tablero (`estados.ORIGENES_AUTOGEN`: import-calendario, radar-auto,
    radar, rss, equipo) y que aún no tienen copy. La selección vive en esta función; en
    `autogen_redactar` solo el LANZADOR `lanzar_para_topic` + el dedup por etiqueta. Reglas:
      - clase 'contenido', origen en `ORIGENES_AUTOGEN`, estado != 'hecha',
      - con marca válida y título no vacío,
      - per-marca: salta las marcas apagadas a mano para «Generar copy» (`ENV_PIPELINE_REDACTAR`),
      - dedup: salta los ya encolados (etiqueta `autogen`, vía `autogen_redactar.ids_ya_generados`) y
        los que ya tienen copy,
      - tope por marca y barrido: como mucho `config.autogen_copy_max(marca)` temas de cada marca
        (override por marca > default global), para que activar una marca con backlog no dispare
        una ráfaga de copy; conserva el orden de selección (se quedan los primeros N por marca).
    Best-effort: una lectura fallida devuelve [].
    """
    from .. import autogen_redactar

    try:
        items = repos.listar_publicaciones_origenes(
            sorted(ORIGENES_AUTOGEN), excluir_estado="hecha"
        )
    except Exception:  # noqa: BLE001 -- sin tablero legible, la etapa no actúa sobre el pool
        return []
    ya_generados = autogen_redactar.ids_ya_generados()
    elegidos: list[dict[str, Any]] = []
    # Tope POR MARCA Y BARRIDO (`config.autogen_copy_max`): cuántos temas de cada marca caben en
    # esta pasada. `por_marca` cuenta los ya elegidos; `caps` cachea el tope por marca (una lectura
    # del store por marca y barrido). Conserva el orden de selección: se quedan los primeros N.
    por_marca: dict[str, int] = {}
    caps: dict[str, int] = {}
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
        if not config.etapa_activa(config.ENV_PIPELINE_REDACTAR, marca):
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if item.get("id") in ya_generados:
            continue
        tema_id = item.get("id", "") or ""
        # Un tema SIN ninguna pieza no es redactable: el copy no tendría dónde aterrizar, así que
        # nunca quedaría "con copy" y el barrido lo re-elegiría cada ciclo (bucle de gasto). Hoy las
        # vías de admisión crean piezas por defecto; este guard corta cualquier tema malformado.
        if not repos.listar_piezas_fila(tema_id):
            continue
        if _tiene_copy(tema_id):
            continue
        cap = caps.get(marca)
        if cap is None:
            cap = config.autogen_copy_max(marca)
            caps[marca] = cap
        if por_marca.get(marca, 0) >= cap:
            continue
        elegidos.append(item)
        por_marca[marca] = por_marca.get(marca, 0) + 1
    return elegidos


def preview_redactar_por_marca() -> dict[str, int]:
    """Cuenta, POR MARCA, cuántos temas autogenerables SIN copy entrarían a Redactar AHORA MISMO.

    Es el MISMO cómputo de selección que `temas_autogen_sin_copy` (orígenes autogen, clase
    contenido, no `hecha`, marca válida, título no vacío, no ya encolado, con pieza donde
    aterrizar y sin copy) PERO ignorando el gate `etapa_activa(ENV_PIPELINE_REDACTAR, marca)`:
    responde «cuántos habría SI la etapa estuviera encendida», agrupados por marca. PREVIEW puro:
    NO lanza ni encola nada. Best-effort: `{}` si el tablero no es legible.
    """
    from .. import autogen_redactar

    try:
        items = repos.listar_publicaciones_origenes(
            sorted(ORIGENES_AUTOGEN), excluir_estado="hecha"
        )
    except Exception:  # noqa: BLE001 -- sin tablero legible, el preview no puede contar
        return {}
    ya_generados = autogen_redactar.ids_ya_generados()
    conteo: dict[str, int] = {}
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
        if not (item.get("titulo") or "").strip():
            continue
        if item.get("id") in ya_generados:
            continue
        tema_id = item.get("id", "") or ""
        if not repos.listar_piezas_fila(tema_id):
            continue
        if _tiene_copy(tema_id):
            continue
        conteo[marca] = conteo.get(marca, 0) + 1
    return conteo


# --------------------------------------------------------------------------- #
# Encadenado por EVENTOS (verificación -> copy -> arte), sin esperar al siguiente barrido #
# --------------------------------------------------------------------------- #


def encadenar_ilustrar_tras_redactar(publicacion_id: str) -> dict[str, Any] | None:
    """Dispara la etapa de Ilustrar de UN tema justo tras crearse sus borradores (por eventos).

    Lo llama el POST-PROCESADO del copy (worker) cuando el copy nidó piezas bajo un tema:
    ilustra ESE tema al instante en vez de esperar al barrido. MISMOS gates que
    `ejecutar_ilustrar`: toggle "Generar arte" + máquina (`gate_maquina`), proveedor de imagen
    configurado, exclusión por marca y dedup por etiqueta `autogen-arte`. Best-effort: un
    fallo se loguea y lo recogerá el barrido. Devuelve lo adjuntado o None si se omite.
    """
    if not publicacion_id:
        return None
    if not config.gate_maquina(lambda: config.alguna_marca_con_etapa(config.ENV_PIPELINE_ILUSTRAR))():
        return None
    from .. import autogen_ilustrar, media

    try:
        if not media.proveedor_configurado():
            return None
        tema = repos.obtener_publicacion(publicacion_id)
        if not tema:
            return None
        if (tema.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            return None
        if (tema.get("estado") or "") == "hecha":
            return None
        if not (tema.get("titulo") or "").strip():
            return None
        if not config.etapa_activa(config.ENV_PIPELINE_ILUSTRAR, tema.get("marca") or ""):
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
            publicacion_id, exc_info=True,
        )
        return None
