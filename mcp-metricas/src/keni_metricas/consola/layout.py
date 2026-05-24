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


def _nav(features: Sequence[ItemNav], activa: str) -> str:
    """Barra de pestanas a partir de las features registradas (ya ordenadas)."""
    enlaces = []
    for f in features:
        clase = ' class="activa"' if f.id == activa else ""  # type: ignore[attr-defined]
        href = escape(f"/{f.id}")  # type: ignore[attr-defined]
        etiqueta = escape(f.etiqueta)  # type: ignore[attr-defined]
        descripcion = escape(getattr(f, "descripcion", "") or "")
        aria = ' aria-current="page"' if f.id == activa else ""  # type: ignore[attr-defined]
        titulo = f' title="{descripcion}"' if descripcion else ""
        enlaces.append(f'<a href="{href}"{clase}{aria}{titulo}>{etiqueta}</a>')
    return "\n".join(enlaces)


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
<title>{escape(titulo)} - Consola Keni</title>
<link rel="stylesheet" href="/estaticos/consola.css">
{css_propio}
</head>
<body>
<a class="saltar" href="#contenido">Saltar al contenido</a>
<header class="barra">
<div class="marca-keni">KENI AI <span class="sub">Consola</span></div>
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
