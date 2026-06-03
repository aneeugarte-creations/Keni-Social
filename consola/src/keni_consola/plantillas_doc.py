"""Plantillas de CONTENIDO como DOCUMENTOS (files-as-truth) bajo la raíz de la Biblioteca.

Rediseño Fase 4: las plantillas dejan de vivir en Postgres y pasan a ser ficheros `.md`
(frontmatter + cuerpo) bajo `biblioteca.raiz()/plantilla/`, igual que prompts y editoriales.
Así heredan lo mismo que el resto de la Biblioteca: store único, copia de seguridad y, sobre
todo, VERSIONADO git (historial/diff/rollback) vía `versionado.registrar`.

CONTRATO: este módulo expone EXACTAMENTE las mismas funciones que `repos.*_plantilla_contenido`
(mismos nombres, args y forma del dict devuelto), de modo que `api/plantillas_contenido.py` y el
frontend NO cambian: solo se cambia el backing store de Postgres a ficheros. El dict devuelto
incluye `variables` como STRING JSON (como hacía la BD) para que `_plantilla_a_dict` lo cargue.

ID: un slug `[a-z0-9-]` SIN barras (las rutas `/{plantilla_id}` no casan barras). El fichero es
`raiz()/plantilla/<slug>.md`. Saneo anti-traversal: el id es un único segmento slug.

MIGRACIÓN: `importar_de_postgres()` copia las plantillas que aún viven en la BD a ficheros, de
forma IDEMPOTENTE y NO DESTRUCTIVA (no borra filas de la BD): si algo va mal, el dato sigue en
Postgres. Cada fichero importado estampa `origen_pg: <id>` para no reimportarse.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from . import biblioteca, versionado
from .io_atomico import escribir_atomico

_log = logging.getLogger("keni_consola.plantillas_doc")

_RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SUBDIR = "plantilla"


def _dir() -> Path:
    """Dir de las plantillas (subcarpeta `plantilla/` bajo la raíz de la Biblioteca)."""
    return biblioteca.raiz() / _SUBDIR


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ruta(plantilla_id: str) -> Path | None:
    """Ruta del `.md` de un id (slug de un solo segmento). None si el id no es válido."""
    if not isinstance(plantilla_id, str):
        return None
    pid = plantilla_id.strip().strip("/")
    if not pid or "/" in pid or not _RE_SLUG.match(pid):
        return None
    base = _dir().resolve()
    destino = (base / f"{pid}.md").resolve()
    if base not in destino.parents:
        return None
    return destino


def _id_unico(slug: str) -> str:
    """Devuelve un id libre derivado de `slug`, añadiendo `-2`, `-3`… si choca."""
    base = _dir()
    candidato = slug
    n = 2
    while (base / f"{candidato}.md").exists():
        candidato = f"{slug}-{n}"
        n += 1
    return candidato


def _parsear(texto: str) -> tuple[dict[str, Any], str]:
    """Separa frontmatter YAML y cuerpo, preservando el cuerpo EXACTO (sin tocar saltos).

    El cuerpo debe round-tripear byte a byte: `aplicar` y el copy resultante dependen de que
    `{{marcadores}}` y el texto no ganen/pierdan saltos. Tolerante: sin frontmatter -> ({}, texto).
    """
    if not texto.startswith("---\n"):
        return {}, texto
    resto = texto[4:]
    cierre = resto.find("\n---\n")
    if cierre == -1:
        return {}, texto
    try:
        meta = yaml.safe_load(resto[:cierre])
    except yaml.YAMLError:
        meta = None
    cuerpo = resto[cierre + len("\n---\n") :]
    return (meta if isinstance(meta, dict) else {}), cuerpo


def _variables_norm(valor: Any) -> list[dict[str, str]]:
    """Normaliza variables a lista de `{clave, etiqueta, ejemplo}` (tolerante)."""
    if not isinstance(valor, list):
        return []
    salida: list[dict[str, str]] = []
    for v in valor:
        if isinstance(v, dict) and isinstance(v.get("clave"), str):
            salida.append({
                "clave": v["clave"],
                "etiqueta": v.get("etiqueta", "") if isinstance(v.get("etiqueta"), str) else "",
                "ejemplo": v.get("ejemplo", "") if isinstance(v.get("ejemplo"), str) else "",
            })
    return salida


def _row(plantilla_id: str, meta: dict[str, Any], cuerpo: str) -> dict[str, Any]:
    """Construye el dict (forma repos) desde frontmatter + cuerpo ya parseados."""
    modo = meta.get("modo") if meta.get("modo") in ("plano", "estructura") else "estructura"
    variables = _variables_norm(meta.get("variables"))

    def _s(clave: str) -> str:
        v = meta.get(clave)
        return v if isinstance(v, str) else ""

    return {
        "id": plantilla_id,
        "nombre": _s("nombre") or plantilla_id.replace("-", " "),
        "modo": modo,
        "tipo_nota": _s("tipo_nota"),
        "descripcion": _s("descripcion"),
        "marca": _s("marca"),
        "red": _s("red"),
        # El CUERPO es `contenido` en modo plano y `estructura` en modo estructura.
        "contenido": cuerpo if modo == "plano" else "",
        "estructura": cuerpo if modo == "estructura" else "",
        "variables": json.dumps(variables, ensure_ascii=False),
        "activo": bool(meta.get("activo", True)),
        "autor_id": _s("autor_id"),
        "autor_nombre": _s("autor_nombre"),
        "creado": _s("creado"),
        "actualizado": _s("actualizado"),
        "origen_pg": _s("origen_pg"),
    }


def _leer(ruta: Path) -> dict[str, Any] | None:
    """Lee un `.md` de plantilla como dict con la forma del repos (variables = JSON string)."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, cuerpo = _parsear(texto)
    return _row(ruta.stem, meta, cuerpo)


