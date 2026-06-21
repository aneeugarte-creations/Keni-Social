"""Guard del esquema tipado del subconjunto estable del contrato `/api/*`.

`keni_consola.esquema_api` define UNA VEZ (como `TypedDict`) las formas mas
estables del contrato y emite su JSON Schema; el frontend genera de ahi
`frontend/src/types.gen.ts` (`npm run gen:types`). Estos tests anclan los dos
extremos para que NO se desincronicen en silencio:

  - el emisor produce un esquema valido y autoconsistente, y
  - el `types.gen.ts` COMITEADO coincide con el esquema actual del backend
    (mismas interfaces, mismos campos). Si alguien cambia un `TypedDict` y olvida
    regenerar el TS, este guard FALLA.

Mismo enfoque que el guard de limites/marcas: parsea el artefacto no-Python y lo
compara contra el backend, sin importar TypeScript. OFFLINE, sin red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from keni_consola.esquema_api import MODELOS, esquema_json

# Raiz del monorepo: consola/tests/test_esquema_api.py -> parents[2].
_REPO = Path(__file__).resolve().parents[2]
_TYPES_GEN = _REPO / "consola" / "frontend" / "src" / "types.gen.ts"


# --------------------------------------------------------------------------- #
# El emisor de esquema: forma valida y autoconsistente                         #
# --------------------------------------------------------------------------- #


def test_esquema_tiene_un_def_por_modelo():
    esquema = esquema_json()
    nombres_def = set(esquema["$defs"].keys())
    nombres_modelo = {m.__name__ for m in MODELOS}
    assert nombres_def == nombres_modelo


def test_esquema_refs_resuelven_a_defs_existentes():
    """Toda `$ref` del esquema apunta a un `$def` definido (no hay refs colgantes)."""
    esquema = esquema_json()
    defs = set(esquema["$defs"].keys())
    refs = set(re.findall(r'"#/\$defs/([A-Za-z0-9_]+)"', __import__("json").dumps(esquema)))
    assert refs <= defs, f"refs sin def: {refs - defs}"


def test_campos_requeridos_y_opcionales_de_un_modelo_conocido():
    """`ErrorApi` tiene ambos campos OPCIONALES; `ResultadoEstado` todos requeridos."""
    defs = esquema_json()["$defs"]
    # ErrorApi: error/mensaje son NotRequired -> sin "required".
    assert "required" not in defs["ErrorApi"]
    assert set(defs["ErrorApi"]["properties"]) == {"error", "mensaje"}
    # ResultadoEstado: los 4 campos son requeridos.
    assert set(defs["ResultadoEstado"]["required"]) == {"estado", "nombre", "detalle", "icono"}
    # El campo `estado` es un enum (Literal) con los 3 niveles.
    assert set(defs["ResultadoEstado"]["properties"]["estado"]["enum"]) == {"ok", "aviso", "error"}


def test_limite_red_es_nullable():
    """`LimiteRed.limite` admite `null` (red sin tope tecnico): anyOf con type null."""
    defs = esquema_json()["$defs"]
    miembros = defs["LimiteRed"]["properties"]["limite"]["anyOf"]
    tipos = {m.get("type") for m in miembros}
    assert "null" in tipos and "integer" in tipos


# --------------------------------------------------------------------------- #
# Areas de churn ampliadas: piezas, runs                                #
# --------------------------------------------------------------------------- #


def test_churn_modelos_presentes():
    """Las entidades de churn y sus envelopes estan en el subconjunto generado."""
    defs = set(esquema_json()["$defs"].keys())
    esperados = {
        "Paginacion", "MetricasRun",
        "Pieza", "RespuestaPiezas", "RespuestaPieza",
    }
    assert esperados <= defs


def test_generacion_deferida_no_esta_en_el_subconjunto():
    """`Generacion` NO se genera (resultado libre, frontend la tipa rico)."""
    defs = set(esquema_json()["$defs"].keys())
    assert "Generacion" not in defs
    assert "RespuestaGeneraciones" not in defs


def test_paginacion_envelope_requerido_en_listados():
    """Los listados pesados (piezas) traen `paginacion` REQUERIDA."""
    defs = esquema_json()["$defs"]
    assert "paginacion" in defs["RespuestaPiezas"]["required"]
    assert set(defs["Paginacion"]["required"]) == {"total", "limite", "desplazamiento"}


def test_version_interno_no_aparece_en_ningun_modelo():
    """El `version` de almacenamiento es INTERNO: nunca en los dicts de la API."""
    defs = esquema_json()["$defs"]
    for nombre, esquema in defs.items():
        assert "version" not in esquema.get("properties", {}), (
            f"`{nombre}` expone `version` (campo interno, no de la API)"
        )


# --------------------------------------------------------------------------- #
# Guard cruzado: `types.gen.ts` comiteado <-> esquema actual del backend        #
# --------------------------------------------------------------------------- #
#
# El frontend NO puede importar `keni_consola`. `types.gen.ts` es el artefacto
# generado; este guard verifica que sigue al dia con el backend SIN ejecutar node
# (parsea el .ts y compara nombres de interface y de campos). Si la consola se
# prueba aislada (sin el frontend del monorepo), se salta.

# Cada bloque `export interface Nombre { ... }` del .ts generado.
_RE_INTERFACE = re.compile(
    r"export interface (?P<nombre>[A-Za-z0-9_]+)\s*\{(?P<cuerpo>[^}]*)\}",
    re.DOTALL,
)
# Cada campo `nombre[?]: tipo;` dentro del cuerpo de una interface (1er nivel).
_RE_CAMPO = re.compile(r"^\s*(?P<nombre>[A-Za-z0-9_]+)\??\s*:", re.MULTILINE)


def _interfaces_de_types_gen() -> dict[str, set[str]]:
    """Parsea `types.gen.ts` -> {NombreInterface: {campos}}."""
    texto = _TYPES_GEN.read_text(encoding="utf-8")
    out: dict[str, set[str]] = {}
    for m in _RE_INTERFACE.finditer(texto):
        campos = {c.group("nombre") for c in _RE_CAMPO.finditer(m.group("cuerpo"))}
        out[m.group("nombre")] = campos
    return out


def _campos_esperados(modelo: type) -> set[str]:
    """Campos (claves) esperados de un `TypedDict` segun el esquema generado."""
    return set(esquema_json()["$defs"][modelo.__name__]["properties"].keys())


def test_types_gen_existe_y_no_esta_vacio():
    if not _TYPES_GEN.is_file():
        pytest.skip("frontend no presente (consola fuera del monorepo)")
    assert _TYPES_GEN.stat().st_size > 0


def test_types_gen_tiene_una_interface_por_modelo():
    """Cada `TypedDict` de MODELOS tiene su `interface` en `types.gen.ts`.

    Si se anade/renombra un modelo y se olvida `npm run gen:types`, esto FALLA.
    """
    if not _TYPES_GEN.is_file():
        pytest.skip("frontend no presente (consola fuera del monorepo)")
    interfaces = _interfaces_de_types_gen()
    for modelo in MODELOS:
        assert modelo.__name__ in interfaces, (
            f"falta `export interface {modelo.__name__}` en types.gen.ts; "
            "regeneralo con `npm run gen:types`"
        )


def test_types_gen_campos_coinciden_con_el_esquema():
    """Los campos de cada interface coinciden con los del esquema del backend.

    Detecta drift a nivel de campo (campo anadido/quitado/renombrado en un
    `TypedDict` sin regenerar el TS).
    """
    if not _TYPES_GEN.is_file():
        pytest.skip("frontend no presente (consola fuera del monorepo)")
    interfaces = _interfaces_de_types_gen()
    for modelo in MODELOS:
        esperados = _campos_esperados(modelo)
        obtenidos = interfaces.get(modelo.__name__, set())
        assert obtenidos == esperados, (
            f"`{modelo.__name__}` divergio entre el backend y types.gen.ts: "
            f"backend={sorted(esperados)} ts={sorted(obtenidos)}; "
            "regeneralo con `npm run gen:types`"
        )
