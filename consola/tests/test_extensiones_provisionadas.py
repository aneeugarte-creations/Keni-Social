"""Guardia estática: toda extensión Postgres que use el esquema de la app debe estar
PROVISIONADA por el superuser en el init script, NO crearse desde el rol de la app.

POR QUÉ (regresión real, deploy roto en prod): el back conecta como `keni_app`, un rol de
MÍNIMO privilegio sin CREATE sobre la base; `CREATE EXTENSION` exige ese privilegio aun para
extensiones *trusted*. En CI el rol de pruebas es superuser, así que un
`CREATE EXTENSION ...` nuevo en el DDL/migraciones pasaba verde y luego REVENTABA el cutover
en hosted (`InsufficientPrivilege`), dejando el back caído. La extensión debe crearla el
superuser bootstrap en `deploy/postgres/initdb/10-app-role.sh`; entonces el
`CREATE EXTENSION IF NOT EXISTS` del DDL/migraciones es un no-op sin privilegio.

Esta prueba es ESTÁTICA (no toca Postgres): cruza las extensiones que el código de la app
referencia con las que el init script provisiona, y falla si alguna no está provisionada.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_RE_EXT = re.compile(
    r"CREATE\s+EXTENSION\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z0-9_]+)\"?",
    re.IGNORECASE,
)


def _raiz_repo() -> Path | None:
    """Sube desde este fichero hasta la raíz del repo (la que tiene app e init script)."""
    for base in Path(__file__).resolve().parents:
        if (base / "consola" / "src" / "keni_consola").is_dir() and (
            base / "deploy" / "postgres" / "initdb" / "10-app-role.sh"
        ).is_file():
            return base
    return None


def _extensiones(texto: str, comentario: str) -> set[str]:
    """Extensiones nombradas en `CREATE EXTENSION`, ignorando líneas de comentario."""
    encontradas: set[str] = set()
    for linea in texto.splitlines():
        if linea.lstrip().startswith(comentario):
            continue
        encontradas.update(m.lower() for m in _RE_EXT.findall(linea))
    return encontradas


def test_extensiones_de_la_app_estan_provisionadas_en_initdb():
    raiz = _raiz_repo()
    if raiz is None:
        pytest.skip("no se localiza la raíz del repo (app + init script) desde el test")

    src = raiz / "consola" / "src" / "keni_consola"
    referenciadas: set[str] = set()
    for py in src.rglob("*.py"):
        referenciadas |= _extensiones(py.read_text(encoding="utf-8"), "#")

    initdb = (raiz / "deploy" / "postgres" / "initdb" / "10-app-role.sh").read_text(encoding="utf-8")
    provisionadas = _extensiones(initdb, "--")

    faltan = referenciadas - provisionadas
    assert not faltan, (
        f"el código de la app hace CREATE EXTENSION de {sorted(faltan)} pero NO está(n) "
        "provisionada(s) por el superuser en deploy/postgres/initdb/10-app-role.sh. "
        "keni_app (rol de la app, mínimo privilegio) no puede crear extensiones: añádela(s) "
        "al init script o el deploy reventará en hosted con InsufficientPrivilege."
    )
