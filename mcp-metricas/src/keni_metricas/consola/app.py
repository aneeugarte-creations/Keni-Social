"""App Starlette de la Consola Keni (capa de gestion web LOCAL).

Sirve dos pestanas — Proyectos y Metricas — con HTML renderizado en servidor y
CSS/JS propios servidos por la app (sin CDN, sin red externa). Bind SOLO a
127.0.0.1 (ver `__main__.py`). Reutiliza las funciones de metricas existentes
(`config`, `reporte`, `dashboard`) y NO reimplementa nada de eso.

SEGURIDAD (resumen): el guardado de CLAUDE.md y el "abrir en Claude Code" SOLO
operan sobre carpetas presentes en consola.toml (allowlist por id estable); las
rutas se resuelven y se comparan contra la allowlist; sin shell=True; los errores
salen como mensajes en espanol (sin tracebacks crudos al cliente).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from ..config import cargar_config, construir_fuente
from ..dashboard import generar_dashboard
from ..reporte import construir_reporte, render_csv
from ..schema import RANGOS_DIAS
from . import lanzador, proyectos

# Inyectable: los tests parchean `app_modulo.abrir_en_claude_code` (o pasan otra
# funcion a `crear_app`) para NO lanzar nada real. Por defecto, la de verdad.
abrir_en_claude_code = lanzador.abrir_en_claude_code

# Rangos validos para la pestana Metricas (misma fuente de verdad que el schema).
RANGOS_VALIDOS = tuple(RANGOS_DIAS.keys())

_DIR_ESTATICOS = Path(__file__).parent / "estaticos"


# --------------------------------------------------------------------------- #
# Plantillas HTML (server-side, sin motor de plantillas: f-strings + escape).  #
# --------------------------------------------------------------------------- #


def _layout(titulo: str, activa: str, contenido: str) -> str:
    """Cascaron comun: barra superior + pestanas + <main>. `activa` = ruta actual."""
    def clase(ruta: str) -> str:
        return "activa" if ruta == activa else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)} — Consola Keni</title>
<link rel="stylesheet" href="/estaticos/consola.css">
</head>
<body>
<header class="barra">
<div class="marca-keni">KENI AI <span class="sub">Consola</span></div>
<nav class="pestanas">
<a href="/proyectos" class="{clase('proyectos')}">Proyectos</a>
<a href="/metricas" class="{clase('metricas')}">Metricas</a>
</nav>
</header>
<main>
{contenido}
</main>
<script src="/estaticos/consola.js"></script>
</body>
</html>
"""


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

    return f"""
<section class="proyecto" data-id="{escape(p.id)}">
  <h2>{escape(p.nombre)} {chip}</h2>
  <div class="ruta">{escape(str(p.ruta))}</div>
  {aviso}
  <textarea class="claude-md" spellcheck="false" {deshab}>{escape(contenido_md)}</textarea>
  <div class="acciones">
    <button type="button" class="primario" data-accion="guardar" {deshab}>Guardar CLAUDE.md</button>
    <button type="button" data-accion="abrir" {deshab}>Abrir en Claude Code</button>
    <span class="estado"></span>
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
        cuerpo.append(f'<p class="aviso-global">{escape(error)}</p>')

    cuerpo.append(
        """
<form class="anadir" id="form-anadir">
  <h2>Anadir carpeta</h2>
  <div class="campos">
    <input type="text" name="nombre" placeholder="Nombre del proyecto" autocomplete="off" required>
    <input type="text" name="ruta" placeholder="/ruta/a/la/carpeta" autocomplete="off" required>
    <button type="submit" class="primario">Anadir</button>
  </div>
  <p class="estado" style="margin-top:8px"></p>
</form>
"""
    )

    try:
        lista = proyectos.cargar_proyectos()
    except proyectos.ConsolaConfigInvalida as e:
        cuerpo.append(f'<p class="aviso-global">{escape(str(e))}</p>')
        lista = []

    if not lista:
        cuerpo.append('<p class="vacio">Aun no hay proyectos. Anade una carpeta arriba para empezar.</p>')
    else:
        cuerpo.extend(_render_proyecto(p) for p in lista)

    return _layout("Proyectos", "proyectos", "".join(cuerpo))


def _pagina_metricas() -> str:
    # Selector de marca desde la fuente activa (scoped por config si aplica).
    try:
        fuente = construir_fuente(cargar_config())
        cuentas = fuente.cuentas()
    except Exception:  # noqa: BLE001 — sin fuente valida igualmente mostramos la pestana
        cuentas = []

    opciones_marca = ['<option value="">Todas las marcas</option>']
    for c in cuentas:
        opciones_marca.append(f'<option value="{escape(c.id)}">{escape(c.nombre)}</option>')

    etiquetas_rango = {"semana": "Semana", "mes": "Mes", "7d": "7 dias", "30d": "30 dias"}
    opciones_rango = []
    for r in RANGOS_VALIDOS:
        sel = " selected" if r == "mes" else ""
        opciones_rango.append(f'<option value="{escape(r)}"{sel}>{escape(etiquetas_rango.get(r, r))}</option>')

    contenido = f"""
