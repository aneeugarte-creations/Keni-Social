"""Post-procesado de generaciones de COPY/DOCUMENTO (parseo + artefactos), NEUTRO.

Estas fábricas convierten la salida cruda de `claude -p` en los ARTEFACTOS de la Consola
(piezas por red, publicaciones-borrador, historial, imágenes previsualizadas). Son DOMINIO
PURO: dependen de `stream` (parseo), `repos` (historial), `dominio.publicaciones` (handoff
A→C de borradores), `redes` y `media`. NO dependen del catálogo de skills.

Viven aquí (y ya no en `dominio.skills`) porque son el post-procesado de CUALQUIER
generación de copy, venga de la Biblioteca de prompts o de donde sea: al retirar el sistema
de skills, este módulo es su hogar estable. `jobspec.reconstruir_procesar` los reconstruye
en el worker desde el `spec`.
"""

from __future__ import annotations

import re

from .. import generaciones, redes, repos
from . import publicaciones as contrato_publicaciones
from . import stream

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
) -> list[dict[str, object]]:
    """Crea UNA publicacion (borrador) por pieza y devuelve sus dicts serializados.

    HANDOFF A->C (ADR 0005 §Seams #1): cada pieza se deposita como BORRADOR por la
    funcion-contrato `dominio.publicaciones.crear_borrador` (nace `borrador`). Si
    `redes_filtro` no es None, solo se crean las piezas cuya red este en el filtro.
    """
    creadas: list[dict[str, object]] = []
    for pieza in piezas:
        red = pieza.get("red")
        contenido = pieza.get("contenido")
        if not isinstance(red, str) or not redes.es_red(red):
            continue
        if redes_filtro is not None and red not in redes_filtro:
            continue
        if not isinstance(contenido, str):
            contenido = ""
        creadas.append(
            contrato_publicaciones.crear_borrador(
                marca, red, titulo=titulo, contenido=contenido, veredicto=verdicto,
                origen=origen, autor=autor,
            )
        )
    return creadas


# --------------------------------------------------------------------------- #
# Callbacks de post-procesado (corren al completarse la generacion)            #
# --------------------------------------------------------------------------- #


def construir_procesar_copy(
    skill: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
) -> generaciones.Procesar:
    """Callback de post-procesado de una generacion de PIEZAS (copy/RSS).

    Parsea la salida en piezas/verdicto, registra el historial (con metricas), AUTO-GUARDA
    una publicacion (borrador) por pieza y devuelve `{resultado, historial_id, verdicto,
    piezas, publicaciones[, imagenes]}`. `skill` es solo la etiqueta de origen del historial.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        parsed = stream.parsear_salida(salida, redes_ids)
        titulo = titulo_dado or stream.derivar_titulo(texto_base or str(parsed["resultado"]))
        historial_id = repos.registrar_historial_skill(
            skill, marca, parsed["resultado"], piezas=parsed["piezas"], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        publicaciones = crear_publicaciones_desde_piezas(
            parsed["piezas"], marca=marca, titulo=titulo,
            verdicto=parsed["verdicto"], origen=historial_id, autor=autor,
        )
        resultado: dict[str, object] = {
            "resultado": parsed["resultado"],
            "historial_id": historial_id,
            "verdicto": parsed["verdicto"],
            "piezas": parsed["piezas"],
            "publicaciones": publicaciones,
        }
        if con_imagenes:
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar


def construir_procesar_documento(
    skill: str,
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
        historial_id = repos.registrar_historial_skill(
            skill, marca, doc, piezas=[], titulo=titulo,
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
