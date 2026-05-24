"""Feature Tareas: gestion de tareas por proyecto (lista, crear, hecha, borrar).

Cada tarea referencia un PROYECTO de la allowlist compartida (`consola.proyectos`,
la misma que usa la pestana Proyectos). La persistencia es local: un JSON en
`~/.config/keni-social/tareas.json` (o la ruta de la env var `KENI_CONSOLA_TAREAS`,
util para tests), con escritura ATOMICA (temp + rename).

SEGURIDAD:
  - Una tarea SOLO puede apuntar a un proyecto presente en la allowlist (consola.toml):
    al crear se valida el id contra `consola.proyectos.proyecto_por_id`. Las tareas
    cuyo proyecto ya no este en la allowlist se muestran como "huerfanas" y no dejan
    abrir Claude Code.
  - "Abrir en Claude Code" resuelve la carpeta SOLO desde la allowlist y delega en
    el lanzador compartido. Sin shell=True; sin rutas crudas del navegador.
  - Los formularios usan POST + redirect (PRG); los errores salen como mensajes en
    espanol, sin tracebacks crudos.

El wrapper `abrir_tarea_en_claude_code` es modulo-nivel para que los tests lo
parcheen (mockeen) y NO se lance nada real. Por defecto reusa
`consola.lanzador.abrir_en_claude_code` SIN editarlo.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date
from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .. import lanzador, layout, proyectos
from . import Feature, RecursoEstatico, features_ordenadas

ESTADOS = ("pendiente", "hecha")

_ESTATICOS = Path(__file__).parent.parent / "estaticos"


# Inyectable: wrapper PROPIO sobre el lanzador compartido. Los tests lo parchean
# para NO abrir nada real. Por defecto delega en la funcion de verdad, pasando
# SOLO la carpeta del proyecto (el lanzador no recibe rutas crudas del navegador).
def abrir_tarea_en_claude_code(ruta: Path, detalle: str = "") -> str:
    """Abre Claude Code en la carpeta de la tarea.

    `detalle` queda disponible como prompt inicial conceptual; hoy el lanzador
    compartido solo abre la carpeta (no se edita lanzador.py). Mantener la firma
    permite enriquecerlo mas adelante sin tocar el resto de la feature.
    """
    return lanzador.abrir_en_claude_code(ruta)


# --------------------------------------------------------------------------- #
# Persistencia local (JSON, escritura atomica)                                 #
# --------------------------------------------------------------------------- #


def ruta_tareas() -> Path:
    """Ruta del tareas.json. `KENI_CONSOLA_TAREAS` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_TAREAS")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "tareas.json"


def _normalizar(cruda: object) -> dict | None:
    """Valida/normaliza una tarea cruda del JSON; None si no es utilizable."""
    if not isinstance(cruda, dict):
        return None
    tid = cruda.get("id")
    proyecto_id = cruda.get("proyecto")
    titulo = cruda.get("titulo")
    if not (isinstance(tid, str) and tid):
        return None
    if not (isinstance(proyecto_id, str) and proyecto_id):
        return None
    if not (isinstance(titulo, str) and titulo.strip()):
        return None
    estado = cruda.get("estado")
    if estado not in ESTADOS:
        estado = "pendiente"
    detalle = cruda.get("detalle")
    fecha = cruda.get("fecha")
    return {
        "id": tid,
        "proyecto": proyecto_id,
        "titulo": titulo.strip(),
        "detalle": detalle.strip() if isinstance(detalle, str) else "",
        "estado": estado,
        "fecha": fecha if isinstance(fecha, str) and fecha else "",
    }


def cargar_tareas() -> list[dict]:
    """Lee tareas.json y devuelve la lista de tareas validas (vacia si no existe).

    Tolerante: un archivo ausente o ilegible devuelve lista vacia (no crashea la
    pestana). Las entradas invalidas se descartan silenciosamente.
    """
    ruta = ruta_tareas()
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return []
    crudas = datos.get("tareas") if isinstance(datos, dict) else None
    if not isinstance(crudas, list):
        return []
    tareas: list[dict] = []
    for c in crudas:
        if (t := _normalizar(c)) is not None:
            tareas.append(t)
    return tareas


