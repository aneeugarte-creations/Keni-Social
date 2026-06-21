"""Capa REPOSITORIO de la Consola Keni: fachada UNICA de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del almacen concreto. Cada
`api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay debajo. La fachada
enruta cada entidad a su almacen de forma FIJA (no hay conmutador ni env var):

  - POSTGRES (`db.py`, via `motor_db`; ADR 0004/0006) es hoy el almacen de casi todo:
    piezas y plantillas (editoriales), `comercial` (piezas + serie temporal de
    snapshots), `rota`, `usuarios`/`sesiones` (via `auth/`), la cola de `jobs`, y las
    entidades que cerraron su rezago file->pg (ADR 0006): `fuentes_rss` + items vistos +
    salud y `franjas` editoriales.
  - FICHEROS (`ficheros.py`) ya solo respaldan el HISTORIAL DE PROMPTS (file-backed bajo
    `KENI_DATA_DIR`). Todo lo demas migro a Postgres.

Las firmas publicas son ESTABLES: ningun `api/*.py` cambia aunque cambie el almacen.

Uso en las features:

    from .. import repos

    repos.crear_pieza(marca="unotv", red="x", titulo="Hola")  # -> Postgres
    repos.registrar_historial_prompt(prompt_id, marca, resultado)   # -> ficheros
"""
# repos.py es un BARREL AUTO-DERIVADO: la implementación vive en `_repos_comun` +
# `repos_<dominio>`. La fachada NO enumera nombre a nombre: descubre lo público de cada
# submódulo y lo reexpone vía `__getattr__`/`__dir__`/`__all__`, así nunca se queda atrás
# cuando un submódulo gana una función. `repos.<algo>` / `from .repos import X` siguen
# funcionando igual. `test_facades` afirma que el barrel reexpone TODO lo público.
from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil

import keni_consola


def _submodulos_repo() -> list[str]:
    """`_repos_comun` + cada `repos_<dominio>` + `db_sugerencias` del paquete. Son los
    módulos cuya API pública reexpone este barrel."""
    nombres = ["_repos_comun"]
    nombres += sorted(
        m.name
        for m in pkgutil.iter_modules(keni_consola.__path__)
        if m.name.startswith("repos_") or m.name == "db_sugerencias"
    )
    return nombres


def _nombres_ligados_aqui(arbol: ast.Module) -> set[str]:
    """Nombres que el módulo DEFINE en su top-level (def/class/asignación), NO los que
    IMPORTA. Así separamos la API propia del submódulo (`crear_pieza`, `JOB_PENDIENTE`…)
    de sus dependencias de implementación (`db`, `Any`, `datetime`, `ahora_iso`…), que
    entran por `import` y no deben reexponerse."""
    ligados: set[str] = set()
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ligados.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            for destino in nodo.targets:
                if isinstance(destino, ast.Name):
                    ligados.add(destino.id)
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            if nodo.value is not None:
                ligados.add(nodo.target.id)
    return ligados


def _exportaciones_de(modname: str) -> set[str]:
    """Nombres públicos que reexpone un submódulo.

    `_repos_comun` declara su API en `__all__` (que incluye plumbing publicado a
    propósito). El resto no tiene `__all__`: se toman los nombres públicos DEFINIDOS en el
    módulo (no los importados; vía AST), que son su API propia de persistencia."""
    mod = importlib.import_module(f"keni_consola.{modname}")
    declarado = getattr(mod, "__all__", None)
    if declarado is not None:
        return set(declarado)
    arbol = ast.parse(inspect.getsource(mod))
    return {n for n in _nombres_ligados_aqui(arbol) if not n.startswith("_")}


def _mapa_exportaciones() -> dict[str, str]:
    """{nombre_público: submódulo que lo define}. Primer submódulo gana ante colisión
    (orden de `_submodulos_repo`); en la práctica los nombres son disjuntos."""
    mapa: dict[str, str] = {}
    for modname in _submodulos_repo():
        for nombre in _exportaciones_de(modname):
            mapa.setdefault(nombre, modname)
    return mapa


_EXPORTS = _mapa_exportaciones()


def __getattr__(name: str):  # PEP 562
    modname = _EXPORTS.get(name)
    if modname is not None:
        return getattr(importlib.import_module(f"keni_consola.{modname}"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


__all__ = sorted(_EXPORTS)
