"""Lanzar generación: compone el prompt (prompt + línea editorial adjunta + contexto) y
ENCOLA un trabajo de `claude -p` reutilizando la infra de generaciones (`prompts_lanzar`).

`POST /api/prompts/lanzar` (JSON: contenido pegado / url / área de la Consola) y
`POST /api/prompts/lanzar-archivo` (multipart: archivo). El frontend sondea
`GET /api/generaciones/{id}` hasta el estado terminal. `ColaLlenaError` se deja PROPAGAR:
el manejador central de `app.py` la traduce a 429.
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

from ... import libprompts, redes
from ..._http_json import leer_json
from ...dominio import extraccion_url
from ...produccion import prompts_lanzar
from ...seguridad import autor_de_peticion
from ._comun import _MAX_TEXTO

# Subida de archivo: limite y trozo de lectura.
_MAX_SUBIDA = 100 * 1024 * 1024  # 100 MB
_TROZO = 1024 * 1024
# Extensiones que tratamos como TEXTO (se leen e incrustan); el resto es MEDIA (se pasa la ruta).
_EXTS_TEXTO = frozenset({"", ".txt", ".md", ".markdown", ".csv", ".json", ".rtf", ".log"})
_RE_EXT = re.compile(r"^\.[a-z0-9]{1,8}$")


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
            return prompts_lanzar.area_contexto(valor if isinstance(valor, str) else "", marca), "", None
        except libprompts.PromptsError as e:
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
    """`POST /api/prompts/lanzar` -> compone y ENCOLA -> `{generacion}`.

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
        gen = prompts_lanzar.lanzar(
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
    except libprompts.PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


def _extension_segura(nombre: str | None) -> str:
    """Extension en minusculas (`.mp4`, `.txt`) o "" si no es reconocible."""
    if not nombre:
        return ""
    suf = Path(nombre).suffix.lower()
    return suf if _RE_EXT.match(suf) else ""


async def _guardar_subida(archivo: UploadFile) -> tuple[Path, Path, str]:
    """Vuelca un `UploadFile` a un temporal con extensión normalizada. Devuelve (ruta, dir_temporal, extension)."""
    dir_temporal = Path(tempfile.mkdtemp(prefix="keni-texto-"))
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
                    raise libprompts.PromptsError("El archivo es demasiado grande.")
                salida.write(trozo)
    except libprompts.PromptsError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise libprompts.PromptsError("No se pudo guardar el archivo subido.") from e
    if total == 0:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise libprompts.PromptsError("El archivo está vacío.")
    return destino, dir_temporal, ext


async def lanzar_archivo(request: Request) -> Response:
    """`POST /api/prompts/lanzar-archivo` (multipart) -> compone con el archivo -> `{generacion}`.

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
    except libprompts.PromptsError as e:
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
        gen = prompts_lanzar.lanzar(
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
    except libprompts.PromptsError as e:
        if dir_para_lanzar is not None:
            shutil.rmtree(dir_para_lanzar, ignore_errors=True)
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})
