"""Post-procesado de generaciones de COPY/DOCUMENTO (parseo + artefactos), NEUTRO.

Estas fábricas convierten la salida cruda de `claude -p` en los ARTEFACTOS de la Consola
(piezas por red, publicaciones-borrador, historial, imágenes previsualizadas). Son DOMINIO
PURO: dependen de `stream` (parseo), `repos` (historial), `dominio.publicaciones` (handoff
A→C de borradores), `redes` y `media`. NO dependen del catálogo de skills.

Viven aquí (y ya no en `dominio.skills`) porque son el post-procesado de CUALQUIER
generación de copy, venga de la Texto de prompts o de donde sea: al retirar el sistema
de skills, este módulo es su hogar estable. `jobspec.reconstruir_procesar` los reconstruye
en el worker desde el `spec`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .. import redes, repos
from . import publicaciones as contrato_publicaciones
from . import stream

if TYPE_CHECKING:
    # `generaciones` solo se usa en anotaciones (`-> generaciones.Procesar`). Mantener el
    # dominio NEUTRO: no importa de `generaciones` en runtime (invariante de `dominio/`).
    from .. import generaciones

# --------------------------------------------------------------------------- #
# Cosecha de IMAGENES de salida (skills/prompts de imagen)                     #
# --------------------------------------------------------------------------- #

# Extensiones de imagen que reconocemos en la salida.
_EXT_IMAGEN = ("png", "jpg", "jpeg", "webp", "gif")

# Ruta a un archivo de imagen dentro del texto (absoluta o relativa con separadores).
_RE_RUTA_IMAGEN = re.compile(
    r"(/?(?:[^\s\"'`<>|]+/)+[^\s\"'`<>|]+\.(?:" + "|".join(_EXT_IMAGEN) + r"))",
    re.IGNORECASE,
)

# Tope defensivo de imagenes que importamos de una sola salida.
_MAX_IMAGENES = 12


def _rutas_imagen_en_texto(salida: str) -> list[str]:
    """Extrae rutas de archivos de imagen mencionadas en la salida (orden, sin duplicar)."""
    if not salida:
        return []
    vistas: list[str] = []
    for m in _RE_RUTA_IMAGEN.finditer(salida):
        ruta = m.group(1)
        if ruta not in vistas:
            vistas.append(ruta)
    return vistas


def cosechar_imagenes(salida: str) -> list[dict[str, str]]:
    """Importa al almacen de media las imagenes que la salida menciona por ruta.

    Tolerante: una ruta inexistente o no importable se OMITE (la previsualizacion es un
    extra, nunca rompe la generacion). Limita a `_MAX_IMAGENES`.
    """
    from .. import media

    imagenes: list[dict[str, str]] = []
    for ruta in _rutas_imagen_en_texto(salida):
        if len(imagenes) >= _MAX_IMAGENES:
            break
        try:
            nombre = media.importar_imagen(ruta)
        except media.MediaError:
            continue
        except Exception:  # noqa: BLE001 -- la previsualizacion nunca rompe la generacion
            continue
        imagenes.append({"nombre": nombre, "url": f"/api/media/{nombre}"})
    return imagenes


# --------------------------------------------------------------------------- #
# Creacion de publicaciones (borrador) por pieza                              #
# --------------------------------------------------------------------------- #


def crear_publicaciones_desde_piezas(
    piezas: list[dict[str, object]],
    *,
    marca: str,
    titulo: str,
    verdicto: str,
    origen: str,
    redes_filtro: set[str] | None = None,
    autor: dict[str, str] | None = None,
    contenido_id: str = "",
    atomico: bool = False,
    imagen_fuente: str = "",
    tipo_contenido: str = "",
) -> list[dict[str, object]]:
    """Crea UNA publicacion (borrador) por pieza y devuelve sus dicts serializados.

    HANDOFF A->C (ADR 0005 §Seams #1): cada pieza se deposita como BORRADOR por la
    funcion-contrato `dominio.publicaciones.crear_borrador` (nace `borrador`). Si
    `redes_filtro` no es None, solo se crean las piezas cuya red este en el filtro.

    NIDO BAJO EL TEMA (lista viva): si `contenido_id` apunta a un tema del tablero existente,
    cada pieza se ADJUNTA a ESE `contenido` (via `crear_borrador_en`) en vez de crear su
    propio padre, de modo que el borrador cuelga de la tarjeta del tema. Sin `contenido_id`
    (default ""), o si el tema no existe, es EXACTAMENTE el comportamiento de hoy.

    `atomico` (default False): TODO-O-NADA. La capa de datos persiste cada borrador por su
    cuenta (sin transacción cross-fila); con `atomico=True`, si la creación de una pieza
    falla a mitad, se BORRAN las ya creadas y se RELANZA, para no dejar publicaciones rotas.
    Lo usa el "Guardar como publicación" del termómetro; el auto-copy lo deja en False
    (best-effort, no debe abortar toda la generación por una pieza).
    """
    creadas: list[dict[str, object]] = []
    # Imagen ORIGINAL de fuente (RSS de marca propia): la DESCARGAMOS una sola vez a media
    # (S3) para que la pieza nazca con un asset propio PUBLICABLE (no una URL externa que
    # puede caducar). Tolerante: si la descarga falla, `imagen_descargada` queda "" y la
    # pieza cae a `imagen_url`=`imagen_fuente` (visible, aunque no publicable).
    imagen_descargada = ""
    if imagen_fuente:
        from . import extraccion_url

        try:
            imagen_descargada = extraccion_url.descargar_imagen_a_media(imagen_fuente)
        except Exception:  # noqa: BLE001 -- la descarga es un extra; nunca rompe la generación
            imagen_descargada = ""
    try:
        for pieza in piezas:
            red = pieza.get("red")
            contenido = pieza.get("contenido")
            copy_in = pieza.get("copy_in")
            if not isinstance(red, str) or not redes.es_red(red):
                continue
            if redes_filtro is not None and red not in redes_filtro:
                continue
            if not isinstance(contenido, str):
                contenido = ""
            if not isinstance(copy_in, str):
                copy_in = ""
            # Con imagen ORIGINAL de fuente usamos la descargada a media (asset propio
            # publicable); si la descarga falló, "" y la pieza cae a la URL original. Sin
            # fuente, NO se hornea placa al crear: la placa de marca se RENDERIZA ON-DEMAND
            # desde la receta (marca + copy_in) cuando se muestra/publica (ver `render_pieza`).
            # Así no se duplica un PNG por cada pieza con el mismo logo/pleca y solo cambia el texto.
            imagen = imagen_descargada if imagen_fuente else ""
            creada: dict[str, object] | None = None
            if contenido_id:
                # Nido bajo el tema: adjunta la pieza al `contenido` existente. Devuelve None si
                # el tema no existe (entonces caemos al borrador suelto).
                creada = contrato_publicaciones.crear_borrador_en(
                    contenido_id, marca, red, titulo=titulo, contenido=contenido,
                    copy_in=copy_in, veredicto=verdicto, imagen=imagen,
                    imagen_fuente=imagen_fuente,
                )
            if creada is None:
                creada = contrato_publicaciones.crear_borrador(
                    marca, red, titulo=titulo, contenido=contenido, copy_in=copy_in,
                    veredicto=verdicto, origen=origen, autor=autor, imagen=imagen,
                    imagen_fuente=imagen_fuente, tipo_contenido=tipo_contenido,
                )
            creadas.append(creada)
    except Exception:
        if atomico:
            _revertir_borradores([str(p.get("id")) for p in creadas if p.get("id")])
        raise
    return creadas


def _revertir_borradores(ids: list[str]) -> None:
    """Borra borradores ya creados (rollback de un guardado a medias). Tolerante a fallos."""
    for pid in ids:
        try:
            repos.borrar_publicacion(pid)
        except Exception:  # noqa: BLE001 -- el rollback nunca debe enmascarar el error original
            continue


def _persistir_url_fuente(publicaciones: list[dict[str, object]], url_fuente: str) -> None:
    """Persiste `url_fuente` en el `contenido` padre de cada borrador creado (dedup por URL).

    POST-HOC: cada borrador serializado trae el `contenido_id` de su tema padre (sea uno nuevo
    creado por la pieza o uno existente al que se nidó). Escribimos la URL canónica en ese
    `contenido` via `repos.actualizar_contenido` (campo `url_fuente`, editable). Deduplicamos
    los `contenido_id` (varias piezas pueden colgar del mismo tema). Best-effort por tema: un
    fallo NUNCA rompe el post-procesado (el copy ya está hecho).
    """
    vistos: set[str] = set()
    for pub in publicaciones:
        cid = str(pub.get("contenido_id") or "").strip()
        if not cid or cid in vistos:
            continue
        vistos.add(cid)
        try:
            repos.actualizar_contenido(cid, {"url_fuente": url_fuente})
        except Exception:  # noqa: BLE001 -- la trazabilidad es un extra; nunca rompe el post-procesado
            continue


# --------------------------------------------------------------------------- #
# Callbacks de post-procesado (corren al completarse la generacion)            #
# --------------------------------------------------------------------------- #


def construir_procesar_copy(
    prompt_id: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
    contenido_id: str = "",
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    veredicto_inicial: str = "",
    url_fuente: str = "",
) -> generaciones.Procesar:
    """Callback de post-procesado de una generacion de PIEZAS (copy/RSS).

    Parsea la salida en piezas/verdicto, registra el historial (con metricas), AUTO-GUARDA
    una publicacion (borrador) por pieza y devuelve `{resultado, historial_id, verdicto,
    piezas, publicaciones[, imagenes]}`. `prompt_id` es solo la etiqueta de origen del historial.

    `contenido_id` (lista viva): si apunta a un tema del tablero existente, cada borrador se
    ADJUNTA a ese `contenido` (cuelga de su tarjeta); sin el (default ""), borrador suelto.
    `veredicto_inicial` (pipeline QPC): veredicto por DEFECTO de las piezas cuando la salida no
    trae uno propio (p. ej. `no_verificado`, para heredar el aviso de la criba de la fuente).
    `url_fuente` (RSS, trazabilidad): URL CANONICA de la nota de origen. Si viene, se PERSISTE en
    `contenido.url_fuente` del tema padre de cada borrador creado (dedup por URL). Best-effort:
    un fallo NUNCA rompe el post-procesado (el copy ya esta hecho). "" = no se toca.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        # Copy UNIFICADO: UN solo copy + copy_in se replica a TODAS las redes pedidas (incluida
        # X, que así nunca nace sin copy_in). El equipo añade los hashtags aparte por grupos.
        parsed = stream.parsear_salida_unificada(salida, redes_ids)
        titulo = titulo_dado or stream.derivar_titulo(texto_base or str(parsed["resultado"]))
        historial_id = repos.registrar_historial_prompt(
            prompt_id, marca, parsed["resultado"], piezas=parsed["piezas"], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        # El veredicto de la salida manda; si viene vacío, cae al inicial (p. ej. no_verificado).
        verdicto = (str(parsed["verdicto"]) or "").strip() or (veredicto_inicial or "")
        publicaciones = crear_publicaciones_desde_piezas(
            parsed["piezas"], marca=marca, titulo=titulo,
            verdicto=verdicto, origen=historial_id, autor=autor,
            contenido_id=contenido_id,
            imagen_fuente=imagen_fuente, tipo_contenido=tipo_contenido,
        )
        # Trazabilidad de la fuente (RSS): persiste la URL canonica en el `contenido` padre de
        # cada borrador creado. Best-effort: el copy YA esta hecho; un fallo aqui no debe romper
        # el post-procesado. Se deduplican los `contenido_id` (varias piezas pueden compartir
        # tema cuando se nida bajo uno existente).
        if url_fuente:
            _persistir_url_fuente(publicaciones, url_fuente)
        resultado: dict[str, object] = {
            "resultado": parsed["resultado"],
            "historial_id": historial_id,
            "verdicto": verdicto,
            "piezas": parsed["piezas"],
            "publicaciones": publicaciones,
        }
        if con_imagenes:
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar


def construir_procesar_galeria(
    prompt_id: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_base: str,
    titulo_dado: str = "",
    autor: dict[str, str] | None = None,
) -> generaciones.Procesar:
    """Callback de post-procesado de una GALERÍA (termómetro): piezas SIN auto-borradores.

    A medio camino entre copy y documento: parsea la salida en piezas por red (igual que
    copy, vía el bloque ```json) y las REGISTRA en el historial, pero NO crea publicaciones
    todavía. El usuario elige al guardar QUÉ redes quiere (`POST .../guardar` con `redes`),
    y ahí se crean los borradores (uno por red). Así un termómetro no inunda el tablero con
    una pieza por cada red de golpe. Devuelve `{documento, resultado, verdicto, historial_id,
    piezas, publicaciones: []}` (`documento` por compat del visor de termómetro).
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        parsed = stream.parsear_salida(salida, redes_ids)
        resultado = str(parsed["resultado"])
        titulo = titulo_dado or stream.derivar_titulo(titulo_base or resultado)
        historial_id = repos.registrar_historial_prompt(
            prompt_id, marca, resultado, piezas=parsed["piezas"], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        return {
            "documento": resultado,
            "resultado": resultado,
            "verdicto": parsed["verdicto"],
            "historial_id": historial_id,
            "piezas": parsed["piezas"],
            "publicaciones": [],
        }

    return procesar


def construir_procesar_documento(
    prompt_id: str,
    marca: str,
    *,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
) -> generaciones.Procesar:
    """Callback de post-procesado de salida `documento` (sin piezas, sin publicaciones).

    Limpia emojis, deriva verdicto/titulo, registra el historial SIN piezas. Devuelve
    `{documento, verdicto, historial_id, piezas: [], publicaciones: []}` (+ `imagenes`).
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        doc = stream.quitar_emojis(salida)
        verdicto = stream.derivar_verdicto(salida)
        titulo = titulo_dado or stream.derivar_titulo(titulo_base or doc)
        historial_id = repos.registrar_historial_prompt(
            prompt_id, marca, doc, piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        resultado: dict[str, object] = {
            "documento": doc,
            "verdicto": verdicto,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }
        if con_imagenes:
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar
