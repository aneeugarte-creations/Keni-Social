"""Render ON-DEMAND de la imagen compuesta de una pieza, derivada de su RECETA.

PROBLEMA QUE RESUELVE
=====================
Hasta ahora cada pieza horneaba y PERSISTÍA un PNG con el logo + pleca + titular (+ foto)
incrustados en píxeles. Editar el copy_in generaba otro PNG: N variantes de texto sobre la
misma marca = N imágenes casi idénticas en el almacén, duplicando logo/pleca una y otra vez.

LA RECETA YA VIVE EN LA PIEZA
=============================
Una publicación ya guarda todo lo necesario para componer su imagen: `marca`/`red`, `foto`
(la foto cruda), `copy_in` (el titular), `foto_encuadre` (recorte 4:5), `plantilla_diseno_id`
(plantilla del estudio) y `placa_oculta`. Así que la imagen publicable se DERIVA de esa receta
y se renderiza bajo demanda, en vez de persistir un composite por cada edición.

CONTENT-ADDRESSED = CACHÉ NATURAL
=================================
El render reusa `estudio_imagen.componer` / `componer_desde_plantilla`, que guardan el PNG con
clave por hash del contenido (`media.importar_imagen`). Misma receta => mismo objeto => no se
duplica y los renders repetidos pegan en caché. Los renders que ninguna pieza acaba usando son
huérfanos reciclables por el GC de media.

CUÁNDO SE DERIVA Y CUÁNDO NO
============================
  - `imagen` (bespoke) presente   -> se respeta tal cual (editor pro / piezas legadas).
  - placa_oculta                  -> publica la FOTO cruda (sin placa de marca).
  - plantilla del estudio elegida -> `componer_desde_plantilla`.
  - marca con plantilla            -> placa de marca (`componer`).
  - sin nada de lo anterior        -> foto cruda (o "" => el llamante cae a `imagen_fuente`).
"""

from __future__ import annotations

from typing import Any


def tiene_receta(pub: dict[str, Any]) -> bool:
    """True si la imagen publicable se DERIVA de una receta de composición (placa/plantilla).

    Hay composición de marca por delante cuando NO está la placa oculta y, o bien hay una
    plantilla del estudio elegida, o la marca tiene una plantilla configurada. Las piezas sin
    receta (placa oculta, marca sin plantilla, solo-foto) publican la foto cruda; las de fuente,
    su `imagen_fuente`. Se usa en la serialización para decidir si `imagen_url` apunta al render
    on-demand (`/compuesta`) en vez de a un objeto de media horneado.
    """
    if pub.get("placa_oculta"):
        return False
    if (pub.get("plantilla_diseno_id") or "").strip():
        return True
    from . import estudio_imagen

    return estudio_imagen.marca_tiene_plantilla(pub.get("marca") or "")


def imagen_compuesta_id(pub: dict[str, Any]) -> str:
    """Media id de la imagen PUBLICABLE de la pieza, renderizando on-demand si hace falta.

    Resuelve la receta en este orden:
      1. `imagen` bespoke ya horneada (editor pro / legacy): se respeta sin recomponer.
      2. sin receta (placa oculta / marca sin plantilla): devuelve la `foto` cruda (o "").
      3. plantilla del estudio: `componer_desde_plantilla(doc, copy_in, foto, encuadre)`.
      4. placa de marca: `componer(foto, marca, formato_por_red(red), titular=copy_in)`.

    El render es content-addressed: idéntica receta => idéntico id (cacheado, sin duplicar).
    Devuelve "" si no hay imagen derivable (el llamante decide el fallback a `imagen_fuente`).
    Lanza `estudio_imagen.EstudioError` si el render falla (el endpoint -> 4xx; el publicador
    lo captura y publica sin media).
    """
    imagen = (pub.get("imagen") or "").strip()
    if imagen:
        return imagen
    if not tiene_receta(pub):
        return (pub.get("foto") or "").strip()

    from . import estudio_imagen

    foto = (pub.get("foto") or "").strip()
    copy_in = pub.get("copy_in") or ""
    plantilla_id = (pub.get("plantilla_diseno_id") or "").strip()

    if plantilla_id:
        from .. import repos

        plantilla = repos.obtener_plantilla_diseno(plantilla_id)
        if plantilla is not None:
            foco, zoom = estudio_imagen.parsear_encuadre(pub.get("foto_encuadre") or "")
            resultado = estudio_imagen.componer_desde_plantilla(
                plantilla.get("documento") or "{}",
                copy_in=copy_in,
                foto=foto,
                foco=foco,
                zoom=zoom,
            )
            return resultado["id"]
        # Plantilla borrada: caemos a la placa de marca (no dejamos la pieza sin imagen).

    resultado = estudio_imagen.componer(
        foto,
        marca=pub.get("marca") or "",
        formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
        titular=copy_in,
        etiqueta=None,
    )
    return resultado["id"]


def imagen_url_de(pub: dict[str, Any]) -> str:
    """URL servible de la imagen de la pieza para la UI/MCP (sin renderizar nada aquí).

    Precedencia (barata, sin componer):
      - `imagen` horneada (bespoke/legacy) -> `/api/media/{imagen}`.
      - receta derivable                   -> `/api/publicaciones/{id}/compuesta` (on-demand).
      - foto cruda                          -> `/api/media/{foto}`.
      - imagen de fuente (URL externa)      -> esa URL.
      - nada                                -> "".

    NO ejecuta el render (no llama a Node): solo decide la URL. El render ocurre cuando el
    navegador/Metricool pide `/compuesta`. Así la serialización de listas sigue siendo barata.
    """
    imagen = (pub.get("imagen") or "").strip()
    if imagen:
        return f"/api/media/{imagen}"
    if tiene_receta(pub):
        return f"/api/publicaciones/{pub['id']}/compuesta"
    foto = (pub.get("foto") or "").strip()
    if foto:
        return f"/api/media/{foto}"
    return pub.get("imagen_fuente") or ""
