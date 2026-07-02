"""Contrato de FACHADA → db: la fachada `repos*` reenvía lo que `db*` acepta.

La capa `repos.py` (barrel de `repos_<dominio>.py`) es la fachada ÚNICA de persistencia:
cada `api/*.py` consume `repos.X(...)` y la fachada delega 1:1 en `db.X(...)`. Cuando una
función de `db` GANA un parámetro nuevo (una columna nueva, p. ej.) y la fachada no lo
propaga, llamar `repos.X(param_nuevo=...)` revienta con `TypeError` — la clase de deriva
fachada→db que ha roto pipelines (p. ej. `crear_audio_transcripcion` sin reenviar
`progreso_ms`). Ese fallo es de RUNTIME y solo aflora con un caller que pase el param.

Este test lo caza ESTÁTICAMENTE (solo `inspect.signature`, SIN Postgres ni red, por eso
corre en el step `contrato-fronteras`): para cada función de fachada que envuelve a una
función `db` del MISMO nombre, AFIRMA que la fachada acepta por keyword TODO parámetro que
la `db` acepta por keyword. Así `repos.X(**kwargs_válidos_para_db)` nunca explota.

Casos legítimos (la fachada transforma a propósito y deja caer un param) van al
`ALLOWLIST` con justificación; el test NO los exige.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

# Parámetros que la fachada DEJA CAER a propósito (la `db` los acepta pero la fachada no los
# expone). Clave: nombre de la función (igual en fachada y db). Valor: set de params omitidos
# adrede, cada uno con su porqué en el comentario. Hoy está VACÍO: toda deriva detectada era
# una omisión accidental y se propagó. Añade aquí SOLO transformaciones intencionales.
ALLOWLIST: dict[str, set[str]] = {
    # Ejemplo del formato (no activo):
    # "crear_algo": {"campo_interno"},  # lo fija la propia fachada, no el caller.
}

_VAR_KINDS = (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
_PASABLES_POR_KEYWORD = (
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
    inspect.Parameter.KEYWORD_ONLY,
)


def _modulos_fachada() -> list[str]:
    """`repos` (barrel) + cada submódulo público de `repos/`."""
    repos = importlib.import_module("keni_consola.repos")
    nombres = ["repos"]
    nombres += sorted(
        f"repos.{m.name}"
        for m in pkgutil.iter_modules(repos.__path__)
        if not m.name.startswith("_")
    )
    return nombres


def _acepta_por_keyword(sig: inspect.Signature) -> set[str]:
    return {
        n for n, p in sig.parameters.items() if p.kind in _PASABLES_POR_KEYWORD
    }


def _tiene_var_keyword(sig: inspect.Signature) -> bool:
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def _pares_fachada_db() -> list[tuple[str, str, object, object]]:
    """(modulo, nombre, fn_fachada, fn_db) para cada función de fachada que envuelve a una
    `db` del mismo nombre. Cada nombre se considera UNA vez (el barrel reexporta los demás)."""
    db = importlib.import_module("keni_consola.db")
    vistos: set[str] = set()
    pares: list[tuple[str, str, object, object]] = []
    for modname in _modulos_fachada():
        mod = importlib.import_module(f"keni_consola.{modname}")
        for nombre in dir(mod):
            if nombre.startswith("_") or nombre in vistos:
                continue
            fn = getattr(mod, nombre)
            if not inspect.isfunction(fn):
                continue
            db_fn = getattr(db, nombre, None)
            if not inspect.isfunction(db_fn):
                continue
            vistos.add(nombre)
            pares.append((modname, nombre, fn, db_fn))
    return pares


def test_fachada_reenvia_parametros_de_db() -> None:
    """Toda fachada `repos.X` acepta por keyword cuanto `db.X` acepta (salvo ALLOWLIST)."""
    derivas: list[str] = []
    revisadas = 0
    for modname, nombre, fn, db_fn in _pares_fachada_db():
        try:
            sig_fn = inspect.signature(fn)
            sig_db = inspect.signature(db_fn)
        except (ValueError, TypeError):
            continue
        revisadas += 1
        if _tiene_var_keyword(sig_fn):
            continue  # la fachada reenvía cualquier kwarg (**kwargs): nada que exigir.
        acepta_fachada = _acepta_por_keyword(sig_fn)
        permitidos = ALLOWLIST.get(nombre, set())
        faltan = [
            p
            for p in _acepta_por_keyword(sig_db)
            if p not in acepta_fachada and p not in permitidos
        ]
        if faltan:
            derivas.append(
                f"{modname}.{nombre}: no reenvía {sorted(faltan)} que db.{nombre} acepta"
            )

    assert revisadas, "no se halló ninguna función de fachada que envuelva a db (¿import roto?)"
    assert not derivas, (
        "Deriva fachada→db: la fachada no propaga parámetros que la función db acepta "
        "(llamar repos.X(**kwargs_de_db) reventaría con TypeError). Propaga el param en la "
        "fachada o, si la omisión es intencional, añádelo al ALLOWLIST con justificación:\n  "
        + "\n  ".join(derivas)
    )


# --------------------------------------------------------------------------- #
# Contrato BARREL ⊇ FUENTE: el barrel reexporta TODO lo público de su fuente.
# --------------------------------------------------------------------------- #
#
# Otra clase de rojo histórico: un barrel mantenido a mano (lista de imports +
# `__all__`) se queda atrás cuando la fuente gana un símbolo, y `from .repos import X`
# revienta con ImportError/AttributeError en montones de tests no relacionados. El barrel
# es AUTO-DERIVADO (delega vía `__getattr__`/`__dir__`); este test fija ese contrato: si
# una deriva futura rompiera la derivación, lo caza AQUÍ (un test) en vez de enrojecer
# pipelines ajenos.


def test_repos_barrel_reexporta_todo_lo_publico_de_los_submodulos() -> None:
    """El barrel `repos` reexpone TODA función pública de cada submódulo de `repos/` /
    `db.sugerencias` / `repos._comun`.

    Solo se exigen FUNCIONES (la API de persistencia que consumen los `api/*.py`); las
    constantes/clases entran igual por la derivación, pero las funciones son lo que rompía
    `from .repos import X`. Si el barrel se quedara atrás, lo caza aquí."""
    repos = importlib.import_module("keni_consola.repos")
    expuestos = set(dir(repos))

    repos_pkg = importlib.import_module("keni_consola.repos")
    submods = ["repos._comun"]
    submods += sorted(
        f"repos.{m.name}"
        for m in pkgutil.iter_modules(repos_pkg.__path__)
        if not m.name.startswith("_")
    )
    submods.append("db.sugerencias")

    faltan: list[str] = []
    revisadas = 0
    for modname in submods:
        mod = importlib.import_module(f"keni_consola.{modname}")
        for nombre in dir(mod):
            if nombre.startswith("_"):
                continue
            valor = getattr(mod, nombre)
            if not inspect.isfunction(valor) or valor.__module__ != mod.__name__:
                continue  # solo funciones DEFINIDAS en el submódulo (no helpers importados)
            revisadas += 1
            if nombre not in expuestos:
                faltan.append(f"{modname}.{nombre}")
            elif getattr(repos, nombre) is not valor:
                faltan.append(f"{modname}.{nombre} (reexpone otro objeto)")

    assert revisadas, "no se halló ninguna función pública en los submódulos repos (¿import roto?)"
    assert not faltan, (
        "El barrel `repos` no reexpone funciones públicas de sus submódulos: "
        f"{sorted(faltan)}. La fachada es auto-derivada; revisa `_exportaciones_de`."
    )
