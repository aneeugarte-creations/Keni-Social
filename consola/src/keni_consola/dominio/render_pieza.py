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

import hashlib
import json
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


def _receta_manda(pub: dict[str, Any]) -> bool:
    """La RECETA prevalece sobre un `imagen` horneado obsoleto. Solo cuando todo esto se cumple:

      - la pieza NO está PUBLICADA (las publicadas congelan su `imagen` como registro exacto), y
      - tiene receta viva (placa de marca / plantilla del estudio), y
      - hay ALGO de lo que recomponer: una plantilla del estudio elegida (`plantilla_diseno_id`,
        que puede no llevar foto), o una `foto` cruda (la placa de marca se compone sobre ella).

    Sin esto, el editor mostraba la plantilla correcta (render en vivo) pero el feed seguía
    sirviendo la placa VIEJA horneada en `imagen` (de un publish anterior o de antes de
    render-on-demand). Y al revés: si solo hay `imagen` (ni plantilla ni foto), ese `imagen` es un
    asset SUBIDO/IMPORTADO bespoke —no una placa derivada— y se RESPETA tal cual.
    """
    if (pub.get("estado") or "") == "publicado":
        return False
    if not tiene_receta(pub):
        return False
    if (pub.get("plantilla_diseno_id") or "").strip():
        return True
    return bool((pub.get("foto") or "").strip())


def _plantilla_efectiva(pub: dict[str, Any]) -> dict[str, Any] | None:
    """Plantilla de ESTUDIO con la que se compone la pieza (la MISMA que muestra el editor).

    - Si la pieza fija una `plantilla_diseno_id` explícita -> esa.
    - Si no -> la plantilla de estudio POR DEFECTO de la marca, idéntica a la del editor
      (`plantilla_diseno_id || idPlacaDeMarca`): la llamada "Placa de marca" si existe, o la
      PRIMERA (más reciente, `creado DESC`, igual que la lista que ve el editor).

    Así el feed compone EXACTAMENTE la plantilla que enseña el editor, en vez de caer a la placa
    de marca por SPEC (legada), que era un diseño distinto (de ahí "plantilla vieja en el feed").
    Devuelve None si la pieza no tiene plantilla explícita y la marca no tiene NINGUNA plantilla de
    estudio: ahí el llamante cae a `componer` (placa de marca por SPEC).
    """
    from .. import repos

    pid = (pub.get("plantilla_diseno_id") or "").strip()
    if pid:
        return repos.obtener_plantilla_diseno(pid)
    marca = (pub.get("marca") or "").strip()
    if not marca:
        return None
    plantillas = repos.listar_plantillas_diseno(marca=marca)
    if not plantillas:
        return None
    for p in plantillas:
        if (p.get("nombre") or "").strip() == "Placa de marca":
            return p
    return plantillas[0]


def imagen_compuesta_id(pub: dict[str, Any]) -> str:
    """Media id de la imagen PUBLICABLE de la pieza, renderizando on-demand si hace falta.

    Resuelve la receta en este orden:
      1. RECETA viva (placa/plantilla) en pieza NO publicada: deriva de la receta ACTUAL aunque
         quede un `imagen` viejo horneado (así el feed == editor sin re-guardar).
      2. `imagen` bespoke ya horneada (editor pro / legacy / publicada): se respeta sin recomponer.
      3. sin receta (placa oculta / marca sin plantilla): devuelve la `foto` cruda (o "").
      4. plantilla del estudio: `componer_desde_plantilla(doc, copy_in, foto, encuadre)`.
      5. placa de marca: `componer(foto, marca, formato_por_red(red), titular=copy_in)`.

    El render es content-addressed: idéntica receta => idéntico id (cacheado, sin duplicar).
    Devuelve "" si no hay imagen derivable (el llamante decide el fallback a `imagen_fuente`).
    Lanza `estudio_imagen.EstudioError` si el render falla (el endpoint -> 4xx; el publicador
    lo captura y publica sin media).
    """
    imagen = (pub.get("imagen") or "").strip()
    if imagen and not _receta_manda(pub):
        return imagen
    if not tiene_receta(pub):
        return (pub.get("foto") or "").strip()

    from . import estudio_imagen

    foto = (pub.get("foto") or "").strip()
    copy_in = pub.get("copy_in") or ""

    # Plantilla de estudio EFECTIVA (explícita o la por defecto de la marca, como el editor).
    plantilla = _plantilla_efectiva(pub)
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
    # Marca sin plantillas de estudio: placa de marca por SPEC (legado).
    resultado = estudio_imagen.componer(
        foto,
        marca=pub.get("marca") or "",
        formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
        titular=copy_in,
        etiqueta=None,
    )
    return resultado["id"]


def _sufijo_cache(pub: dict[str, Any]) -> str:
    """Sufijo `?v=...` para la URL del render on-demand (`/compuesta`).

    El `/compuesta` se sirve con `Cache-Control: max-age=300`, así que el navegador reusaría la
    imagen cacheada hasta 5 min tras EDITAR la pieza (p. ej. subir/cambiar la foto) y el feed no se
    actualizaría. El token deriva de `actualizado` (lo bumpea TODA edición): al editar cambia la
    URL -> cache miss -> imagen fresca. Las piezas sin tocar conservan su URL (y su caché). Las
    rutas `/api/media/{id}` no lo necesitan (son content-addressed: el id ya cambia con el contenido).
    """
    sello = str(pub.get("actualizado") or pub.get("fecha_actualizacion") or "").strip()
    if not sello:
        return ""
    return f"?v={hashlib.sha256(sello.encode('utf-8')).hexdigest()[:8]}"


