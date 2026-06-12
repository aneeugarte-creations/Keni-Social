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
El render reusa `estudio_imagen.componer_desde_plantilla`, que guarda el PNG con clave por hash del
contenido. Misma receta => mismo objeto => no se duplica y los renders repetidos pegan en caché.
Los renders que ninguna pieza acaba usando son huérfanos reciclables por el GC de media.

CUÁNDO SE DERIVA Y CUÁNDO NO
============================
  - `imagen` (bespoke) presente       -> se respeta tal cual (editor pro / piezas legadas).
  - placa_oculta                      -> publica la FOTO cruda (sin placa).
  - plantilla del estudio (elegida o por defecto de la marca) -> `componer_desde_plantilla`.
  - sin plantilla de estudio resoluble -> foto cruda. (La placa de marca por SPEC, legada, YA NO
    se compone: solo se aplican plantillas de la galería del estudio.)
  - nada de lo anterior               -> "" => el llamante cae a `imagen_fuente`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def marca_tiene_plantilla_estudio(marca: str) -> bool:
    """True si la marca tiene al menos UNA plantilla en la GALERÍA del estudio (PlantillaDiseno).

    Es la ÚNICA fuente de placa: la placa de marca por SPEC (legada, "Sube una foto"/"ÚLTIMA HORA")
    YA NO se aplica —solo se componen plantillas del estudio—. Tolerante: si el almacén no está
    disponible (p. ej. tests unitarios sin Postgres), devuelve False (se trata como "sin plantilla":
    la pieza publica su foto). En producción consulta el almacén real.
    """
    marca = (marca or "").strip()
    if not marca:
        return False
    try:
        from .. import repos

        return bool(repos.listar_plantillas_diseno(marca=marca))
    except Exception:  # noqa: BLE001 -- sin almacén disponible => sin plantilla (degradación segura)
        return False


def tiene_receta(pub: dict[str, Any]) -> bool:
    """True si la imagen publicable se DERIVA de una plantilla del ESTUDIO (placa por capas).

    SOLO componen plantillas de la galería del estudio: la elegida por la pieza
    (`plantilla_diseno_id`) o la POR DEFECTO de la marca si tiene alguna. La placa de marca por SPEC
    (legada, "Sube una foto"/"ÚLTIMA HORA") YA NO se aplica. Sin plantilla de estudio, la pieza
    publica su foto cruda / `imagen_fuente`. Decide si `imagen_url` apunta a `/compuesta`.
    """
    if pub.get("placa_oculta"):
        return False
    if (pub.get("plantilla_diseno_id") or "").strip():
        return True
    return marca_tiene_plantilla_estudio(pub.get("marca") or "")


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
    - Si no, y la marca tiene plantillas EN ROTACIÓN (`rotar=1`, activas) -> la PRIMERA de ellas
      (orden estable de la galería). Las plantillas en rotación MANDAN: una pieza sin plantilla nunca
      se compone con una de fuera de la rotación si la marca tiene alguna marcada. Cubre las piezas
      legadas (creadas antes de marcar la rotación, sin `plantilla_diseno_id`): al mostrarlas, el feed
      adopta la plantilla en rotación, no la primera cualquiera de la galería.
    - Si no hay ninguna en rotación -> la plantilla de estudio POR DEFECTO de la marca, idéntica a la
      del editor: la llamada "Placa de marca" si existe, o la PRIMERA de la galería (orden manual /
      más reciente).

    Así el feed compone EXACTAMENTE la plantilla que enseña el editor (de ahí el arreglo de la
    "plantilla vieja en el feed"). Devuelve None si la pieza no tiene plantilla explícita y la marca
    no tiene NINGUNA plantilla de estudio: ahí el llamante sirve la FOTO cruda (la placa de marca por
    SPEC, legada, ya no se compone).
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
    # Las plantillas EN ROTACIÓN mandan sobre la por defecto: si la marca tiene alguna marcada
    # (`rotar`, activa), el default es la primera de ellas (orden estable de la galería), nunca una
    # de fuera. Sin rotación marcada, cae al comportamiento de siempre (Placa de marca / la primera).
    en_rotacion = [p for p in plantillas if p.get("rotar") and p.get("activo")]
    if en_rotacion:
        return en_rotacion[0]
    for p in plantillas:
        if (p.get("nombre") or "").strip() == "Placa de marca":
            return p
    return plantillas[0]