<h1>Metricas</h1>
<p class="intro">Dashboard consolidado de redes (mismas funciones que el reporte). Elige marca y rango.</p>
<div class="controles">
  <label>Marca
    <select id="sel-marca">{"".join(opciones_marca)}</select>
  </label>
  <label>Rango
    <select id="sel-rango">{"".join(opciones_rango)}</select>
  </label>
  <a id="enlace-csv" class="boton" href="/metricas/export.csv?rango=mes" download>Descargar CSV</a>
</div>
<iframe id="iframe-dashboard" class="dashboard" title="Dashboard de metricas" src="about:blank"></iframe>
"""
    return _layout("Metricas", "metricas", contenido)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def raiz(request: Request) -> Response:
    return RedirectResponse(url="/proyectos")


async def pagina_proyectos(request: Request) -> Response:
    return HTMLResponse(_pagina_proyectos())


async def pagina_metricas(request: Request) -> Response:
    return HTMLResponse(_pagina_metricas())


async def _leer_json(request: Request) -> dict:
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 — body invalido => dict vacio (se valida abajo)
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


def _fuente_para(marca: str | None):
    """Fuente activa, opcionalmente acotada a UNA marca (selector de la pestana)."""
    from ..config import FuenteScoped

    fuente = construir_fuente(cargar_config())
    if marca:
        return FuenteScoped(fuente, [marca])
    return fuente


def _validar_rango(rango: str) -> str:
    return rango if rango in RANGOS_VALIDOS else "mes"


async def metricas_dashboard(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        html = generar_dashboard(fuente, rango)
    except ValueError as e:
        return HTMLResponse(
            _layout("Metricas", "metricas", f'<p class="aviso-global">{escape(str(e))}</p>'),
            status_code=400,
        )
    except Exception:  # noqa: BLE001 — nunca un traceback crudo al navegador
        return HTMLResponse(
            _layout(
                "Metricas",
                "metricas",
                '<p class="aviso-global">No se pudo generar el dashboard.</p>',
            ),
            status_code=500,
        )
    return HTMLResponse(html)


async def metricas_export_csv(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        rep = construir_reporte(fuente, rango)
        csv_texto = render_csv(rep)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el CSV.", status_code=500)
    sufijo = f"-{marca}" if marca else ""
    nombre = f"metricas-{rango}{sufijo}.csv"
    return Response(
        csv_texto,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def _servir_estatico(nombre: str, media_type: str):
    async def handler(request: Request) -> Response:
        archivo = _DIR_ESTATICOS / nombre
        try:
            texto = archivo.read_text(encoding="utf-8")
        except OSError:
            return PlainTextResponse("No encontrado", status_code=404)
        return Response(texto, media_type=media_type)

    return handler


def crear_app(abrir=None) -> Starlette:
    """Construye la app Starlette de la consola.

    `abrir`: funcion opcional `(Path) -> str` para lanzar Claude Code; por defecto
    la real (`lanzador.abrir_en_claude_code`). Los tests pasan un mock o parchean
    el atributo modulo `abrir_en_claude_code`.
    """
    if abrir is not None:
        global abrir_en_claude_code
        abrir_en_claude_code = abrir

    # Aseguramos que existe el consola.toml (best-effort; no rompe si falla).
    try:
        proyectos.crear_config_si_falta()
    except OSError:
        pass

    rutas = [
        Route("/", raiz),
        Route("/proyectos", pagina_proyectos),
        Route("/metricas", pagina_metricas),
        Route("/metricas/dashboard", metricas_dashboard),
        Route("/metricas/export.csv", metricas_export_csv),
        Route("/api/proyectos/claude-md", api_guardar_claude_md, methods=["POST"]),
        Route("/api/proyectos/abrir", api_abrir, methods=["POST"]),
        Route("/api/proyectos/anadir", api_anadir, methods=["POST"]),
        Route("/estaticos/consola.css", _servir_estatico("consola.css", "text/css; charset=utf-8")),
        Route("/estaticos/consola.js", _servir_estatico("consola.js", "application/javascript; charset=utf-8")),
    ]
    return Starlette(routes=rutas)
