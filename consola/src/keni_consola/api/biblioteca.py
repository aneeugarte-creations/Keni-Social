"""API de la BIBLIOTECA: documentos (prompts + linea editorial) + lanzar generacion.

CRUD del almacen unico de documentos markdown (`biblioteca`) + el endpoint de LANZAR un
prompt sobre un target (contenido pegado / archivo / url / area de la Consola), que compone
el prompt (prompt + linea editorial adjunta + contexto) y ENCOLA un trabajo de `claude -p`
reutilizando la infra de generaciones (`dominio.biblioteca_lanzar`). El frontend sondea
`GET /api/generaciones/{id}` hasta el estado terminal.

La app descubre este modulo por su variable `RUTAS` (ver `api/__init__.py`); no se toca
`app.py`. Errores como JSON en espanol. `ColaLlenaError` se deja PROPAGAR: el manejador
central de `app.py` la traduce a 429.

ORDEN DE RUTAS: las estaticas (`/papelera`, `/editoriales`, `/areas`, `/lanzar`,
`/lanzar-archivo`) van ANTES que la parametrica `/{doc_id:path}` (que captura barras) para
que Starlette las case primero.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import biblioteca, marcas, redes
from .._http_json import leer_json
from ..dominio import biblioteca_lanzar, extraccion_url
from ..seguridad import autor_de_peticion

# Tope de tamano del bloque de contexto (texto pegado / leido de archivo / url) en chars.
_MAX_TEXTO = 200_000
# Subida de archivo: limite y trozo de lectura.
_MAX_SUBIDA = 100 * 1024 * 1024  # 100 MB
_TROZO = 1024 * 1024
# Extensiones que tratamos como TEXTO (se leen e incrustan); el resto es MEDIA (se pasa la ruta).
_EXTS_TEXTO = frozenset({"", ".txt", ".md", ".markdown", ".csv", ".json", ".rtf", ".log"})
_RE_EXT = re.compile(r"^\.[a-z0-9]{1,8}$")


# --------------------------------------------------------------------------- #
# CRUD de documentos                                                          #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """`GET /api/biblioteca?tipo=&carpeta=&q=` -> `{documentos: [...], carpetas: [...]}`."""
    tipo = request.query_params.get("tipo") or None
    carpeta = request.query_params.get("carpeta") or None
    q = request.query_params.get("q") or None
    docs = biblioteca.listar(tipo=tipo, carpeta=carpeta, q=q)
    return JSONResponse({
        "documentos": [d.a_dict() for d in docs],
        "carpetas": biblioteca.listar_carpetas(tipo=tipo),
    })


async def crear(request: Request) -> Response:
    """`POST /api/biblioteca` -> crea un documento `{titulo, tipo, ...}` -> `{documento}`."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
    kwargs: dict[str, object] = {}
    for clave in ("tipo", "carpeta", "cuerpo", "clase"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    if isinstance(datos.get("marcas"), list):
        kwargs["marcas"] = [m for m in datos["marcas"] if isinstance(m, str)]
    try:
        doc = biblioteca.crear(titulo, **kwargs)
    except biblioteca.BibliotecaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"documento": doc.a_dict()})


async def obtener(request: Request) -> Response:
    """`GET /api/biblioteca/{doc_id}` -> `{documento}` (404 si no existe)."""
    doc = biblioteca.obtener(request.path_params["doc_id"])
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    return JSONResponse({"documento": doc.a_dict()})


async def guardar(request: Request) -> Response:
    """`PUT /api/biblioteca/{doc_id}` -> actualiza -> `{documento}` (puede cambiar el id)."""
    doc_id = request.path_params["doc_id"]
    datos = await leer_json(request)
    kwargs: dict[str, object] = {}
    for clave in ("titulo", "cuerpo", "carpeta", "clase"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    if isinstance(datos.get("marcas"), list):
        kwargs["marcas"] = [m for m in datos["marcas"] if isinstance(m, str)]
    try:
        doc = biblioteca.guardar(doc_id, **kwargs)
    except biblioteca.BibliotecaError as e:
        # "no existe" -> 404; el resto (validacion) -> 400.
        codigo = 404 if "no existe" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": doc.a_dict()})


async def borrar(request: Request) -> Response:
    """`DELETE /api/biblioteca/{doc_id}` -> a papelera -> `{mensaje}` (404)."""
    try:
        biblioteca.borrar(request.path_params["doc_id"])
    except biblioteca.BibliotecaError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"mensaje": "Documento movido a la papelera."})


# --------------------------------------------------------------------------- #
# Papelera                                                                     #
# --------------------------------------------------------------------------- #


async def papelera_listar(request: Request) -> Response:
    """`GET /api/biblioteca/papelera` -> `{papelera: [...]}`."""
    return JSONResponse({"papelera": biblioteca.listar_papelera()})


async def papelera_restaurar(request: Request) -> Response:
    """`POST /api/biblioteca/papelera/{pid}/restaurar` -> `{documento}` (400/404)."""
    try:
        doc = biblioteca.restaurar(request.path_params["pid"])
    except biblioteca.BibliotecaError as e:
        codigo = 404 if "no está en la papelera" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": doc.a_dict()})