def plantilla_efectiva_doc(pub: dict[str, Any]) -> dict[str, Any] | None:
    """Documento (parseado) de la plantilla de estudio EFECTIVA de la pieza, o None.

    Es la MISMA plantilla con la que se compone el feed (`_plantilla_efectiva`). La usa el editor
    para arrancar una pieza SIN versión guardada del documento que de verdad se publica (marco real),
    en vez de la plantilla genérica por SPEC de la marca. Tolerante a JSON inválido.
    """
    plantilla = _plantilla_efectiva(pub)
    if not plantilla:
        return None
    try:
        doc = json.loads(plantilla.get("documento") or "{}")
    except (ValueError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


def fotos_de_pieza(pub: dict[str, Any]) -> list[dict[str, Any]]:
    """Fotos por HUECO de la pieza (collage): `[{objeto, foco, zoom}, …]`, una por hueco en orden.

    Fuente: el campo `fotos` (JSON array) si lo hay; si está vacío, deriva el HUECO ÚNICO del par
    legado `foto`/`foto_encuadre` (retrocompat con la foto única). Tolerante a JSON inválido.
    """
    from . import estudio_imagen

    crudo = (pub.get("fotos") or "").strip()
    if crudo:
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            datos = None
        if isinstance(datos, list):
            specs: list[dict[str, Any]] = []
            for it in datos:
                if isinstance(it, dict):
                    specs.append(
                        {
                            "objeto": str(it.get("objeto") or ""),
                            "foco": it.get("foco"),
                            "zoom": it.get("zoom") or 0.0,
                        }
                    )
            if specs:
                return specs
    foco, zoom = estudio_imagen.parsear_encuadre(pub.get("foto_encuadre") or "")
    return [{"objeto": (pub.get("foto") or "").strip(), "foco": foco, "zoom": zoom}]


def imagen_compuesta_id(pub: dict[str, Any]) -> str:
    """Media id de la imagen PUBLICABLE de la pieza, renderizando on-demand si hace falta.

    Resuelve la receta en este orden:
      1. RECETA viva (plantilla de estudio) en pieza NO publicada: deriva de la receta ACTUAL aunque
         quede un `imagen` viejo horneado (así el feed == editor sin re-guardar).
      2. `imagen` bespoke ya horneada (editor pro / legacy / publicada): se respeta sin recomponer.
      3. sin plantilla de estudio (placa oculta / marca sin plantilla): devuelve la `foto` cruda.
      4. plantilla del estudio: `componer_desde_plantilla(doc, copy_in, fotos)`.

    Ya NO se usa la placa de marca por SPEC (legada): solo componen plantillas de la galería.
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
        resultado = estudio_imagen.componer_desde_plantilla(
            plantilla.get("documento") or "{}",
            copy_in=copy_in,
            fotos=fotos_de_pieza(pub),  # una foto por hueco (collage); legado = hueco único
        )
        return resultado["id"]
    # Sin plantilla de estudio resoluble: la foto cruda (NO la placa de marca por SPEC, retirada).
    return foto


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
        datos = estudio_imagen.componer_desde_plantilla_bytes(
            plantilla.get("documento") or "{}",
            copy_in=copy_in,
            fotos=fotos_de_pieza(pub),  # una foto por hueco (collage); legado = hueco único
        )
        return datos, "image/png"
    # Sin plantilla de estudio resoluble: la foto cruda (NO la placa por SPEC, retirada).
    if not foto:
        return None
    datos = media.leer_media(foto)
    return (datos, media.mime_de(foto)) if datos is not None else None


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
        "fotos": pub.get("fotos") or "",
        "placa_oculta": bool(pub.get("placa_oculta")),
        "plantilla_diseno_id": (pub.get("plantilla_diseno_id") or "").strip(),
        "imagen": (pub.get("imagen") or "").strip(),
        "actualizado": pub.get("fecha_actualizacion") or "",
    }
    try:
        if not pub.get("placa_oculta"):
            # La plantilla EFECTIVA (explícita o la por defecto de la marca): su documento entra en
            # la firma para que editar la plantilla invalide la caché HTTP. (La placa por SPEC ya no
            # se usa, así que no entra en la firma.)
            plantilla = _plantilla_efectiva(pub)
            if plantilla is not None:
                base["doc"] = plantilla.get("documento") or ""
                base["doc_id"] = plantilla.get("id") or ""
    except Exception:  # noqa: BLE001 -- el respaldo (actualizado) basta si falla el doc
        pass
    crudo = json.dumps(base, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]
