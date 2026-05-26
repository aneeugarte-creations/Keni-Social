"""Tests del catalogo UNICO de marcas (#82). Solo datos puros; sin I/O ni red.

Cubre: un solo catalogo (no dos) con 5 marcas (el golf NO es marca, es un
sub-vertical editorial de Claro Sports), traduccion id canonico <-> id_metricas,
y los helpers de la frontera con metricas.

Ademas (#102): guards de NO-DIVERGENCIA que anclan a este catalogo unico las otras
fuentes de identidad de marca del monorepo (la fuente `muestra` de keni_metricas y
los artefactos de skills-copy), que keni_consola NO puede importar pero SI puede
leer porque el job de CI hace checkout de todo el monorepo e instala keni_metricas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keni_consola import marcas

# Raiz del monorepo: consola/tests/test_marcas.py -> parents[2].
_REPO = Path(__file__).resolve().parents[2]
_SKILLS = _REPO / "skills-copy"
_MARCAS_JSON = _SKILLS / ".claude" / "skills" / "breaking-express" / "marcas.json"
_FICHAS_DIR = _SKILLS / "contexto-editorial" / "marcas"


def test_catalogo_unico_sin_duplicados():
    # UN solo catalogo: cada marca aparece una vez, con id canonico unico.
    ids = marcas.ids()
    assert len(ids) == len(set(ids))
    # El orden de presentacion es estable y conocido (slug-guion como id canonico).
    # Son 5 marcas: el golf NO es marca de primer nivel.
    assert ids == [
        "unotv",
        "claro-sports",
        "nacion-gamer",
        "piso-15",
        "fundacion",
    ]


def test_opciones_son_id_canonico_y_etiqueta_humana():
    opts = dict(marcas.opciones())
    assert opts["unotv"] == "UnoTV"
    assert opts["claro-sports"] == "Claro Sports"
    assert opts["nacion-gamer"] == "Nación Gamer"  # etiqueta con acentos
    assert opts["fundacion"] == "Fundación"


def test_golf_no_es_marca():
    # El golf NO es una marca de primer nivel: es un sub-vertical editorial de
    # Claro Sports. No esta en el catalogo ni en las opciones.
    assert not marcas.es_marca("claro-sports-golf")
    ids_opciones = [mid for mid, _ in marcas.opciones()]
    assert "claro-sports-golf" not in ids_opciones
    # Helper tolerante: id desconocido cae al propio id (no rompe la UI).
    assert marcas.etiqueta_de("claro-sports-golf") == "claro-sports-golf"


def test_es_marca_distingue_id_canonico_de_id_metricas():
    # El id canonico es valido; la forma id_metricas (guion_bajo) NO lo es.
    assert marcas.es_marca("claro-sports")
    assert not marcas.es_marca("claro_sports")
    assert not marcas.es_marca("inexistente")


def test_traduccion_id_canonico_a_id_metricas():
    # La frontera con metricas: id canonico -> id_metricas (guion_bajo).
    assert marcas.id_metricas_de("claro-sports") == "claro_sports"
    assert marcas.id_metricas_de("nacion-gamer") == "nacion_gamer"
    assert marcas.id_metricas_de("piso-15") == "piso_15"
    assert marcas.id_metricas_de("unotv") == "unotv"


def test_id_metricas_cubre_toda_la_fuente_muestra():
    # Todos los ids de la fuente "muestra" de keni_metricas tienen su marca aqui.
    esperados = {
        "unotv",
        "claro_sports",
        "nacion_gamer",
        "piso_15",
        "fundacion",
    }
    assert {m.id_metricas for m in marcas.MARCAS} == esperados


def test_helpers_frontera_metricas():
    # opciones_metricas devuelve (id_metricas, etiqueta), no el id canonico.
    opts = dict(marcas.opciones_metricas())
    assert opts["claro_sports"] == "Claro Sports"
    assert "claro_sports_golf" not in opts  # golf NO es marca
    assert "claro-sports" not in opts  # nunca el id canonico en esta frontera
    # Resolucion de etiqueta y de Marca por id_metricas.
    assert marcas.etiqueta_por_id_metricas("nacion_gamer") == "Nación Gamer"
    m = marcas.marca_por_id_metricas("piso_15")
    assert m is not None
    assert m.id == "piso-15"  # devuelve la Marca, cuyo id es el canonico


def test_caidas_a_id_cuando_desconocido():
    # Helpers tolerantes: id desconocido cae al propio id (no rompen la UI).
    assert marcas.etiqueta_de("zzz") == "zzz"
    assert marcas.etiqueta_por_id_metricas("zzz") == "zzz"
    assert marcas.id_metricas_de("zzz") == "zzz"
    assert marcas.marca_de("zzz") is None
    assert marcas.marca_por_id_metricas("zzz") is None


# --------------------------------------------------------------------------- #
# #102: identidad UNICA de marca cruzando consola <-> metricas <-> skills       #
# --------------------------------------------------------------------------- #
#
# Estos guards convierten "copias independientes que pueden divergir" en
# "referencias verificadas": si alguien renombra/anade una marca en muestra.py,
# marcas.json o las fichas sin tocar el catalogo canonico, el CI lo caza.


def test_muestra_de_metricas_usa_los_mismos_id_metricas():
    # keni_metricas es dependencia de la consola en CI: se puede importar.
    from keni_metricas.fuentes.muestra import (
        IDS_CUENTAS_HERMANAS,
        IDS_METRICAS_MARCAS,
    )

    canonicos = {m.id_metricas for m in marcas.MARCAS}
    # Las marcas editoriales de la muestra son EXACTAMENTE las del catalogo unico.
    assert IDS_METRICAS_MARCAS == canonicos
    # Las cuentas hermanas de Claro Sports NO son marcas del catalogo.
    assert not (IDS_CUENTAS_HERMANAS & canonicos)


def test_marcas_json_de_skills_usa_ids_canonicos():
    if not _MARCAS_JSON.is_file():
        pytest.skip("skills-copy no presente (consola fuera del monorepo)")
    datos = json.loads(_MARCAS_JSON.read_text(encoding="utf-8"))
    bloque = datos.get("marcas", {})
    canonicos = set(marcas.ids())
    # Las claves de marcas.json son un SUBCONJUNTO de los ids canonicos (slug-guion):
    # breaking-express solo tiene tokens de diseño para algunas marcas, no inventa ids.
    assert set(bloque) <= canonicos, f"marcas.json tiene ids fuera del catalogo: {set(bloque) - canonicos}"
    # Y cada `id_metricas` declarado coincide con el del catalogo canonico.
    for mid, tokens in bloque.items():
        assert tokens.get("id_metricas") == marcas.id_metricas_de(mid), (
            f"marcas.json[{mid}].id_metricas divergente del catalogo"
        )


def test_fichas_editoriales_de_skills_cubren_el_catalogo_canonico():
    if not _FICHAS_DIR.is_dir():
        pytest.skip("skills-copy no presente (consola fuera del monorepo)")
    # Hay EXACTAMENTE una ficha por marca canonica, nombrada por su id canonico.
    nombres = {p.stem for p in _FICHAS_DIR.glob("*.md")}
    assert nombres == set(marcas.ids()), (
        f"fichas editoriales no cuadran con el catalogo: {nombres ^ set(marcas.ids())}"
    )
    # El golf NO tiene ficha propia (es un sub-vertical de Claro Sports).
    assert "claro-sports-golf" not in nombres
