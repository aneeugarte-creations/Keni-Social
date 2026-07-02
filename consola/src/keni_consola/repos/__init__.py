"""Capa REPOSITORIO de la Consola Keni: fachada UNICA de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del almacen concreto. Cada
`api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay debajo. La fachada
enruta cada entidad a su almacen de forma FIJA (no hay conmutador ni env var):

  - POSTGRES (`db`, via `motor_db`; ADR 0004/0006) es hoy el almacen de casi todo:
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
# repos es un BARREL AUTO-DERIVADO: la implementación vive en `_comun` + cada submódulo de
# `repos/`. La fachada NO enumera nombre a nombre: descubre lo público de cada submódulo y lo
# reexpone vía `__getattr__`/`__dir__`/`__all__`, así nunca se queda atrás cuando un submódulo
# gana una función. `repos.<algo>` / `from .. import repos` siguen funcionando igual.
# `test_facades` afirma que el barrel reexpone TODO lo público.
from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil


def _submodulos_repo() -> list[str]:
    """Rutas de módulo COMPLETAS cuya API pública reexpone este barrel: `_comun` + cada
    submódulo público de `repos/` + `db.sugerencias` (la persistencia de sugerencias vive
    en `keni_consola.db.sugerencias`; esta fachada la reexpone históricamente)."""
    nombres = ["keni_consola.repos._comun"]
    nombres += [
        f"keni_consola.repos.{m.name}"
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name)
        if not m.name.startswith("_")
    ]
    nombres.append("keni_consola.db.sugerencias")
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


def _exportaciones_de(nombre_modulo: str) -> set[str]:
    """Nombres públicos que reexpone un submódulo.

    `_comun` declara su API en `__all__` (que incluye plumbing publicado a propósito). El
    resto no tiene `__all__`: se toman los nombres públicos DEFINIDOS en el módulo (no los
    importados; vía AST), que son su API propia de persistencia."""
    mod = importlib.import_module(nombre_modulo)
    declarado = getattr(mod, "__all__", None)
    if declarado is not None:
        return set(declarado)
    arbol = ast.parse(inspect.getsource(mod))
    return {n for n in _nombres_ligados_aqui(arbol) if not n.startswith("_")}


def _mapa_exportaciones() -> dict[str, str]:
    """{nombre_público: módulo que lo define}. Primer submódulo gana ante colisión
    (orden de `_submodulos_repo`); en la práctica los nombres son disjuntos."""
    mapa: dict[str, str] = {}
    for nombre_modulo in _submodulos_repo():
        for nombre in _exportaciones_de(nombre_modulo):
            mapa.setdefault(nombre, nombre_modulo)
    return mapa


_EXPORTS = _mapa_exportaciones()

# Materializa cada nombre reexpuesto en el namespace del módulo. Los submódulos ya se
# importaron al derivar `_EXPORTS`, así que esto no añade coste de import. Bind REAL en el
# `__dict__` (no un `__getattr__` perezoso): así un reexport se comporta como el explícito
# de toda la vida —`vars(repos)` lo ve y un `monkeypatch.delattr` lo borra de verdad, sin
# que nada lo resucite—, que es lo que esperan la introspección y los tests.
for _nombre, _nombre_modulo in _EXPORTS.items():
    globals()[_nombre] = getattr(importlib.import_module(_nombre_modulo), _nombre)


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


__all__ = sorted(_EXPORTS)
