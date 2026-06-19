"""API Media: subir imagenes, servirlas y generarlas con IA (si hay proveedor).

El SPA adjunta imagenes a las piezas. Esta API:
  - `POST /api/media`        guarda una imagen subida (multipart `archivo`).
  - `GET  /api/media/{n}`    sirve una imagen del dir de media (anti-traversal).
  - `POST /api/media/generar` genera una imagen con IA si HAY proveedor configurado;
    si no, responde 400 con un mensaje claro (la clave del proveedor no se commitea).

SEGURIDAD: el nombre en disco lo genera el servidor (uuid); el GET valida que el
nombre pedido no escape del dir (anti-traversal). Errores en espanol, sin tracebacks.
El proveedor de imagen y su clave viven en `consola.media` y son mockeables: los
tests NUNCA tocan la red.

RIESGO RESIDUAL — ALCANCE POR MARCA (cierre ADR 0003, DIFERIDO aqui): el media tiene un
espacio de nombres PLANO (uuid) SIN etiqueta de marca. `GET /api/media/{n}` sirve cualquier
imagen a cualquier sesion autenticada: no se puede acotar por tenant sin asociar marca a cada
asset (columna/tabla -> cambio de db.py, reservado a otro agente). Es coste/abuso de baja
gravedad (no expone estado editorial, solo el binario para quien adivine el uuid). Se deja al
dueño cuando exista el tag de marca; no se sobre-restringe aqui para no romper accesos legitimos.
"""

from __future__ import annotations

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_ilustrar, generaciones, media, repos
from .._http_json import leer_json
from ..dominio import extraccion_url
from ..seguridad import autor_de_peticion

# Carpetas en las que el CLIENTE puede pedir guardar una subida (allowlist publica). Las demas
# categorias (logos/texto/render/generadas/documentos) las asigna el server por su flujo;
# el cliente solo distingue una foto de pieza (`fotos`) de un asset del editor de plantillas.
_CATEGORIAS_SUBIDA = {"fotos", "plantillas"}


async def subir(request: Request) -> Response:
    """Guarda una imagen subida (multipart `archivo`; opcional `categoria`) -> `{id, url}`."""
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer la imagen subida."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ninguna imagen."}, status_code=400)
    categoria = form.get("categoria")
    categoria = categoria if categoria in _CATEGORIAS_SUBIDA else "fotos"
    try:
        nombre = await media.guardar_subida(archivo, categoria=categoria)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


