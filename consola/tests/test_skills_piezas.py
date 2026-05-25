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


# --------------------------------------------------------------------------- #
# derivar_titulo (helper puro)                                                #
# --------------------------------------------------------------------------- #


def test_derivar_titulo_primera_linea_no_vacia():
    assert skills.derivar_titulo("\n\n  Titular de la nota  \nresto") == "Titular de la nota"


def test_derivar_titulo_recorta_a_80_chars():
    largo = "x" * 200
    titulo = skills.derivar_titulo(largo)
    # 80 chars + el caracter de elipsis
    assert titulo.endswith("…")
    assert len(titulo) == 81


def test_derivar_titulo_sin_contenido_cae_a_borrador_con_fecha():
    titulo = skills.derivar_titulo("   \n\n  ")
    assert titulo.startswith("Borrador ")


# --------------------------------------------------------------------------- #
# Auto-guardado: generacion crea N publicaciones (una por pieza)              #
# --------------------------------------------------------------------------- #


def _listar_publicaciones(cli):
    return cli.get("/api/publicaciones").json()["publicaciones"]


def test_ejecutar_autocrea_una_publicacion_por_pieza(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "texto": "Mi nota importante\nsegunda linea",
            "redes": ["x", "instagram"],
        },
    )
    assert r.status_code == 200
    cuerpo = r.json()
    # 2 piezas => 2 publicaciones recien creadas en la respuesta.
    pubs = cuerpo["publicaciones"]
    assert len(pubs) == 2
    assert [p["red"] for p in pubs] == ["x", "instagram"]
    # Forma completa serializada (igual que en api/publicaciones).
    primera = pubs[0]
    for clave in ("id", "titulo", "marca", "marca_nombre", "red", "red_nombre",
                  "contenido", "estado", "veredicto", "origen", "imagen_url"):
        assert clave in primera
    assert primera["estado"] == "borrador"
    assert primera["veredicto"] == "listo"
    assert primera["marca"] == "unotv"
    # origen = historial_id
    assert primera["origen"] == cuerpo["historial_id"]
    assert primera["contenido"] == "Titular fuerte y al grano."
    # Titulo derivado de la 1a linea de la nota (no se paso titulo).
    assert primera["titulo"] == "Mi nota importante"
    # Persistidas de verdad: el listado las devuelve.
    assert len(_listar_publicaciones(cli)) == 2


def test_ejecutar_usa_titulo_dado_si_viene(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar",
        json={
            "skill": "copy-desde-nota",
            "marca": "unotv",
            "texto": "una nota",
            "redes": ["x"],
            "titulo": "  Mi titulo a mano  ",
        },
    )
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert pubs[0]["titulo"] == "Mi titulo a mano"


def test_ejecutar_sin_piezas_no_crea_publicaciones(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_SIN_JSON))
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "una nota"},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["piezas"] == []
    assert cuerpo["publicaciones"] == []
    assert _listar_publicaciones(cli) == []


def test_ejecutar_archivo_autocrea_publicaciones(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    r = cli.post(
        "/api/skills/ejecutar-archivo",
        data={"skill": "copy-desde-nota", "marca": "unotv", "redes": "x,instagram",
              "titulo": "Desde archivo"},
        files={"archivo": ("nota.txt", b"contenido de la nota", "text/plain")},
    )
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert len(pubs) == 2
    assert all(p["titulo"] == "Desde archivo" for p in pubs)
    assert len(_listar_publicaciones(cli)) == 2


# --------------------------------------------------------------------------- #
# Historial: listado/detalle devuelven piezas + titulo                        #
# --------------------------------------------------------------------------- #


def test_historial_listado_y_detalle_incluyen_piezas_y_titulo(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    gen = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "Una nota",
              "redes": ["x", "instagram"]},
    ).json()
    hid = gen["historial_id"]

    lista = cli.get("/api/skills/historial").json()["historial"]
    assert lista[0]["titulo"] == "Una nota"
    assert [p["red"] for p in lista[0]["piezas"]] == ["x", "instagram"]

    detalle = cli.get(f"/api/skills/historial/{hid}").json()
    assert detalle["titulo"] == "Una nota"
    assert [p["red"] for p in detalle["piezas"]] == ["x", "instagram"]


# --------------------------------------------------------------------------- #
# Recuperar historial -> publicaciones                                        #
# --------------------------------------------------------------------------- #


def test_historial_guardar_con_piezas_crea_una_por_pieza(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    gen = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "Una nota",
              "redes": ["x", "instagram"]},
    ).json()
    hid = gen["historial_id"]
    antes = len(_listar_publicaciones(cli))

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert [p["red"] for p in pubs] == ["x", "instagram"]
    assert all(p["origen"] == hid for p in pubs)
    assert all(p["estado"] == "borrador" for p in pubs)
    # Crea publicaciones NUEVAS (ademas de las auto-guardadas).
    assert len(_listar_publicaciones(cli)) == antes + 2


def test_historial_guardar_con_piezas_filtra_a_redes(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    hid = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "Una nota",
              "redes": ["x", "instagram"]},
    ).json()["historial_id"]

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"redes": ["instagram"]})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert [p["red"] for p in pubs] == ["instagram"]


def test_historial_guardar_usa_titulo_param(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner(_SALIDA_CON_JSON))
    cli = _cliente()
    hid = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": "unotv", "texto": "Una nota",
              "redes": ["x"]},
    ).json()["historial_id"]

    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"titulo": "Recuperado"})
    assert r.json()["publicaciones"][0]["titulo"] == "Recuperado"


def test_historial_guardar_sin_piezas_requiere_red(entorno):
    # Entrada antigua sin piezas: la insertamos directo via db.
    from keni_consola import db

    hid = db.registrar_historial_skill("copy-desde-nota", "unotv", "✅ texto plano")
    cli = _cliente()
    # Sin red => 400 claro.
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={})
    assert r.status_code == 400
    assert "red" in r.json()["error"].lower()


def test_historial_guardar_sin_piezas_con_red_crea_una(entorno):
    from keni_consola import db

    hid = db.registrar_historial_skill("copy-desde-nota", "unotv", "✅ contenido viejo")
    cli = _cliente()
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"red": "facebook"})
    assert r.status_code == 200
    pubs = r.json()["publicaciones"]
    assert len(pubs) == 1
    assert pubs[0]["red"] == "facebook"
    assert pubs[0]["contenido"] == "✅ contenido viejo"
    assert pubs[0]["veredicto"] == "listo"  # derivado del ✅
    assert pubs[0]["origen"] == hid


def test_historial_guardar_red_invalida_da_400(entorno):
    from keni_consola import db

    hid = db.registrar_historial_skill("copy-desde-nota", "unotv", "texto viejo")
    cli = _cliente()
    r = cli.post(f"/api/skills/historial/{hid}/guardar", json={"red": "myspace"})
    assert r.status_code == 400


def test_historial_guardar_404_si_no_existe(entorno):
    cli = _cliente()
    r = cli.post("/api/skills/historial/noexiste/guardar", json={})
    assert r.status_code == 404