def guardar_tareas(tareas: list[dict]) -> None:
    """Escribe la lista de tareas de forma ATOMICA (temp + os.replace)."""
    ruta = ruta_tareas()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + f".tmp-{uuid.uuid4().hex}")
    payload = json.dumps({"tareas": tareas}, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, ruta)


def crear_tarea(proyecto_id: str, titulo: str, detalle: str = "") -> dict:
    """Crea y persiste una tarea, validando el proyecto contra la allowlist.

    Lanza `ValueError` (en espanol) si faltan datos o el proyecto no esta permitido.
    """
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("La tarea necesita un titulo.")
    if not (proyecto_id or "").strip():
        raise ValueError("La tarea necesita un proyecto.")
    if proyectos.proyecto_por_id(proyecto_id) is None:
        # Rechazo de allowlist: solo se permiten proyectos configurados.
        raise ValueError("Proyecto no permitido o inexistente.")

    tarea = {
        "id": uuid.uuid4().hex[:12],
        "proyecto": proyecto_id,
        "titulo": titulo,
        "detalle": (detalle or "").strip(),
        "estado": "pendiente",
        "fecha": date.today().isoformat(),
    }
    tareas = cargar_tareas()
    tareas.append(tarea)
    guardar_tareas(tareas)
    return tarea


def _tarea_por_id(tareas: list[dict], tarea_id: str) -> dict | None:
    for t in tareas:
        if t["id"] == tarea_id:
            return t
    return None


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _opciones_proyecto(lista: list[proyectos.Proyecto]) -> str:
    opciones = ['<option value="">Elige un proyecto</option>']
    for p in lista:
        opciones.append(f'<option value="{escape(p.id)}">{escape(p.nombre)}</option>')
    return "".join(opciones)


def _render_tarea(t: dict) -> str:
    hecha = t["estado"] == "hecha"
    clase = "tarea hecha" if hecha else "tarea"
    chip = (
        '<span class="chip ok">hecha</span>'
        if hecha
        else '<span class="chip aviso">pendiente</span>'
    )
    detalle = ""
    if t["detalle"]:
        detalle = f'<p class="tarea-detalle">{escape(t["detalle"])}</p>'
    fecha = f'<span class="tarea-fecha">{escape(t["fecha"])}</span>' if t["fecha"] else ""

    tid = escape(t["id"])
    boton_hecha = (
        ""
        if hecha
        else (
            f'<form method="post" action="/tareas/{tid}/hecha" class="en-linea">'
            '<button type="submit">Marcar hecha</button></form>'
        )
    )
    return f"""
<li class="{clase}" data-id="{tid}">
  <div class="tarea-cabecera">
    <span class="tarea-titulo">{escape(t["titulo"])}</span>
    {chip}
    {fecha}
  </div>
  {detalle}
  <div class="tarea-acciones">
    <form method="post" action="/tareas/{tid}/abrir" class="en-linea">
      <button type="submit" class="primario">Abrir en Claude Code</button>
    </form>
    {boton_hecha}
    <form method="post" action="/tareas/{tid}/borrar" class="en-linea"
          onsubmit="return confirm('Borrar esta tarea?');">
      <button type="submit">Borrar</button>
    </form>
  </div>
</li>
"""


def _render_huerfana(t: dict) -> str:
    """Tarea cuyo proyecto ya no esta en la allowlist: visible pero sin abrir."""
    tid = escape(t["id"])
    return f"""
<li class="tarea huerfana" data-id="{tid}">
  <div class="tarea-cabecera">
    <span class="tarea-titulo">{escape(t["titulo"])}</span>
    <span class="chip error">proyecto no configurado</span>
  </div>
  <p class="tarea-detalle">El proyecto de esta tarea ya no esta en consola.toml. Borrala o
  vuelve a anadir su carpeta en la pestana Proyectos.</p>
  <div class="tarea-acciones">
    <form method="post" action="/tareas/{tid}/borrar" class="en-linea"
          onsubmit="return confirm('Borrar esta tarea?');">
      <button type="submit">Borrar</button>
    </form>
  </div>
</li>
"""


