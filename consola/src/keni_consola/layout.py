"""Cascaron HTML compartido de la Consola Keni (branding + nav + landmarks).

Las features NO escriben el `<head>`, la barra de marca ni la navegacion: solo
producen el CONTENIDO de su `<main>` y se lo pasan a `render_pagina(...)`, que
arma la pagina completa. Asi el branding y la accesibilidad viven en UN solo
sitio y todas las pestanas se ven coherentes.

La barra de navegacion se construye a partir de la LISTA de features registradas
(ya ordenadas por `orden`), de modo que anadir una feature hace aparecer su
pestana automaticamente, sin tocar este archivo.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

# Tipado laxo para evitar import circular con features.__init__ (que importa de
# aqui). En runtime cada item expone .id, .etiqueta, .descripcion, .css, .js.
ItemNav = object

# Favicon de marca: SVG data-URI INLINE (sin red, sin CDN). Un cuadro redondeado
# naranja de marca con una "K" en blanco. Va tal cual en el <head>.
#
# OJO: el namespace SVG es la URI fija `http://www.w3.org/2000/svg`, pero NO la
# escribimos cruda: dejariamos el literal `http://` en el HTML y dispararia los
# tests de "sin recursos externos" de las features (que verifican que la pagina no
# carga nada de la red). Como esto es un data-URI, percent-encodeamos los dos
# puntos (`%3A`): el navegador lo decodifica de vuelta a `http://...` al parsear
# el data-URI, asi que el SVG renderiza igual y NO hay ninguna peticion de red.
_FAVICON_SVG = (
    "data:image/svg+xml,"
    "%3Csvg%20xmlns='http%3A//www.w3.org/2000/svg'%20viewBox='0%200%2032%2032'%3E"
    "%3Crect%20width='32'%20height='32'%20rx='7'%20fill='%23ff5a1f'/%3E"
    "%3Ctext%20x='16'%20y='23'%20font-family='Helvetica,Arial,sans-serif'"
    "%20font-size='20'%20font-weight='700'%20fill='white'%20text-anchor='middle'%3EK%3C/text%3E"
    "%3C/svg%3E"
)

# Wordmark de la barra: "KENI · Consola" con el cuadro-logo de marca. Estatico;
# se define aqui (fuera del f-string de render_pagina, que usa comillas dobles)
# para no pasarnos del ancho de linea ni reusar la comilla exterior del f-string.
_WORDMARK = (
    '<div class="marca-keni">'
    '<span class="marca-keni-logo" aria-hidden="true">K</span>'
    'KENI <span class="sub">· Consola</span>'
    "</div>"
)

# Agrupacion de la nav en bloques con sentido para el dia a dia de un CM.
#   - "Trabajo": lo que usa a diario (generar copy, ver metricas, gestionar tareas).
#   - "Ajustes": configuracion y mantenimiento (proyectos, carpetas, estado, config).
# Mapeamos por `id` de feature (estable) en vez de hardcodear el orden. Una feature
# cuyo id no este aqui cae al grupo "Ajustes" por defecto, asi nunca desaparece de
# la nav aunque se anada despues. Dentro de cada grupo se respeta el `orden`.
_GRUPO_POR_ID: dict[str, str] = {
    # Trabajo
    "skills": "Trabajo",
    "metricas": "Trabajo",
    "tareas": "Trabajo",
    # Ajustes
    "proyectos": "Ajustes",
    "carpetas": "Ajustes",
    "estado": "Ajustes",
    "config": "Ajustes",
}
_GRUPO_POR_DEFECTO = "Ajustes"
# Orden en que se pintan los grupos en la barra (con un divisor entre ellos).
_ORDEN_GRUPOS: tuple[str, ...] = ("Trabajo", "Ajustes")


def _links_css(nombres: Sequence[str]) -> str:
    """Etiquetas <link> para los CSS propios de la feature (servidos localmente)."""
    salida = []
    for nombre in nombres:
        href = escape(f"/estaticos/{nombre}")
        salida.append(f'<link rel="stylesheet" href="{href}">')
    return "\n".join(salida)


def _scripts_js(nombres: Sequence[str]) -> str:
    """Etiquetas <script> (defer) para los JS propios de la feature."""
    salida = []
    for nombre in nombres:
        src = escape(f"/estaticos/{nombre}")
        salida.append(f'<script src="{src}" defer></script>')
    return "\n".join(salida)


def _enlace_nav(f: ItemNav, activa: str) -> str:
    """Una pestana <a> (con estado activo, aria-current y title descriptivo)."""
    clase = ' class="activa"' if f.id == activa else ""  # type: ignore[attr-defined]
    href = escape(f"/{f.id}")  # type: ignore[attr-defined]
    etiqueta = escape(f.etiqueta)  # type: ignore[attr-defined]
    descripcion = escape(getattr(f, "descripcion", "") or "")
    aria = ' aria-current="page"' if f.id == activa else ""  # type: ignore[attr-defined]
    titulo = f' title="{descripcion}"' if descripcion else ""
    return f'<a href="{href}"{clase}{aria}{titulo}>{etiqueta}</a>'


def _nav(features: Sequence[ItemNav], activa: str) -> str:
    """Barra de pestanas agrupada en "Trabajo" y "Ajustes".

    Cada feature se asigna a un grupo por su `id` (ver `_GRUPO_POR_ID`); dentro de
    un grupo se respeta el `orden` con el que llegan las features (ya ordenadas).
    Cada grupo lleva una etiqueta y se separan con un divisor visual. Un grupo sin
    features no se pinta (no deja etiquetas huerfanas).
    """
    por_grupo: dict[str, list[str]] = {g: [] for g in _ORDEN_GRUPOS}
    for f in features:
        grupo = _GRUPO_POR_ID.get(f.id, _GRUPO_POR_DEFECTO)  # type: ignore[attr-defined]
        por_grupo.setdefault(grupo, []).append(_enlace_nav(f, activa))

    bloques: list[str] = []
    for grupo in _ORDEN_GRUPOS:
        enlaces = por_grupo.get(grupo) or []
        if not enlaces:
            continue
        etiqueta = escape(grupo)
        bloques.append(
            f'<div class="grupo-nav" role="group" aria-label="{etiqueta}">'
            f'<span class="grupo-nav-etiqueta">{etiqueta}</span>'
            f'{"".join(enlaces)}'
            "</div>"
        )
    # Divisor visual entre grupos (decorativo, no navegable).
    return '<span class="grupo-nav-divisor" aria-hidden="true"></span>'.join(bloques)


def render_pagina(
    *,
    features: Sequence[ItemNav],
    activa: str,
    titulo: str,
    contenido: str,
    css: Sequence[str] = (),
    js: Sequence[str] = (),
) -> str:
    """Devuelve el HTML completo de una pagina de la consola.

    - `features`: lista de features registradas (para la nav), ya ordenadas.
    - `activa`: id de la feature actual (resalta su pestana).
    - `titulo`: titulo de la pestana del navegador y encabezado interno.
    - `contenido`: HTML del `<main>` (ya escapado por la feature donde toque).
    - `css` / `js`: nombres de estaticos PROPIOS de la feature a incluir
      (ademas del CSS/JS compartido). Se sirven en `/estaticos/<nombre>`.
    """
    css_propio = _links_css(css)
    js_propio = _scripts_js(js)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)} · Consola Keni</title>
<link rel="icon" href="{_FAVICON_SVG}">
<link rel="stylesheet" href="/estaticos/consola.css">
{css_propio}
</head>
<body>
<a class="saltar" href="#contenido">Saltar al contenido</a>
<header class="barra">
{_WORDMARK}
<nav class="pestanas" aria-label="Secciones de la consola">
{_nav(features, activa)}
</nav>
</header>
<main id="contenido">
{contenido}
</main>
<script src="/estaticos/consola.js" defer></script>
{js_propio}
</body>
</html>
"""
