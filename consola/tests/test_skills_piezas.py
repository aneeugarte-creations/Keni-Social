"""Tests del parser de piezas por red y de la generacion por red de Skills.

TODO OFFLINE: NUNCA se llama a `claude` real; el runner se mockea o se prueban
funciones puras (`parsear_salida`, `normalizar_redes`, `construir_prompt`).

Fixtures cubiertos por `parsear_salida`:
  - salida CON bloque json valido (piezas correctas)
  - salida SIN bloque json (resultado tal cual, sin piezas)
  - salida con json MALFORMADO (resultado tal cual, sin piezas)
"""

from __future__ import annotations

from keni_consola import redes
from keni_consola.api import skills

from .conftest import _cliente

# --------------------------------------------------------------------------- #
# Fixtures de salida cruda (lo que devolveria `claude`)                        #
# --------------------------------------------------------------------------- #

_SALIDA_CON_JSON = """✅ Copy listo para publicar.

## X
Titular fuerte y al grano.

## Instagram
Gancho visual + contexto.

```json
{"piezas": [{"red": "x", "texto": "Titular fuerte y al grano."},
            {"red": "instagram", "texto": "Gancho visual + contexto."}]}
```
"""

_SALIDA_SIN_JSON = """⚠️ Revisa antes de publicar.

## X
Un solo bloque de texto sin json al final.
"""

_SALIDA_JSON_MALFORMADO = """❌ No publicar.

## X
Texto.

```json
{"piezas": [{"red": "x", "texto": "falta cierre}
```
"""


# --------------------------------------------------------------------------- #
# parsear_salida: bloque json valido                                          #
# --------------------------------------------------------------------------- #


def test_parsear_con_json_valido_extrae_piezas():
    res = skills.parsear_salida(_SALIDA_CON_JSON, ["x", "instagram"])
    assert res["verdicto"] == "listo"
    piezas = res["piezas"]
    assert [p["red"] for p in piezas] == ["x", "instagram"]
    assert piezas[0]["contenido"] == "Titular fuerte y al grano."
    assert piezas[0]["caracteres"] == len("Titular fuerte y al grano.")
    # el bloque json se QUITA del resultado limpio
    assert "```json" not in res["resultado"]
    assert "piezas" not in res["resultado"]
    assert "Gancho visual" in res["resultado"]


def test_parsear_respeta_orden_fijo_de_redes():
    """Aunque el json venga en otro orden, las piezas salen en el orden pedido."""
    salida = (
        "✅ ok\n\n```json\n"
        '{"piezas": [{"red": "instagram", "texto": "ig"}, {"red": "x", "texto": "tw"}]}\n'
        "```\n"
    )
    res = skills.parsear_salida(salida, ["x", "instagram"])
    assert [p["red"] for p in res["piezas"]] == ["x", "instagram"]


def test_parsear_ignora_redes_fuera_de_las_pedidas():
    salida = (
        "✅ ok\n\n```json\n"
        '{"piezas": [{"red": "x", "texto": "tw"}, {"red": "tiktok", "texto": "tk"}]}\n'
        "```\n"
    )
    res = skills.parsear_salida(salida, ["x"])  # solo se pidio X
    assert [p["red"] for p in res["piezas"]] == ["x"]


def test_parsear_usa_el_ultimo_bloque_json():
    """Si hay varios bloques json, el de las piezas es el ULTIMO."""
    salida = (
        "```json\n{\"otro\": 1}\n```\n\n"
        "✅ ok\n\n```json\n{\"piezas\": [{\"red\": \"x\", \"texto\": \"final\"}]}\n```\n"
    )
    res = skills.parsear_salida(salida, ["x"])
    assert res["piezas"][0]["contenido"] == "final"
    # el primer bloque (no-piezas) se queda en el resultado
    assert '{"otro": 1}' in res["resultado"]


# --------------------------------------------------------------------------- #
# parsear_salida: sin bloque / json malformado                                #
# --------------------------------------------------------------------------- #


def test_parsear_sin_json_devuelve_salida_tal_cual():
    res = skills.parsear_salida(_SALIDA_SIN_JSON, ["x"])
    assert res["piezas"] == []
    assert res["verdicto"] == "revisar"
    assert res["resultado"] == _SALIDA_SIN_JSON.strip()