def _pagina_tareas(error: str | None = None, aviso_ok: str | None = None) -> str:
    cuerpo: list[str] = [
        "<h1>Tareas</h1>",
        '<p class="intro">Organiza tareas por proyecto y abre Claude Code dentro de la '
        "carpeta correspondiente para ponerte a trabajar.</p>",
    ]
    if error:
        cuerpo.append(f'<p class="aviso-global" role="alert">{escape(error)}</p>')
    if aviso_ok:
        cuerpo.append(f'<p class="aviso-ok" role="status">{escape(aviso_ok)}</p>')

    try:
        lista_proyectos = proyectos.cargar_proyectos()
    except proyectos.ConsolaConfigInvalida as e:
        cuerpo.append(f'<p class="aviso-global" role="alert">{escape(str(e))}</p>')
        lista_proyectos = []

    if lista_proyectos:
        cuerpo.append(
            f"""
<form class="anadir" id="form-tarea" method="post" action="/tareas/crear">
  <h2>Nueva tarea</h2>
  <p class="ayuda">Elige un proyecto configurado, ponle titulo y, si quieres, un detalle o
  prompt para arrancar el trabajo.</p>
  <div class="campos">
    <label class="oculto-visual" for="tarea-proyecto">Proyecto</label>
    <select id="tarea-proyecto" name="proyecto" required>{_opciones_proyecto(lista_proyectos)}</select>
    <label class="oculto-visual" for="tarea-titulo">Titulo de la tarea</label>
    <input id="tarea-titulo" type="text" name="titulo" placeholder="Titulo de la tarea" autocomplete="off" required>
  </div>
  <label class="oculto-visual" for="tarea-detalle">Detalle o prompt</label>
  <textarea id="tarea-detalle" name="detalle" class="tarea-detalle-input"
            placeholder="Detalle o prompt inicial (opcional)" spellcheck="false"></textarea>
  <div class="campos" style="margin-top:10px">
    <button type="submit" class="primario">Crear tarea</button>
  </div>
</form>
"""
        )
    else:
        cuerpo.append(
            '<div class="vacio">'
            "<p><strong>Aun no tienes proyectos configurados.</strong></p>"
            "<p>Anade una carpeta en la pestana <a href=\"/proyectos\">Proyectos</a> para poder "
            "crear tareas asociadas a ella.</p>"
            "</div>"
        )

    tareas = cargar_tareas()
    if not tareas:
        cuerpo.append(
            '<div class="vacio">'
            "<p><strong>No hay tareas todavia.</strong></p>"
            "<p>Crea la primera con el formulario de arriba.</p>"
            "</div>"
        )
    else:
        cuerpo.append(_render_grupos(tareas, lista_proyectos))

    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Tareas",
        contenido="".join(cuerpo),
        css=FEATURE.css,
    )


def _render_grupos(tareas: list[dict], lista_proyectos: list[proyectos.Proyecto]) -> str:
    """Agrupa las tareas por proyecto (proyectos de la allowlist + grupo huerfanas)."""
    nombre_por_id = {p.id: p.nombre for p in lista_proyectos}
    grupos: dict[str, list[dict]] = {}
    huerfanas: list[dict] = []
    for t in tareas:
        if t["proyecto"] in nombre_por_id:
            grupos.setdefault(t["proyecto"], []).append(t)
        else:
            huerfanas.append(t)

    partes: list[str] = []
    # Mantener el orden de los proyectos tal y como vienen de la allowlist.
    for p in lista_proyectos:
        del_grupo = grupos.get(p.id)
        if not del_grupo:
            continue
        items = "".join(_render_tarea(t) for t in del_grupo)
        partes.append(
            f'<section class="grupo-tareas" data-proyecto="{escape(p.id)}">'
            f"<h2>{escape(p.nombre)}</h2>"
            f'<ul class="lista-tareas">{items}</ul>'
            "</section>"
        )
    if huerfanas:
        items = "".join(_render_huerfana(t) for t in huerfanas)
        partes.append(
            '<section class="grupo-tareas huerfanas">'
            "<h2>Sin proyecto configurado</h2>"
            f'<ul class="lista-tareas">{items}</ul>'
            "</section>"
        )
    return "".join(partes)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_tareas(request: Request) -> Response:
    error = request.query_params.get("error") or None
    ok = request.query_params.get("ok") or None
    return HTMLResponse(_pagina_tareas(error=error, aviso_ok=ok))


