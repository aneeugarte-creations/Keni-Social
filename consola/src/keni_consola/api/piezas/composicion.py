"""Composicion de IMAGEN de una pieza: integrar foto, aplicar plantilla y servir compuesta.

Recompone la foto detrás de la placa/plantilla de marca (síncrono, determinista) y sirve la
imagen compuesta on-demand y efímera. Extraido TAL CUAL del modulo `piezas.py`
original (refactor de pura reubicacion, sin cambio de comportamiento).
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ..._http_json import leer_json
from ...seguridad import autor_de_peticion
from ._comun import _publicacion_a_dict


async def integrar_foto(request: Request) -> Response:
    """Integra una FOTO subida dentro de la plantilla de marca de la publicación.

    `POST /api/piezas/{id}/integrar-foto {imagen}` (imagen = id de media de la foto).
    Si la pieza tiene marca (cualquiera del catálogo) RECOMPONE de forma determinista
    (síncrona, ~<1s) la foto detrás de la plantilla por SPEC usando el `copy_in` de la pieza
    como titular; sin marca devuelve la foto tal cual. NO persiste: devuelve la imagen
    resultante para que el SPA la fije y la guarde con el resto de la edición.
    -> `{imagen, imagen_url}` | 400 | 404.
    """
    from ...dominio import estudio_imagen

    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return JSONResponse({"error": "Falta la foto a integrar."}, status_code=400)
    imagen = imagen.strip()
    # `copy_in` opcional: el SPA puede mandar el texto-en-imagen VIGENTE (aún sin guardar) para
    # que la placa use ese titular; si no viene, se usa el `copy_in` persistido de la pieza.
    copy_in = datos.get("copy_in")
    titular = copy_in if isinstance(copy_in, str) else (pub.get("copy_in") or "")

    marca = pub.get("marca") or ""
    final = imagen
    if estudio_imagen.marca_tiene_plantilla(marca):
        try:
            resultado = estudio_imagen.componer(
                imagen,
                marca=marca,
                formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
                titular=titular,
                etiqueta=None,
                autor=autor_de_peticion(request),
            )
            final = resultado.get("id") or imagen
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    return JSONResponse({"imagen": final, "imagen_url": f"/api/media/{final}"})


async def aplicar_plantilla(request: Request) -> Response:
    """Aplica una PLANTILLA del estudio a la publicación y RECOMPONE su imagen.

    `POST /api/piezas/{id}/aplicar-plantilla {plantilla_id}`: renderiza el documento de la
    plantilla (PlantillaDiseno) con la FOTO y el COPY-IN actuales de la pieza, fija la imagen
    resultante y recuerda la plantilla elegida (`plantilla_diseno_id`). Persiste. Así el equipo
    prueba distintas plantillas y compara el resultado real. -> `{pieza}` | 400 | 404.
    """
    from ...dominio import estudio_imagen

    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    plantilla_id = datos.get("plantilla_id")
    if not isinstance(plantilla_id, str) or not plantilla_id.strip():
        return JSONResponse({"error": "Falta la plantilla a aplicar."}, status_code=400)
    plantilla_id = plantilla_id.strip()
    plantilla = repos.obtener_plantilla_diseno(plantilla_id)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)

    # `foto`/`copy_in`/`foto_encuadre` opcionales: el SPA manda los valores VIGENTES del editor
    # (aún sin guardar) para componer con ellos; si no vienen, se usan los persistidos de la pieza.
    foto_req = datos.get("foto")
    foto = foto_req if isinstance(foto_req, str) else (pub.get("foto") or "")
    copy_in_req = datos.get("copy_in")
    copy_in = copy_in_req if isinstance(copy_in_req, str) else (pub.get("copy_in") or "")
    enc_req = datos.get("foto_encuadre")
    foto_encuadre = enc_req if isinstance(enc_req, str) else (pub.get("foto_encuadre") or "")
    foco, zoom = estudio_imagen.parsear_encuadre(foto_encuadre)

    # Render de VALIDACIÓN (síncrono) a BYTES: confirma que la plantilla compone con esta
    # foto/copy_in antes de fijarla, SIN persistir nada (no genera registros sueltos). La imagen se
    # renderiza on-demand y efímera desde la receta (`/compuesta`); no se hornea en `imagen`.
    try:
        estudio_imagen.componer_desde_plantilla_bytes(
            plantilla.get("documento") or "{}",
            copy_in=copy_in,
            foto=foto,
            foco=foco,
            zoom=zoom,
        )
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    actualizada = repos.actualizar_pieza(
        pieza_id,
        {
            # `imagen` vacío: la composición se deriva de la receta y se sirve por `/compuesta`.
            "imagen": "",
            "plantilla_diseno_id": plantilla_id,
            "foto": foto,
            "foto_encuadre": foto_encuadre,
        },
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"pieza": _publicacion_a_dict(actualizada)})


async def componer_slide(request: Request) -> Response:
    """HORNEA la placa de UN slide del carrusel y devuelve su media id (igual que el generador).

    `POST /api/piezas/{id}/componer-slide {foto?, titular?, plantilla_id?, foto_encuadre?}`:
    compone la plantilla (la `plantilla_id` indicada, o la EFECTIVA de la marca) con la foto +
    titular + reencuadre y guarda el PNG en la carpeta protegida `artes/` (los slides viven en el
    campo `carrusel`, fuera del catálogo regenerable; el GC no la borra). Devuelve `{id, url}` para
    que el SPA fije ese media como `objeto` del slide y guarde su PROCEDENCIA (foto+titular+
    plantilla+encuadre) en el carrusel, de modo que el slide se pueda re-editar como placa.

    A diferencia de `aplicar-plantilla` (que toca los campos de la PORTADA), esto NO persiste nada
    en la pieza: solo produce el media del slide; el SPA lo guarda dentro del JSON `carrusel`.
    Marca sin plantilla: cae a la foto cruda promovida a `artes/`. Sin foto NI plantilla -> 400.
    -> `{id, url}` | 400 | 404 | 422.
    """
    from ... import almacen_media, media
    from ...dominio import estudio_imagen, render_pieza

    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    foto = datos.get("foto")
    foto = foto.strip() if isinstance(foto, str) else ""
    titular_req = datos.get("titular")
    titular = titular_req.strip() if isinstance(titular_req, str) else ""
    if not foto and not titular:
        return JSONResponse({"error": "El slide necesita una foto o un titular."}, status_code=400)

    # Plantilla: la indicada explícitamente, o la EFECTIVA de la marca (la misma de la portada).
    # `sin_plantilla` (como el "quitar plantilla" de la portada): el slide es la foto cruda.
    sin_plantilla = bool(datos.get("sin_plantilla"))
    plantilla_id = datos.get("plantilla_id")
    plantilla_id = plantilla_id.strip() if isinstance(plantilla_id, str) else ""
    plantilla: dict | None = None
    if not sin_plantilla:
        if plantilla_id:
            plantilla = repos.obtener_plantilla_diseno(plantilla_id)
            if plantilla is None:
                return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
        else:
            try:
                plantilla = render_pieza._plantilla_efectiva({"marca": pub.get("marca") or ""})
            except Exception:  # noqa: BLE001 -- sin plantilla legible: tratamos como marca sin placa
                plantilla = None

    enc_req = datos.get("foto_encuadre")
    foto_encuadre = enc_req if isinstance(enc_req, str) else ""
    foco, zoom = estudio_imagen.parsear_encuadre(foto_encuadre)

    if plantilla is not None:
        try:
            bytes_png = await run_in_threadpool(
                estudio_imagen.componer_desde_plantilla_bytes,
                plantilla.get("documento") or "{}",
                copy_in=titular,
                foto=foto,
                foco=foco,
                zoom=zoom,
            )
            media_id = await run_in_threadpool(
                media.guardar_bytes_contenido, bytes_png, ext="png", categoria="artes"
            )
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=422)
    elif foto:
        # Marca sin plantilla de estudio: el slide es la foto cruda, protegida en `artes/`.
        media_id = await run_in_threadpool(almacen_media.promover_objeto, foto, "artes")
    else:
        return JSONResponse(
            {"error": "La marca no tiene plantilla y el slide no trae foto."}, status_code=400
        )

    return JSONResponse({"id": media_id, "url": f"/api/media/{media_id}"})


async def compuesta(request: Request) -> Response:
    """Sirve la imagen COMPUESTA de la pieza, renderizada ON-DEMAND y EFÍMERA (sin persistir).

    `GET /api/piezas/{id}/compuesta`: deriva la imagen publicable (placa de marca o
    plantilla del estudio aplicada a la foto + copy_in + encuadre) y devuelve los bytes SIN
    escribir nada en el almacén — el composite es función pura de la receta, no un objeto que
    almacenar. La caché vive en la capa HTTP: `ETag = hash(receta)` + `Cache-Control`; si el
    cliente reenvía `If-None-Match` y la receta no cambió, respondemos 304 SIN recomponer (el
    ETag se calcula de la receta, barato; no corre Node). Así no se generan registros sueltos.

    404 si la pieza no existe o no tiene imagen servible; 422 si el render falla (motivo en
    español).
    """
    from ...dominio import estudio_imagen, render_pieza

    pieza_id = request.path_params["pieza_id"]
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    etag = f'"{render_pieza.firma_receta(pub)}"'
    cache = "private, max-age=300"
    # 304 sin renderizar si el cliente ya tiene esta versión de la receta.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})

    try:
        # Render es bloqueante (subprocess.run); ejecutar en threadpool para no bloquear el event loop.
        resultado = await run_in_threadpool(render_pieza.render_bytes, pub)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    if resultado is None:
        return JSONResponse({"error": "La pieza aún no tiene imagen."}, status_code=404)
    datos, mime = resultado
    return Response(
        datos,
        media_type=mime,
        headers={"ETag": etag, "Cache-Control": cache},
    )


async def generar_carrusel(request: Request) -> Response:
    """ENCOLA la generación de un CARRUSEL a partir del copy YA redactado de un post. -> `{generacion}`.

    `POST /api/piezas/{id}/generar-carrusel`: lanza un `claude -p` READ-ONLY que parte el copy de la
    pieza en titulares de slides; el post-procesado los hornea como placas de la marca y los escribe
    en todas las piezas gemelas del contenido (la portada se conserva). El feed YA flip-eó el formato
    a carrusel antes de llamar. El SPA sondea `GET /api/generaciones/{id}` hasta el estado terminal y
    recarga la pieza (los slides aparecen en el editor). `ColaLlenaError` se PROPAGA (el manejador
    central de `app.py` la traduce a 429). -> `{generacion}` | 400 | 404.
    """
    from ...dominio import carrusel

    pieza_id = request.path_params["pieza_id"]
    try:
        gen = carrusel.lanzar_para_pieza(pieza_id)
    except carrusel.CarruselError as e:
        estado = 404 if "ya no existe" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=estado)
    return JSONResponse({"generacion": gen})
