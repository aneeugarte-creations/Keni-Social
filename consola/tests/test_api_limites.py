"""Tests de la API Limites (/api/limites) y de la fuente unica de los topes.

Los limites de caracteres por red viven SOLO en `limites_plataforma`; el
endpoint los expone y `redes.py` los consume sin redefinirlos. OFFLINE, sin red.

Guard CRUZADO backend <-> frontend. La inicial `_LIMITES_BASE` de
`consola/frontend/.../meta.ts` (espejo del backend, usado antes de hidratar desde
`GET /api/limites`) debe coincidir EXACTAMENTE con `limites_plataforma.LIMITES`. Si
alguien cambia un tope en el backend y olvida la inicial del frontend, este test
FALLA (mismo estilo que el guard de marcas: parsea el `.ts` y compara, sin importar
TS). Convierte una copia que puede divergir en una referencia verificada.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from keni_consola import limites_plataforma, redes

# Raiz del monorepo: consola/tests/test_api_limites.py -> parents[2].
_REPO = Path(__file__).resolve().parents[2]
_META_TS = _REPO / "consola" / "frontend" / "src" / "pages" / "piezas" / "meta.ts"


def test_limites_endpoint_orden_y_forma(cliente):
    datos = cliente.get("/api/limites").json()
    assert "limites" in datos
    ids = [r["id"] for r in datos["limites"]]
    # mismo orden fijo que el catalogo de redes
    assert ids == ["x", "instagram", "facebook", "tiktok", "youtube"]
    por_id = {r["id"]: r for r in datos["limites"]}
    assert por_id["x"] == {"id": "x", "nombre": "X", "limite": 25000}
    assert por_id["instagram"]["limite"] == 2200
    assert por_id["facebook"]["limite"] is None
    assert por_id["tiktok"]["limite"] == 4000  # caption ampliado 2023-24
    assert por_id["youtube"]["limite"] is None


def test_redes_consume_la_fuente_unica_de_limites():
    # `redes.REDES.limite` NO se redefine: es exactamente `limites_plataforma`.
    for r in redes.REDES:
        assert r.limite == limites_plataforma.limite_de(r.id)


def test_la_fuente_de_limites_es_keni_shared_no_un_espejo():
    # `keni_consola.limites_plataforma` REEXPORTA `keni_shared`. Es la MISMA
    # tabla: un cambio en keni_shared se ve en la consola sin tocar nada.
    from keni_shared import limites_plataforma as ks_limites

    assert limites_plataforma.LIMITES is ks_limites.LIMITES


def test_tiktok_reconciliado_a_4000():
    # La divergencia (meta.ts=2200 vs plataformas.md "2200/4000") se
    # reconcilia al maximo tecnico actual: 4000.
    assert limites_plataforma.limite_de("tiktok") == 4000


def test_limite_de_red_desconocida_es_none():
    assert limites_plataforma.limite_de("threads") is None


# --------------------------------------------------------------------------- #
# Guard cruzado inicial `meta.ts` <-> `limites_plataforma.LIMITES`             #
# --------------------------------------------------------------------------- #
#
# El frontend NO puede importar `keni_consola`, asi que `meta.ts` mantiene una
# INICIAL (`_LIMITES_BASE`) que es un espejo del backend para que el limite sea
# correcto el instante anterior a la hidratacion (`GET /api/limites`). Este guard la
# ancla al backend: si divergen (alguien cambia el backend y olvida la inicial, o al
# reves), el CI lo caza. Mismo enfoque que el guard de marcas en `test_marcas.py`
# (parsea el artefacto no-Python y compara).

# Captura el cuerpo del objeto `const _LIMITES_BASE: ... = { ... };` de meta.ts.
_RE_INICIAL = re.compile(
    r"_LIMITES_BASE\s*:[^=]*=\s*\{(?P<cuerpo>.*?)\}\s*;",
    re.DOTALL,
)
# Cada entrada `id: <valor>` del cuerpo, donde el valor es un entero o `null`.
_RE_ENTRADA = re.compile(r"(?P<id>[A-Za-z_][\w-]*)\s*:\s*(?P<valor>\d+|null)\b")


def _inicial_meta_ts() -> dict[str, int | None]:
    """Parsea `_LIMITES_BASE` de meta.ts -> dict id->limite (`null` => None)."""
    texto = _META_TS.read_text(encoding="utf-8")
    bloque = _RE_INICIAL.search(texto)
    assert bloque is not None, "no se encontro _LIMITES_BASE en meta.ts"
    inicial: dict[str, int | None] = {}
    for m in _RE_ENTRADA.finditer(bloque.group("cuerpo")):
        valor = m.group("valor")
        inicial[m.group("id")] = None if valor == "null" else int(valor)
    return inicial


def test_inicial_meta_ts_coincide_con_limites_backend():
    # El frontend solo se incluye dentro del monorepo (el job de CI hace checkout de
    # todo). Si la consola se prueba aislada, no hay meta.ts que comparar.
    if not _META_TS.is_file():
        pytest.skip("frontend no presente (consola fuera del monorepo)")
    inicial = _inicial_meta_ts()
    # Coincidencia EXACTA: mismas redes y mismos topes (incluido tiktok=4000 y los None).
    assert inicial == limites_plataforma.LIMITES, (
        "la inicial _LIMITES_BASE de meta.ts divergio de limites_plataforma.LIMITES; "
        f"meta.ts={inicial} backend={limites_plataforma.LIMITES}"
    )