def _redirigir(error: str | None = None, ok: str | None = None) -> RedirectResponse:
    """Redirige a /tareas (PRG) con un aviso opcional por query param."""
    destino = "/tareas"
    if error:
        from urllib.parse import quote

        destino = f"/tareas?error={quote(error)}"
    elif ok:
        from urllib.parse import quote

        destino = f"/tareas?ok={quote(ok)}"
    return RedirectResponse(url=destino, status_code=303)


async def crear_tarea_endpoint(request: Request) -> Response:
    form = await request.form()
    proyecto_id = form.get("proyecto")
    titulo = form.get("titulo")
    detalle = form.get("detalle")
    try:
        crear_tarea(
            proyecto_id if isinstance(proyecto_id, str) else "",
            titulo if isinstance(titulo, str) else "",
            detalle if isinstance(detalle, str) else "",
        )
    except ValueError as e:
        return _redirigir(error=str(e))
    return _redirigir(ok="Tarea creada.")


async def marcar_hecha(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    tareas = cargar_tareas()
    t = _tarea_por_id(tareas, tarea_id)
    if t is None:
        return _redirigir(error="La tarea ya no existe.")
    t["estado"] = "hecha"
    guardar_tareas(tareas)
    return _redirigir(ok="Tarea marcada como hecha.")


async def borrar_tarea(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    tareas = cargar_tareas()
    restantes = [t for t in tareas if t["id"] != tarea_id]
    if len(restantes) == len(tareas):
        return _redirigir(error="La tarea ya no existe.")
    guardar_tareas(restantes)
    return _redirigir(ok="Tarea borrada.")


async def abrir_tarea(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    tareas = cargar_tareas()
    t = _tarea_por_id(tareas, tarea_id)
    if t is None:
        return _redirigir(error="La tarea ya no existe.")
    # Allowlist: la carpeta solo se resuelve desde consola.proyectos por id estable.
    p = proyectos.proyecto_por_id(t["proyecto"])
    if p is None:
        return _redirigir(error="El proyecto de esta tarea ya no esta configurado.")
    if not p.existe:
        return _redirigir(error="La carpeta del proyecto ya no existe.")
    try:
        # Inyectable: en tests se parchea este wrapper modulo-nivel.
        mensaje = abrir_tarea_en_claude_code(p.ruta, t["detalle"])
    except RuntimeError as e:
        return _redirigir(error=str(e))
    return _redirigir(ok=mensaje)


FEATURE = Feature(
    id="tareas",
    etiqueta="Tareas",
    orden=40,
    descripcion="Organiza tareas por proyecto y abre Claude Code en su carpeta.",
    rutas=[
        Route("/tareas", pagina_tareas),
        Route("/tareas/crear", crear_tarea_endpoint, methods=["POST"]),
        Route("/tareas/{tarea_id}/hecha", marcar_hecha, methods=["POST"]),
        Route("/tareas/{tarea_id}/borrar", borrar_tarea, methods=["POST"]),
        Route("/tareas/{tarea_id}/abrir", abrir_tarea, methods=["POST"]),
    ],
    estaticos=[
        RecursoEstatico("tareas.css", _ESTATICOS / "tareas.css", "text/css; charset=utf-8"),
    ],
    css=["tareas.css"],
)