def imagen_url_de(pub: dict[str, Any]) -> str:
    """URL servible de la imagen de la pieza para la UI/MCP (sin renderizar nada aquí).

    Precedencia (barata, sin componer):
      - receta viva en pieza NO publicada   -> `/api/publicaciones/{id}/compuesta` (gana al PNG viejo).
      - `imagen` horneada (bespoke/legacy/publicada) -> `/api/media/{imagen}`.
      - receta derivable                   -> `/api/publicaciones/{id}/compuesta` (on-demand).
      - foto cruda                          -> `/api/media/{foto}`.
      - imagen de fuente (URL externa)      -> esa URL.
      - nada                                -> "".

    NO ejecuta el render (no llama a Node): solo decide la URL. El render ocurre cuando el
    navegador/Metricool pide `/compuesta`. Así la serialización de listas sigue siendo barata.
    """
    imagen = (pub.get("imagen") or "").strip()
    if imagen and not _receta_manda(pub):
        return f"/api/media/{imagen}"
    if tiene_receta(pub):
        return f"/api/publicaciones/{pub['id']}/compuesta{_sufijo_cache(pub)}"
    foto = (pub.get("foto") or "").strip()
    if foto:
        return f"/api/media/{foto}"
    return pub.get("imagen_fuente") or ""


def render_bytes(pub: dict[str, Any]) -> tuple[bytes, str] | None:
    """Bytes de la imagen publicable + su mime, renderizando ON-DEMAND y SIN persistir.

    Es el camino EFÍMERO del endpoint `/compuesta`: el composite (placa/plantilla) se renderiza
    en memoria y NO se escribe en el almacén — no genera huérfanos. Para `imagen` ya horneada
    (bespoke / publicada) o la `foto` cruda, se sirven sus bytes tal cual (assets reales, sin
    crear nada nuevo). Devuelve `None` si la pieza no tiene imagen servible. Lanza
    `estudio_imagen.EstudioError` si el render falla.
    """
    from .. import media

    imagen = (pub.get("imagen") or "").strip()
    if imagen and not _receta_manda(pub):
        datos = media.leer_media(imagen)
        return (datos, media.mime_de(imagen)) if datos is not None else None
    if not tiene_receta(pub):
        foto = (pub.get("foto") or "").strip()
        if not foto:
            return None
        datos = media.leer_media(foto)
        return (datos, media.mime_de(foto)) if datos is not None else None

    from . import estudio_imagen

    foto = (pub.get("foto") or "").strip()
    copy_in = pub.get("copy_in") or ""

    # Plantilla de estudio EFECTIVA (explícita o la por defecto de la marca, como el editor).
    plantilla = _plantilla_efectiva(pub)
    if plantilla is not None:
        foco, zoom = estudio_imagen.parsear_encuadre(pub.get("foto_encuadre") or "")
        datos = estudio_imagen.componer_desde_plantilla_bytes(
            plantilla.get("documento") or "{}",
            copy_in=copy_in, foto=foto, foco=foco, zoom=zoom,
        )
        return datos, "image/png"
    # Marca sin plantillas de estudio: placa de marca por SPEC (legado).
    datos = estudio_imagen.componer_bytes(
        foto,
        marca=pub.get("marca") or "",
        formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
        titular=copy_in,
        etiqueta=None,
    )
    return datos, "image/png"


def firma_receta(pub: dict[str, Any]) -> str:
    """Hash ESTABLE de la receta -> ETag del render on-demand (cambia sii cambia la salida).

    Cubre todo lo que altera los bytes compuestos: campos de la pieza (marca/red/foto/copy_in/
    encuadre/placa_oculta/plantilla/imagen) MÁS el contenido del que depende el layout —el
    DOCUMENTO de la plantilla si hay una, o el SPEC de la marca si es placa— para que una edición
    de la plantilla/spec invalide la caché HTTP. Incluye `fecha_actualizacion` como respaldo si
    no se pudiera leer el spec/doc. Es BARATO (no corre Node): permite responder 304 sin componer.
    """
    base: dict[str, Any] = {
        "marca": pub.get("marca") or "",
        "red": pub.get("red") or "",
        "foto": pub.get("foto") or "",
        "copy_in": pub.get("copy_in") or "",
        "foto_encuadre": pub.get("foto_encuadre") or "",
        "placa_oculta": bool(pub.get("placa_oculta")),
        "plantilla_diseno_id": (pub.get("plantilla_diseno_id") or "").strip(),
        "imagen": (pub.get("imagen") or "").strip(),
        "actualizado": pub.get("fecha_actualizacion") or "",
    }
    try:
        if not pub.get("placa_oculta"):
            # La plantilla EFECTIVA (explícita o la por defecto de la marca): su documento entra en
            # la firma para que editar la plantilla invalide la caché HTTP. Si la marca no tiene
            # plantillas de estudio, cae al SPEC (placa de marca legada).
            plantilla = _plantilla_efectiva(pub)
            if plantilla is not None:
                base["doc"] = plantilla.get("documento") or ""
                base["doc_id"] = plantilla.get("id") or ""
            elif pub.get("marca") or "":
                from .. import plantillas_marca

                base["spec"] = plantillas_marca.obtener_spec(pub["marca"])
    except Exception:  # noqa: BLE001 -- el respaldo (actualizado) basta si falla el spec/doc
        pass
    crudo = json.dumps(base, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]
