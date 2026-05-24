"""Feature Proyectos: ver/editar el CLAUDE.md de tus carpetas y abrir Claude Code.

La LOGICA de carpetas (allowlist en consola.toml) vive en el helper compartido
`consola.proyectos`; el lanzamiento de Claude Code en `consola.lanzador`. Esta
feature solo orquesta paginas + endpoints HTTP.

SEGURIDAD: guardar CLAUDE.md y "abrir en Claude Code" SOLO operan sobre carpetas
de la allowlist (consola.toml), resueltas por id estable. Sin shell=True. Los
errores salen como mensajes en espanol, sin tracebacks crudos.
"""

from __future__ import annotations

from html import escape

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .. import lanzador, layout, proyectos
from . import Feature, features_ordenadas

# Inyectable: `crear_app(abrir=...)` reasigna esto (los tests lo usan para NO
# lanzar nada real). Por defecto, la funcion de verdad.
abrir_en_claude_code = lanzador.abrir_en_claude_code


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _render_proyecto(p: proyectos.Proyecto) -> str:
    """Tarjeta de un proyecto: nombre, ruta, estado de CLAUDE.md, editor y acciones."""
    if not p.existe:
        chip = '<span class="chip error">carpeta no encontrada</span>'
    elif p.tiene_claude_md:
        chip = '<span class="chip ok">CLAUDE.md</span>'
    else:
        chip = '<span class="chip aviso">sin CLAUDE.md</span>'

    contenido_md = proyectos.claude_md_de(p) if p.existe else ""
    deshab = "disabled" if not p.existe else ""
    aviso = ""
    if not p.existe:
        aviso = (
            '<p class="aviso-global">La carpeta de este proyecto ya no existe en el '
            "disco. Corrige la ruta en consola.toml.</p>"
        )

    id_ta = f"md-{escape(p.id)}"
    return f"""
<section class="proyecto" data-id="{escape(p.id)}">
  <h2>{escape(p.nombre)} {chip}</h2>
  <div class="ruta">{escape(str(p.ruta))}</div>
  {aviso}
  <label class="oculto-visual" for="{id_ta}">Contenido del CLAUDE.md de {escape(p.nombre)}</label>
  <textarea id="{id_ta}" class="claude-md" spellcheck="false" {deshab}>{escape(contenido_md)}</textarea>
  <div class="acciones">
    <button type="button" class="primario" data-accion="guardar" {deshab}>Guardar CLAUDE.md</button>
    <button type="button" data-accion="abrir" {deshab}>Abrir en Claude Code</button>
    <span class="estado" role="status" aria-live="polite"></span>
  </div>
</section>
"""


def _pagina_proyectos(error: str | None = None) -> str:
    cuerpo: list[str] = [
        "<h1>Proyectos</h1>",
        '<p class="intro">Tus carpetas de proyecto. Edita el CLAUDE.md de cada una y '
        "lanza Claude Code dentro de la carpeta. Claude Code queda debajo como motor.</p>",
    ]
    if error:
        cuerpo.append(f'<p class="aviso-global" role="alert">{escape(error)}</p>')

    cuerpo.append(
        """
<form class="anadir" id="form-anadir">
  <h2>Anadir carpeta</h2>
  <p class="ayuda">Pega la ruta de una carpeta de tu equipo. La consola solo podra editar el
  CLAUDE.md y abrir Claude Code dentro de las carpetas que anadas aqui.</p>
  <div class="campos">
    <label class="oculto-visual" for="anadir-nombre">Nombre del proyecto</label>
    <input id="anadir-nombre" type="text" name="nombre" placeholder="Nombre del proyecto" autocomplete="off" required>
    <label class="oculto-visual" for="anadir-ruta">Ruta de la carpeta</label>
    <input id="anadir-ruta" type="text" name="ruta" placeholder="/ruta/a/la/carpeta" autocomplete="off" required>
    <button type="submit" class="primario">Anadir</button>
  </div>
  <p class="estado" role="status" aria-live="polite" style="margin-top:8px"></p>
</form>
"""
    )

    try:
        lista = proyectos.cargar_proyectos()
    except proyectos.ConsolaConfigInvalida as e:
        cuerpo.append(f'<p class="aviso-global" role="alert">{escape(str(e))}</p>')
        lista = []

    if not lista:
        cuerpo.append(
            '<div class="vacio">'
            "<p><strong>Aun no tienes carpetas.</strong></p>"
            "<p>Anade una carpeta con el formulario de arriba para empezar a editar su "
            "CLAUDE.md y abrir Claude Code dentro de ella.</p>"
            "</div>"
        )
    else:
        cuerpo.extend(_render_proyecto(p) for p in lista)

    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Proyectos",
        contenido="".join(cuerpo),
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_proyectos(request: Request) -> Response:
    return HTMLResponse(_pagina_proyectos())