def _serializar(row: dict[str, Any]) -> str:
    """dict (forma repos) -> texto `.md` (frontmatter estable + cuerpo)."""
    modo = row.get("modo") or "estructura"
    cuerpo = (row.get("contenido", "") if modo == "plano" else row.get("estructura", "")) or ""
    try:
        variables = json.loads(row.get("variables") or "[]")
    except (ValueError, TypeError):
        variables = []
    meta: dict[str, Any] = {
        "nombre": row.get("nombre", ""),
        "modo": modo,
        "tipo_nota": row.get("tipo_nota", "") or "",
        "descripcion": row.get("descripcion", "") or "",
        "marca": row.get("marca", "") or "",
        "red": row.get("red", "") or "",
        "activo": bool(row.get("activo", True)),
        "autor_id": row.get("autor_id", "") or "",
        "autor_nombre": row.get("autor_nombre", "") or "",
        "variables": _variables_norm(variables),
        "creado": row.get("creado", "") or "",
        "actualizado": row.get("actualizado", "") or "",
    }
    if row.get("origen_pg"):
        meta["origen_pg"] = row["origen_pg"]
    cabecera = yaml.safe_dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    # Cuerpo VERBATIM (sin rstrip ni newline extra): debe round-tripear byte a byte.
    return f"---\n{cabecera}---\n{cuerpo}"


def _escribir(plantilla_id: str, row: dict[str, Any], *, mensaje: str, autor: dict[str, str] | None) -> None:
    ruta = _ruta(plantilla_id)
    if ruta is None:
        raise ValueError("Identificador de plantilla no válido.")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta, _serializar(row))
    versionado.registrar(ruta, mensaje, autor=autor)


# --------------------------------------------------------------------------- #
# API compatible con repos.*_plantilla_contenido                              #
# --------------------------------------------------------------------------- #


def listar_plantillas_contenido(
    *, marca: str | None = None, tipo_nota: str | None = None, solo_activas: bool = False
) -> list[dict[str, Any]]:
    """Plantillas del store, filtrables por marca / tipo_nota / solo_activas. Recientes primero."""
    base = _dir()
    if not base.is_dir():
        return []
    filas: list[dict[str, Any]] = []
    for ruta in base.glob("*.md"):
        row = _leer(ruta)
        if row is None:
            continue
        if marca and row["marca"] != marca:
            continue
        if tipo_nota and row["tipo_nota"] != tipo_nota:
            continue
        if solo_activas and not row["activo"]:
            continue
        filas.append(row)
    filas.sort(key=lambda r: (r["creado"], r["id"]), reverse=True)
    return filas


def obtener_plantilla_contenido(plantilla_id: str) -> dict[str, Any] | None:
    ruta = _ruta(plantilla_id)
    if ruta is None or not ruta.is_file():
        return None
    return _leer(ruta)