def test_parsear_json_malformado_no_crashea():
    res = skills.parsear_salida(_SALIDA_JSON_MALFORMADO, ["x"])
    assert res["piezas"] == []
    assert res["verdicto"] == "no_publicar"
    # con json malformado, el texto se deja TAL CUAL (incluido el bloque)
    assert "```json" in res["resultado"]


def test_parsear_verdicto_vacio_si_no_hay_simbolo():
    res = skills.parsear_salida("Sin simbolo de veredicto.\n## X\ntexto", ["x"])
    assert res["verdicto"] == ""


def test_parsear_piezas_no_lista_no_crashea():
    salida = "✅ ok\n\n```json\n{\"piezas\": \"no soy lista\"}\n```\n"
    res = skills.parsear_salida(salida, ["x"])
    assert res["piezas"] == []
    assert "```json" not in res["resultado"]  # json valido => bloque removido


# --------------------------------------------------------------------------- #
# normalizar_redes                                                            #
# --------------------------------------------------------------------------- #


def test_normalizar_redes_none_devuelve_las_cinco():
    assert skills.normalizar_redes(None) == redes.ids()
    assert len(skills.normalizar_redes(None)) == 5


def test_normalizar_redes_vacia_o_basura_devuelve_las_cinco():
    assert skills.normalizar_redes([]) == redes.ids()
    assert skills.normalizar_redes(["zzz", "nope"]) == redes.ids()


def test_normalizar_redes_filtra_y_ordena():
    # llega desordenado y con basura; sale en orden fijo y sin la basura
    assert skills.normalizar_redes(["instagram", "x", "zzz"]) == ["x", "instagram"]


def test_normalizar_redes_dedup():
    assert skills.normalizar_redes(["x", "x", "x"]) == ["x"]


# --------------------------------------------------------------------------- #
# construir_prompt: instruccion ADITIVA                                       #
# --------------------------------------------------------------------------- #


def test_prompt_sin_redes_no_anade_instruccion():
    p = skills.construir_prompt("copy-desde-nota", "unotv", "una nota")
    assert "json" not in p.lower()
    assert "una nota" in p


def test_prompt_con_redes_anade_bloque_json_y_redes():
    p = skills.construir_prompt("copy-desde-nota", "unotv", "una nota", ["x", "instagram"])
    assert "una nota" in p  # el copy base no cambia
    assert "```json" in p
    assert '"x"' in p and '"instagram"' in p


# --------------------------------------------------------------------------- #
# Endpoint /api/skills/ejecutar con runner mockeado                            #
# --------------------------------------------------------------------------- #


def _mock_runner(salida: str):
    """Devuelve un runner que ignora el prompt y devuelve `salida` fija."""

    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        return salida

    return runner


def test_endpoint_ejecutar_devuelve_piezas_y_verdicto(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    r = _cliente().post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "texto": "una nota",
            "redes": ["x", "instagram"],
        },
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["verdicto"] == "listo"
    assert [p["red"] for p in cuerpo["piezas"]] == ["x", "instagram"]
    assert cuerpo["historial_id"]
    assert "```json" not in cuerpo["resultado"]


def test_endpoint_ejecutar_sin_redes_usa_las_cinco(entorno, monkeypatch):
    capturado = {}

    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        capturado["prompt"] = prompt
        return _SALIDA_SIN_JSON

    monkeypatch.setattr(skills, "_runner", runner)
    r = _cliente().post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "una nota"},
    )
    assert r.status_code == 200
    # el prompt debe mencionar las 5 redes por nombre
    for nombre in ("X", "Instagram", "Facebook", "TikTok", "YouTube"):
        assert nombre in capturado["prompt"]
    # sin json en la salida => piezas vacias, resultado tal cual
    assert r.json()["piezas"] == []


def test_endpoint_ejecutar_archivo_redes_csv(entorno, monkeypatch):
    capturado = {}

    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        capturado["prompt"] = prompt
        return _SALIDA_CON_JSON

    monkeypatch.setattr(skills, "_runner", runner)
    r = _cliente().post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv", "redes": "x,instagram"},
        files={"archivo": ("nota.txt", b"una nota de prueba", "text/plain")},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert [p["red"] for p in cuerpo["piezas"]] == ["x", "instagram"]
    # CSV parseado: solo X e Instagram en el prompt (no las 5)
    assert "TikTok" not in capturado["prompt"]
