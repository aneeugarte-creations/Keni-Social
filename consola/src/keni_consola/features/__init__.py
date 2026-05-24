"""Contrato de FEATURES de la Consola Keni + auto-descubrimiento.

================================================================================
PARA QUIEN ANADE UNA FEATURE NUEVA (leeme entero, esto es el contrato)
================================================================================

Una "feature" es una pestana de la consola (Proyectos, Metricas, ...). Anadir
una pestana = crear UN archivo `consola/features/<lo_que_sea>.py` que exporta una
variable de modulo llamada exactamente `FEATURE`. NO se toca `app.py`, ni el
CSS/JS compartido, ni la barra de navegacion: `app.py` descubre tu modulo solo
(con `pkgutil.iter_modules` sobre este paquete), lee tu `FEATURE`, ordena la nav
por `orden`, y monta tus rutas y tus estaticos.

REGLAS PARA NO CHOCAR CON OTROS AGENTES (importante, varios trabajan en paralelo):
  - Tu `id` debe ser UNICO (en minusculas, sin espacios: `^[a-z0-9-]+$`).
  - Tus rutas deben vivir bajo `/<id>` o `/<id>/...` (o `/api/<id>/...`). No
    pises `/` (raiz), `/estaticos/...`, ni rutas de otra feature.
  - Tus estaticos propios se sirven en `/estaticos/<nombre>`; usa nombres
    prefijados con tu id (p.ej. `tareas.css`, `tareas.js`) para no colisionar
    con `consola.css`/`consola.js` ni con los de otra feature.
  - NO importes ni edites otros modulos de feature; comparte logica via helpers
    del paquete `consola` (p.ej. `consola.proyectos`, `consola.lanzador`).

--------------------------------------------------------------------------------
QUE EXPORTA TU MODULO
--------------------------------------------------------------------------------

    # consola/features/tareas.py
    from __future__ import annotations
    from pathlib import Path
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, Response
    from starlette.routing import Route

    from .. import layout
    from . import Feature, RecursoEstatico, features_ordenadas

    _ESTATICOS = Path(__file__).parent.parent / "estaticos"

    async def _pagina(request: Request) -> Response:
        cuerpo = "<h1>Tareas</h1><p class='intro'>Tus tareas.</p>"
        return HTMLResponse(layout.render_pagina(
            features=features_ordenadas(),   # nav completa (todas las pestanas)
            activa=FEATURE.id,
            titulo=FEATURE.etiqueta,
            contenido=cuerpo,
            css=FEATURE.css,                 # tu CSS propio (opcional)
            js=FEATURE.js,                   # tu JS propio (opcional)
        ))

    FEATURE = Feature(
        id="tareas",
        etiqueta="Tareas",
        orden=30,
        descripcion="Lista de tareas pendientes del equipo.",
        rutas=[Route("/tareas", _pagina)],
        # Opcional: CSS/JS propios, servidos por la consola en /estaticos/<nombre>.
        estaticos=[
            RecursoEstatico("tareas.css", _ESTATICOS / "tareas.css", "text/css; charset=utf-8"),
            RecursoEstatico("tareas.js", _ESTATICOS / "tareas.js", "application/javascript; charset=utf-8"),
        ],
        css=["tareas.css"],
        js=["tareas.js"],
    )

CAMPOS DE `Feature`:
  - id          str   identificador unico; va en la URL (`/<id>`) y para tus
                      estaticos. Solo `[a-z0-9-]`.
  - etiqueta    str   texto visible de la pestana en la nav.
  - orden       int   ordena la nav de menor a mayor (Proyectos=10, Metricas=20).
  - rutas       lista de `starlette.routing.Route` ya con sus paths definitivos
                      (bajo `/<id>`, `/<id>/...` o `/api/<id>/...`).
  - descripcion str   (opcional) una linea de que hace; se usa como `title` de la
                      pestana y para estados vacios. Escribela para no tecnicos.
  - estaticos   lista de `RecursoEstatico` (opcional): archivos CSS/JS PROPIOS que
                      la consola servira en `/estaticos/<nombre>`.
  - css         lista de nombres de estatico a incluir como <link> en tu <head>.
  - js          lista de nombres de estatico a incluir como <script defer>.

RENDER: usa `consola.layout.render_pagina(...)` para envolver tu contenido con el
branding, la nav y los landmarks (header/nav/main). NO escribas el <head> a mano.

ESTATICOS COMPARTIDOS: `consola.css` y `consola.js` los incluye SIEMPRE el layout;
no los declares en `estaticos`. Tus reglas CSS deben vivir en tu propio archivo.

================================================================================
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from starlette.routing import Route


@dataclass(frozen=True)
class RecursoEstatico:
    """Un archivo estatico PROPIO de una feature, servido en `/estaticos/<nombre>`.

    `nombre`: nombre publico (p.ej. `tareas.css`). Prefijalo con tu id.
    `ruta`:   ruta absoluta al archivo en disco.
    `media_type`: Content-Type a devolver (incluye `; charset=utf-8`).
    """

    nombre: str
    ruta: Path
    media_type: str


@dataclass(frozen=True)
class Feature:
    """Una pestana de la consola. Ver el docstring del modulo para el contrato."""

    id: str
    etiqueta: str
    orden: int
    rutas: Sequence[Route]
    descripcion: str = ""
    estaticos: Sequence[RecursoEstatico] = field(default_factory=tuple)
    css: Sequence[str] = field(default_factory=tuple)
    js: Sequence[str] = field(default_factory=tuple)


# Cache del descubrimiento (modulos solo se importan una vez). `crear_app` lo
# reusa; los tests pueden forzar un redescubrimiento con `descubrir(refresco=True)`.
_cache: list[Feature] | None = None


def _validar(feature: object, modulo: str) -> Feature:
    """Comprueba que un `FEATURE` cumple el contrato; error claro si no."""
    if not isinstance(feature, Feature):
        raise TypeError(
            f"El modulo de feature '{modulo}' debe exportar FEATURE como instancia de "
            f"Feature (encontrado: {type(feature).__name__})."
        )
    if not feature.id or not all(c.islower() or c.isdigit() or c == "-" for c in feature.id):
        raise ValueError(
            f"La feature '{modulo}' tiene un id invalido ({feature.id!r}): usa solo [a-z0-9-]."
        )
    return feature


def descubrir(refresco: bool = False) -> list[Feature]:
    """Auto-descubre todos los modulos de `consola/features/` y devuelve sus
    `FEATURE`, ordenados por `orden` (y por `id` para empate, determinista).

    Cada submodulo de este paquete que exporte una variable `FEATURE` cuenta. Los
    modulos sin `FEATURE` (helpers) se ignoran. Ids duplicados -> error claro.
    """
    global _cache
    if _cache is not None and not refresco:
        return _cache

    encontradas: list[Feature] = []
    vistos: set[str] = set()
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        modulo = importlib.import_module(f"{__name__}.{info.name}")
        feature = getattr(modulo, "FEATURE", None)
        if feature is None:
            continue  # submodulo helper, no es una feature
        feature = _validar(feature, info.name)
        if feature.id in vistos:
            raise ValueError(
                f"Id de feature duplicado: {feature.id!r} (modulo '{info.name}'). "
                "Cada feature debe tener un id unico."
            )
        vistos.add(feature.id)
        encontradas.append(feature)

    encontradas.sort(key=lambda f: (f.orden, f.id))
    _cache = encontradas
    return _cache


def features_ordenadas() -> list[Feature]:
    """Atajo para la nav: las features ya descubiertas y ordenadas."""
    return descubrir()