async def _leer_json(request: Request) -> dict:
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- body invalido => dict vacio (se valida abajo)
        return {}
    return datos if isinstance(datos, dict) else {}


def _resolver_proyecto_o_400(proyecto_id: object) -> proyectos.Proyecto | JSONResponse:
    """Resuelve un proyecto por id contra la allowlist; 400 si no esta o el id falta."""
    if not isinstance(proyecto_id, str) or not proyecto_id:
        return JSONResponse({"error": "Falta el identificador del proyecto."}, status_code=400)
    p = proyectos.proyecto_por_id(proyecto_id)
    if p is None:
        # Rechazo de allowlist: el id no corresponde a ninguna carpeta configurada.
        return JSONResponse({"error": "Proyecto no permitido o inexistente."}, status_code=400)
    return p


async def api_guardar_claude_md(request: Request) -> Response:
    datos = await _leer_json(request)
    p = _resolver_proyecto_o_400(datos.get("id"))
    if isinstance(p, JSONResponse):
        return p
    contenido = datos.get("contenido")
    if not isinstance(contenido, str):
        return JSONResponse({"error": "Falta el contenido del CLAUDE.md."}, status_code=400)
    try:
        proyectos.guardar_claude_md(p, contenido)
    except (ValueError, OSError) as e:
        return JSONResponse({"error": f"No se pudo guardar: {e}"}, status_code=400)
    return JSONResponse({"mensaje": "CLAUDE.md guardado."})


async def api_abrir(request: Request) -> Response:
    datos = await _leer_json(request)
    p = _resolver_proyecto_o_400(datos.get("id"))
    if isinstance(p, JSONResponse):
        return p
    if not p.existe:
        return JSONResponse({"error": "La carpeta del proyecto ya no existe."}, status_code=400)
    try:
        # Inyectable: en tests se parchea esta funcion modulo-nivel.
        mensaje = abrir_en_claude_code(p.ruta)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"mensaje": mensaje})


async def api_anadir(request: Request) -> Response:
    datos = await _leer_json(request)
    nombre = datos.get("nombre")
    ruta = datos.get("ruta")
    if not isinstance(nombre, str) or not isinstance(ruta, str):
        return JSONResponse({"error": "Faltan el nombre o la ruta."}, status_code=400)
    try:
        p = proyectos.anadir_proyecto(nombre, ruta)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError as e:
        return JSONResponse({"error": f"No se pudo guardar la carpeta: {e}"}, status_code=400)
    return JSONResponse({"mensaje": f"Anadida la carpeta {p.nombre}."})


FEATURE = Feature(
    id="proyectos",
    etiqueta="Proyectos",
    orden=10,
    descripcion="Edita el CLAUDE.md de tus carpetas y abre Claude Code dentro de ellas.",
    rutas=[
        Route("/proyectos", pagina_proyectos),
        Route("/api/proyectos/claude-md", api_guardar_claude_md, methods=["POST"]),
        Route("/api/proyectos/abrir", api_abrir, methods=["POST"]),
        Route("/api/proyectos/anadir", api_anadir, methods=["POST"]),
    ],
)