# --------------------------------------------------------------------------- #
# Linea editorial: auto-adjunto + areas disponibles                            #
# --------------------------------------------------------------------------- #


async def editoriales(request: Request) -> Response:
    """`GET /api/biblioteca/editoriales?marca=` -> `{editoriales: [...]}` (auto-adjunto)."""
    marca = request.query_params.get("marca") or ""
    docs = biblioteca.editoriales_de_marca(marca)
    return JSONResponse({"editoriales": [d.a_dict() for d in docs]})


async def areas(request: Request) -> Response:
    """`GET /api/biblioteca/areas` -> `{areas: [{id, nombre}]}` (secciones como contexto)."""
    return JSONResponse({"areas": biblioteca_lanzar.areas_disponibles()})


async def marcas_disponibles(request: Request) -> Response:
    """`GET /api/biblioteca/marcas` -> `{marcas: [{id, nombre}]}` (catalogo de marcas).

    La Biblioteca es autosuficiente: expone su propio catalogo de marcas (en vez de
    depender del endpoint de skills, que se retira) para poblar el selector del SPA.
    """
    return JSONResponse({"marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()]})


# --------------------------------------------------------------------------- #
# Lanzar (JSON: contenido / url / area) y lanzar-archivo (multipart)           #
# --------------------------------------------------------------------------- #


def _adjuntos_lista(crudo: object) -> list[str]:
    """Normaliza la lista de ids de documentos editoriales a adjuntar."""
    return [a for a in crudo if isinstance(a, str)] if isinstance(crudo, list) else []


def _redes_lista(crudo: object) -> list[str]:
    """Filtra ids de red contra las canonicas (orden de llegada, sin duplicar).

    Solo importa en el MODO PIEZAS (prompt `salida=piezas`); para prompts normales el
    dominio ignora las redes. Devuelve [] si no llega una lista o no hay ids validos.
    """
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


def _bloque_de_target(target: dict, marca: str) -> tuple[str, str, Response | None]:
    """Resuelve el target a un BLOQUE DE CONTEXTO. Devuelve (bloque, titulo_sugerido, error).

    `titulo_sugerido` solo lo da la URL (el titular real de la página): sirve para que el
    borrador NO se titule con la primera línea del bloque (que, en una URL, es el AVISO de
    extracción automática). Para el resto de targets es "" (el título se deriva del contenido).
    """
    tipo = target.get("tipo") if isinstance(target, dict) else None
    valor = target.get("valor") if isinstance(target, dict) else None

    if not tipo or tipo == "ninguno":
        return "", "", None
    if tipo == "contenido":
        return (valor if isinstance(valor, str) else "")[:_MAX_TEXTO], "", None
    if tipo == "area":
        try:
            return biblioteca_lanzar.area_contexto(valor if isinstance(valor, str) else "", marca), "", None
        except biblioteca.BibliotecaError as e:
            return "", "", JSONResponse({"error": str(e)}, status_code=400)
    if tipo == "url":
        url_limpia, error = extraccion_url.validar_url(valor)
        if error is not None:
            return "", "", JSONResponse({"error": error}, status_code=400)
        try:
            titulo, cuerpo = extraccion_url.extraer_texto(url_limpia)
        except extraccion_url.ExtraccionError as e:
            return "", "", JSONResponse({"error": str(e)}, status_code=502)
        nota = extraccion_url.componer_nota_no_verificada(url_limpia, titulo, cuerpo)
        return nota[:_MAX_TEXTO], titulo.strip(), None
    return "", "", JSONResponse({"error": "Tipo de target no válido."}, status_code=400)


async def lanzar(request: Request) -> Response:
    """`POST /api/biblioteca/lanzar` -> compone y ENCOLA -> `{generacion}`.

    Cuerpo JSON: `{prompt_id?|texto?, titulo?, marca, adjuntos?: [ids], target: {tipo, valor}}`.
    `target.tipo ∈ {ninguno, contenido, url, area}`. Marca/prompt los valida el dominio.
    """
    datos = await leer_json(request)
    marca = datos.get("marca")
    if not isinstance(marca, str) or not marca:
        return JSONResponse({"error": "Falta la marca."}, status_code=400)

    bloque, titulo_contenido, error = _bloque_de_target(datos.get("target") or {}, marca)
    if error is not None:
        return error

    try:
        gen = biblioteca_lanzar.lanzar(
            prompt_id=datos.get("prompt_id") if isinstance(datos.get("prompt_id"), str) else None,
            texto=datos.get("texto") if isinstance(datos.get("texto"), str) else None,
            titulo=datos.get("titulo") if isinstance(datos.get("titulo"), str) else "",
            marca=marca,
            adjuntos_ids=_adjuntos_lista(datos.get("adjuntos")),
            bloque_contexto=bloque,
            titulo_contenido=titulo_contenido,
            redes_ids=_redes_lista(datos.get("redes")),
            autor=autor_de_peticion(request),
        )
    except biblioteca.BibliotecaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


def _extension_segura(nombre: str | None) -> str:
    """Extension en minusculas (`.mp4`, `.txt`) o "" si no es reconocible."""
    if not nombre:
        return ""
    suf = Path(nombre).suffix.lower()
    return suf if _RE_EXT.match(suf) else ""


async def _guardar_subida(archivo: UploadFile) -> tuple[Path, Path, str]:
    """Vuelca un `UploadFile` a un temporal saneado. Devuelve (ruta, dir_temporal, extension)."""
    dir_temporal = Path(tempfile.mkdtemp(prefix="keni-biblioteca-"))
    ext = _extension_segura(archivo.filename)
    destino = dir_temporal / f"{uuid.uuid4().hex}{ext}"
    total = 0
    try:
        with destino.open("wb") as salida:
            while True:
                trozo = await archivo.read(_TROZO)
                if not trozo:
                    break
                total += len(trozo)
                if total > _MAX_SUBIDA:
                    raise biblioteca.BibliotecaError("El archivo es demasiado grande.")
                salida.write(trozo)
    except biblioteca.BibliotecaError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise biblioteca.BibliotecaError("No se pudo guardar el archivo subido.") from e
    if total == 0:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise biblioteca.BibliotecaError("El archivo está vacío.")
    return destino, dir_temporal, ext


async def lanzar_archivo(request: Request) -> Response:
    """`POST /api/biblioteca/lanzar-archivo` (multipart) -> compone con el archivo -> `{generacion}`.

    Form: `archivo`, `marca`, `prompt_id?`/`texto?`, `titulo?`, `adjuntos` (repetido o CSV).
    Texto (.txt/.md/...) se LEE e incrusta; media (imagen/video) se pasa por RUTA temporal
    (claude la lee en local; el lanzador borra el temporal al terminar).
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    marca = form.get("marca")
    archivo = form.get("archivo")
    if not isinstance(marca, str) or not marca:
        return JSONResponse({"error": "Falta la marca."}, status_code=400)
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ningún archivo."}, status_code=400)

    adjuntos: list[str] = []
    for valor in form.getlist("adjuntos"):
        if isinstance(valor, str):
            adjuntos.extend(p.strip() for p in valor.split(",") if p.strip())

    # Redes (modo PIEZAS): campo repetido o CSV. Se filtran contra las canonicas.
    redes_crudas: list[str] = []
    for valor in form.getlist("redes"):
        if isinstance(valor, str):
            redes_crudas.extend(p.strip() for p in valor.split(",") if p.strip())
    redes_ids = _redes_lista(redes_crudas)

    try:
        ruta, dir_temporal, ext = await _guardar_subida(archivo)
    except biblioteca.BibliotecaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    bloque = ""
    dir_para_lanzar: Path | None = None
    if ext in _EXTS_TEXTO:
        try:
            bloque = ruta.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXTO]
        finally:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        if not bloque.strip():
            return JSONResponse({"error": "El archivo está vacío."}, status_code=400)
    else:
        # MEDIA: el temporal vive hasta que termine el trabajo (claude lo lee en local).
        bloque = f"Hay un archivo adjunto para esta tarea en la ruta local: {ruta}"
        dir_para_lanzar = dir_temporal

    def _campo(nombre: str) -> str | None:
        v = form.get(nombre)
        return v if isinstance(v, str) and v else None

    try:
        gen = biblioteca_lanzar.lanzar(
            prompt_id=_campo("prompt_id"),
            texto=_campo("texto"),
            titulo=_campo("titulo") or "",
            marca=marca,
            adjuntos_ids=adjuntos,
            bloque_contexto=bloque,
            redes_ids=redes_ids,
            dir_temporal=dir_para_lanzar,
            autor=autor_de_peticion(request),
        )
    except biblioteca.BibliotecaError as e:
        if dir_para_lanzar is not None:
            shutil.rmtree(dir_para_lanzar, ignore_errors=True)
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


# Rutas: estaticas ANTES que la parametrica `/{doc_id:path}` (captura barras).
RUTAS = [
    Route("/api/biblioteca", listar, methods=["GET"]),
    Route("/api/biblioteca", crear, methods=["POST"]),
    Route("/api/biblioteca/papelera", papelera_listar, methods=["GET"]),
    Route("/api/biblioteca/papelera/{pid}/restaurar", papelera_restaurar, methods=["POST"]),
    Route("/api/biblioteca/editoriales", editoriales, methods=["GET"]),
    Route("/api/biblioteca/areas", areas, methods=["GET"]),
    Route("/api/biblioteca/marcas", marcas_disponibles, methods=["GET"]),
    Route("/api/biblioteca/lanzar", lanzar, methods=["POST"]),
    Route("/api/biblioteca/lanzar-archivo", lanzar_archivo, methods=["POST"]),
    Route("/api/biblioteca/{doc_id:path}", obtener, methods=["GET"]),
    Route("/api/biblioteca/{doc_id:path}", guardar, methods=["PUT"]),
    Route("/api/biblioteca/{doc_id:path}", borrar, methods=["DELETE"]),
]