def crear_plantilla_contenido(
    *,
    nombre: str,
    modo: str = "estructura",
    tipo_nota: str = "",
    descripcion: str = "",
    marca: str = "",
    red: str = "",
    contenido: str = "",
    estructura: str = "",
    variables: str = "[]",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una plantilla-documento. Devuelve el dict (forma repos). `id` opcional (migración)."""
    autor = autor or {}
    slug = (id.strip() if id and _RE_SLUG.match(id.strip()) else biblioteca._slug(nombre))
    plantilla_id = _id_unico(slug)
    ahora = creado or _ahora_iso()
    row = {
        "id": plantilla_id,
        "nombre": nombre.strip(),
        "modo": modo if modo in ("plano", "estructura") else "estructura",
        "tipo_nota": tipo_nota,
        "descripcion": descripcion,
        "marca": marca,
        "red": red,
        "contenido": contenido,
        "estructura": estructura,
        "variables": variables,
        "activo": bool(activo),
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or autor.get("nombre", "") or "",
        "creado": ahora,
        "actualizado": actualizado or ahora,
    }
    _escribir(plantilla_id, row, mensaje=f"crear plantilla {plantilla_id}", autor=autor)
    return row


def actualizar_plantilla_contenido(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edición PARCIAL. `campos` usa las mismas claves que la BD (modo/contenido/estructura/…)."""
    actual = obtener_plantilla_contenido(plantilla_id)
    if actual is None:
        return None
    row = dict(actual)
    for clave in ("nombre", "modo", "tipo_nota", "descripcion", "marca", "red",
                  "contenido", "estructura", "variables", "activo"):
        if clave in campos:
            row[clave] = campos[clave]
    row["activo"] = bool(row["activo"])
    row["actualizado"] = _ahora_iso()
    _escribir(plantilla_id, row, mensaje=f"editar plantilla {plantilla_id}", autor=None)
    return obtener_plantilla_contenido(plantilla_id)


def borrar_plantilla_contenido(plantilla_id: str) -> bool:
    ruta = _ruta(plantilla_id)
    if ruta is None or not ruta.is_file():
        return False
    ruta.unlink(missing_ok=True)
    versionado.registrar(ruta, f"borrar plantilla {plantilla_id}")
    return True


# --------------------------------------------------------------------------- #
# Historial de versiones (git) — paridad con los documentos de la Biblioteca   #
# --------------------------------------------------------------------------- #


def _doc_id(plantilla_id: str) -> str:
    """Id de versionado: la ruta relativa de la plantilla dentro del repo de la Biblioteca."""
    return f"{_SUBDIR}/{plantilla_id}"


def historial(plantilla_id: str, *, limite: int = 50) -> list[dict[str, str]]:
    """Historial de versiones de una plantilla (recientes primero). [] si no existe/sin git."""
    if obtener_plantilla_contenido(plantilla_id) is None:
        return []
    return versionado.historial(_doc_id(plantilla_id), limite=limite)


def version(plantilla_id: str, sha: str) -> dict[str, Any] | None:
    """La plantilla tal y como estaba en la versión `sha` (forma repos). None si no existe."""
    texto = versionado.version(_doc_id(plantilla_id), sha)
    if texto is None:
        return None
    meta, cuerpo = _parsear(texto)
    return _row(plantilla_id, meta, cuerpo)


def restaurar_version(
    plantilla_id: str, sha: str, *, autor: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """Devuelve la plantilla al contenido de `sha` (commit nuevo encima; rollback no destructivo)."""
    texto = versionado.version(_doc_id(plantilla_id), sha)
    if texto is None:
        return None
    ruta = _ruta(plantilla_id)
    if ruta is None or not ruta.is_file():
        return None
    meta, cuerpo = _parsear(texto)
    row = _row(plantilla_id, meta, cuerpo)
    row["actualizado"] = _ahora_iso()
    _escribir(plantilla_id, row, mensaje=f"revertir plantilla {plantilla_id} a {sha[:8]}", autor=autor)
    return obtener_plantilla_contenido(plantilla_id)


# --------------------------------------------------------------------------- #
# Migración Postgres -> ficheros (idempotente, no destructiva)                #
# --------------------------------------------------------------------------- #


def importar_de_postgres() -> int:
    """Copia las plantillas que viven en Postgres a ficheros. Idempotente y NO destructiva.

    Lee TODAS las plantillas de la BD (`repos.listar_plantillas_contenido`) y crea un fichero
    por cada una que aún no se haya importado (marca por `origen_pg`). No borra filas de la BD:
    si la migración falla, el dato sigue en Postgres. Devuelve cuántas se importaron.
    """
    from . import repos

    try:
        filas = repos.listar_plantillas_contenido()
    except Exception:  # noqa: BLE001 -- sin BD (local/tests) no hay nada que migrar
        return 0
    if not filas:
        return 0
    ya = {r.get("origen_pg") for r in listar_plantillas_contenido() if r.get("origen_pg")}
    n = 0
    for fila in filas:
        origen = str(fila.get("id") or "")
        if not origen or origen in ya:
            continue
        try:
            nombre = fila.get("nombre", "") or "Plantilla"
            plantilla_id = _id_unico(biblioteca._slug(nombre))
            ahora = fila.get("creado", "") or _ahora_iso()
            row = {
                "id": plantilla_id,
                "nombre": nombre.strip(),
                "modo": fila.get("modo") or "estructura",
                "tipo_nota": fila.get("tipo_nota", "") or "",
                "descripcion": fila.get("descripcion", "") or "",
                "marca": fila.get("marca", "") or "",
                "red": fila.get("red", "") or "",
                "contenido": fila.get("contenido", "") or "",
                "estructura": fila.get("estructura", "") or "",
                "variables": fila.get("variables", "[]") or "[]",
                "activo": bool(fila.get("activo", True)),
                "autor_id": fila.get("autor_id", "") or "",
                "autor_nombre": fila.get("autor_nombre", "") or "",
                "creado": ahora,
                "actualizado": fila.get("actualizado", "") or ahora,
                "origen_pg": origen,  # marca de idempotencia: no se reimporta
            }
            _escribir(plantilla_id, row, mensaje=f"importar plantilla {origen}", autor=None)
            ya.add(origen)
            n += 1
        except Exception:  # noqa: BLE001 -- una plantilla corrupta no debe abortar la migración
            _log.warning("no se pudo importar la plantilla %s", origen, exc_info=True)
    return n