async def subir_video(request: Request) -> Response:
    """Guarda un VIDEO subido (multipart `archivo`) -> `{id, url}` (espejo de `POST /api/media`).

    Para piezas de formato video. El asset va a la carpeta `videos/` (content-addressed) y se
    sirve por el mismo `GET /api/media/{n}`. Mismos errores en espanol que la subida de imagen.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer el video subido."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ningún video."}, status_code=400)
    try:
        nombre = await media.guardar_video_subida(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar el video."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


# El media es CONTENT-ADDRESSED (el nombre = hash del contenido; nunca se reescribe bajo el mismo
# nombre): un objeto es INMUTABLE. Por eso se sirve con caché agresiva y `immutable`, así el
# navegador no lo revalida ni re-descarga (la galería con N miniaturas/fotos abre instantánea en
# revisitas). 1 año = el tope práctico de `max-age`.
_CACHE_MEDIA = "public, max-age=31536000, immutable"


async def servir(request: Request) -> Response:
    """Sirve una imagen del almacen de media por nombre (404 si falta; anti-traversal).

    SIN `?w`: camino backend-NEUTRAL clasico — `media.leer_media` lee del disco (con
    anti-traversal) o del bucket S3 segun el backend activo, y devolvemos los bytes con el mime
    de la extension. Retrocompatible (descargas / vista a tamano completo piden el original).

    CON `?w=<px>`: sirve una derivada WebP redimensionada a ese ancho (resize ON-THE-FLY con
    cache en `deriv/`; allowlist de anchos, sin upscale). Si el original no es redimensionable
    (video, GIF animado, formato raro) se cae al original intacto; si `w` no es un entero
    positivo, 400. Cacheable inmutable en ambos casos: el contenido por (nombre, ancho) no cambia.
    """
    nombre = request.path_params["nombre"]
    ancho = request.query_params.get("w")
    if ancho is not None:
        try:
            deriv = media.derivada(nombre, ancho)
        except ValueError:
            return JSONResponse({"error": "Ancho de imagen inválido."}, status_code=400)
        if deriv is not None:
            datos, mime = deriv
            return Response(datos, media_type=mime, headers={"Cache-Control": _CACHE_MEDIA})
    datos = media.leer_media(nombre)
    if datos is None:
        return JSONResponse({"error": "Esa imagen no existe."}, status_code=404)
    return _respuesta_media(datos, media.mime_de(nombre), request.headers.get("range"))


def _respuesta_media(datos: bytes, mime: str, rango: str | None) -> Response:
    """Sirve bytes de media con soporte de RANGO (HTTP Range) para audio/vídeo seekable.

    Sin `Range`: 200 con todo el cuerpo (+ `Accept-Ranges: bytes` para que el reproductor sepa que
    puede buscar). Con `Range: bytes=ini-fin`: 206 con solo ese tramo (`Content-Range`). Así el
    `<audio>` puede SALTAR a un segundo concreto sin descargar todo y empezar donde toca.
    """
    total = len(datos)
    cabeceras = {"Accept-Ranges": "bytes", "Cache-Control": _CACHE_MEDIA}
    if rango and rango.startswith("bytes=") and total:
        tramo = rango[len("bytes=") :].split(",", 1)[0].strip()
        ini_s, _, fin_s = tramo.partition("-")
        try:
            if not ini_s:  # sufijo: últimos N bytes
                ini, fin = max(0, total - int(fin_s)), total - 1
            else:
                ini = int(ini_s)
                fin = int(fin_s) if fin_s else total - 1
        except ValueError:
            ini, fin = 0, total - 1
        ini = max(0, ini)
        fin = min(fin, total - 1)
        if ini <= fin:
            cuerpo = datos[ini : fin + 1]
            return Response(
                cuerpo,
                status_code=206,
                media_type=mime,
                headers={
                    **cabeceras,
                    "Content-Range": f"bytes {ini}-{fin}/{total}",
                    "Content-Length": str(len(cuerpo)),
                },
            )
    return Response(datos, media_type=mime, headers=cabeceras)


def lanzar_generacion_imagen(
    *,
    prompt: str,
    modelo: str = "",
    marca: str = "",
    publicacion_id: str = "",
    titulo: str = "",
    autor: dict | None = None,
) -> dict:
    """Crea UNA generación de imagen y lanza su job en 2.º plano -> dict público de la generación.

    Camino ÚNICO de imagen reutilizable por todos los lanzadores manuales (botón «Generar con
    IA» de una pieza y «Generar arte a mano» por marca): `generaciones.crear` + el proveedor
    (`media.generar_imagen_detallado`, con `modelo` opcional) + `lanzar_job_imagen`. Captura el
    COSTE real del proveedor y lo sella en `metricas` para que el cierre lo vuelque al ledger
    `gasto_ia` (tipo `imagen`, con el modelo) y poder estimar el coste medio por imagen. Si la
    generación está correlada a una pieza (`publicacion_id`), deja además la etapa ARTE en su
    pipeline. El frontend sondea `GET /api/generaciones/{id}` y recoge `resultado={id,url,modelo,coste_usd}`.
    """
    autor = autor or {}

    def _generar() -> dict[str, object]:
        salida = media.generar_imagen_detallado(prompt, modelo=modelo)
        nombre = media.guardar_bytes(salida.datos, ext="png")
        # Para una pieza: deja la traza de la etapa ARTE en SU pipeline (prompt + salida reales).
        if publicacion_id:
            autogen_ilustrar.registrar_arte(
                publicacion_id=publicacion_id, marca=marca, titulo=titulo,
                prompt=prompt, imagen=nombre,
            )
        # Sella el gasto en el registro: el cierre lo vuelca al ledger por la vía única de
        # `presupuesto_ia.registrar_cierre` (coste real + modelo). Solo si hubo coste medible.
        if salida.coste_usd > 0:
            generaciones.actualizar(
                gen["id"],
                {"metricas": {"total_cost_usd": salida.coste_usd, "tokens_in": 0,
                              "tokens_out": 0, "modelo": salida.modelo}},
            )
        return {"id": nombre, "url": f"/api/media/{nombre}",
                "modelo": salida.modelo, "coste_usd": salida.coste_usd}

    gen = generaciones.crear(
        {
            # Con pieza, la generación pertenece a su pipeline (correlada por `publicacion_id`); el
            # `prompt` viaja para que el detalle del pipeline lo muestre (no "prompt no disponible").
            "tipo": "imagen",
            "marca": marca,
            "publicacion_id": publicacion_id,
            "prompt": prompt if publicacion_id else "",
            "etiqueta": (f"Arte · {titulo[:40]}" if titulo else f"Imagen · {prompt[:40]}"),
            "autor_id": autor.get("id", ""),
            "autor_nombre": autor.get("usuario", ""),
        }
    )
    try:
        generaciones.lanzar_job_imagen(gen["id"], generar=_generar)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos error en el registro
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "error": "No se pudo generar la imagen.",
             "fecha_fin": generaciones.ahora_iso()},
        )
    return generaciones.obtener(gen["id"]) or gen


async def generar(request: Request) -> Response:
    """Genera una imagen con IA EN SEGUNDO PLANO -> `{generacion}`.

    Cuerpo JSON: `{prompt, publicacion_id?|pieza_id?}`. Si la imagen es PARA UNA PIEZA
    (`publicacion_id`, o `pieza_id` que se resuelve a su contenido), la generación se
    CORRELACIONA a esa pieza (`publicacion_id` + marca) y al completarse registra la etapa ARTE
    de su pipeline (igual que el auto-arte): así sale DENTRO del pipeline de la pieza, no como
    una generación suelta. Sin pieza, es una generación de imagen suelta (caso sin pipeline).

    400 inmediato si no hay proveedor configurado. El frontend sondea `GET /api/generaciones/{id}`
    y, al completarse, recoge `resultado = {id, url, modelo, coste_usd}`.
    """
    datos = await leer_json(request)
    prompt = datos.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return JSONResponse({"error": "Falta el texto (prompt) para generar la imagen."}, status_code=400)
    if not media.proveedor_configurado():
        return JSONResponse(
            {
                "error": "La generación de imagen no está configurada. Añade una clave "
                "de proveedor de imagen para activarla."
            },
            status_code=400,
        )
    prompt = prompt.strip()

    # Pieza a la que pertenece (opcional): `publicacion_id` directo o vía `pieza_id`. De ella
    # sacamos marca y título para correlacionar la generación con el pipeline de la pieza.
    publicacion_id = str(datos.get("publicacion_id") or "").strip()
    pieza_id = str(datos.get("pieza_id") or "").strip()
    marca, titulo_pieza = "", ""
    if not publicacion_id and pieza_id:
        pub = repos.obtener_pieza(pieza_id)
        if pub:
            publicacion_id = str(pub.get("publicacion_id") or "")
            marca = str(pub.get("marca") or "")
    if publicacion_id:
        cont = repos.obtener_publicacion(publicacion_id)
        if cont:
            marca = marca or str(cont.get("marca") or "")
            titulo_pieza = str(cont.get("titulo") or "")

    # Atribucion por usuario (#130 Fase 1): la imagen la genera el usuario de la peticion.
    gen = lanzar_generacion_imagen(
        prompt=prompt, marca=marca, publicacion_id=publicacion_id,
        titulo=titulo_pieza, autor=autor_de_peticion(request) or {},
    )
    return JSONResponse({"generacion": gen})


async def desde_url(request: Request) -> Response:
    """Descarga una imagen desde una URL externa al almacén -> `{id, url}`.

    Reutiliza la imagen ORIGINAL de un artículo (p.ej. de un RSS de marca propia) como un
    asset PROPIO y publicable. Guard SSRF + tope de tamaño + validación de que el contenido
    sea realmente una imagen (en `extraccion_url.descargar_imagen_a_media`).
    """
    datos = await leer_json(request)
    url = datos.get("url")
    if not isinstance(url, str) or not url.strip():
        return JSONResponse({"error": "Falta la URL de la imagen."}, status_code=400)
    try:
        nombre = extraccion_url.descargar_imagen_a_media(url.strip())
    except extraccion_url.ExtraccionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo descargar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


RUTAS = [
    Route("/api/media", subir, methods=["POST"]),
    Route("/api/media/video", subir_video, methods=["POST"]),
    Route("/api/media/desde-url", desde_url, methods=["POST"]),
    Route("/api/media/generar", generar, methods=["POST"]),
    Route("/api/media/{nombre:path}", servir, methods=["GET"]),
]
