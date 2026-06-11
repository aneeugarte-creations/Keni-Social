"""Tests de la API Hashtags (/api/hashtags). OFFLINE: el runner se mockea, NUNCA
se llama a `claude` real.

Cubre: CRUD de grupos, validaciones (nombre/marca/hashtags), normalizacion de tags,
sugerencia con runner mock y parseo tolerante.
"""

from __future__ import annotations

from keni_consola.api import hashtags

from .conftest import _cliente, lanzador_generacion_completa

# --------------------------------------------------------------------------- #
# CRUD                                                                        #
# --------------------------------------------------------------------------- #


def test_crear_y_listar(cliente):
    r = cliente.post(
        "/api/hashtags", json={"nombre": "Deportes", "marca": "unotv", "hashtags": ["gol", "#liga"]}
    )
    assert r.status_code == 200
    grupo = r.json()["grupo"]
    assert grupo["nombre"] == "Deportes"
    assert grupo["marca"] == "unotv"
    assert grupo["marca_nombre"] == "UnoTV"
    # cada tag normalizado con # inicial
    assert grupo["hashtags"] == ["#gol", "#liga"]
    listado = cliente.get("/api/hashtags").json()["grupos"]
    assert len(listado) == 1


def test_crear_sin_marca_ok(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "Generales", "hashtags": ["#a"]})
    assert r.status_code == 200
    assert r.json()["grupo"]["marca"] == ""


def test_crear_nombre_vacio_400(cliente):
    assert cliente.post("/api/hashtags", json={"nombre": "  "}).status_code == 400


def test_crear_marca_invalida_400(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "X", "marca": "marca_falsa"})
    assert r.status_code == 400


def test_crear_hashtags_no_lista_400(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "X", "hashtags": "no soy lista"})
    assert r.status_code == 400


def test_actualizar_parcial(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "V", "hashtags": ["#a"]}).json()["grupo"]["id"]
    r = cliente.put(f"/api/hashtags/{gid}", json={"nombre": "N", "hashtags": ["#x", "#y"]})
    assert r.status_code == 200
    grupo = r.json()["grupo"]
    assert grupo["nombre"] == "N"
    assert grupo["hashtags"] == ["#x", "#y"]


def test_actualizar_404(cliente):
    assert cliente.put("/api/hashtags/noexiste", json={"nombre": "X"}).status_code == 404


def test_actualizar_sin_campos_400(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "V"}).json()["grupo"]["id"]
    assert cliente.put(f"/api/hashtags/{gid}", json={}).status_code == 400


def test_borrar(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "B"}).json()["grupo"]["id"]
    assert cliente.delete(f"/api/hashtags/{gid}").status_code == 200
    assert cliente.delete(f"/api/hashtags/{gid}").status_code == 404


# --------------------------------------------------------------------------- #
# parsear_hashtags (funcion pura, tolerante)                                  #
# --------------------------------------------------------------------------- #


def test_parsear_extrae_tags_con_almohadilla():
    out = hashtags.parsear_hashtags("Aquí van: #Gol #Liga y #Gol de nuevo")
    assert out == ["#Gol", "#Liga"]  # dedup preservando orden


def test_parsear_fallback_por_lineas():
    out = hashtags.parsear_hashtags("gol\nliga\nmundial")
    assert out == ["#gol", "#liga", "#mundial"]


def test_parsear_vacio_devuelve_lista_vacia():
    assert hashtags.parsear_hashtags("") == []
    assert hashtags.parsear_hashtags("   \n  ") == []


# --------------------------------------------------------------------------- #
# POST /api/hashtags/sugerir (runner mockeado)                                #
# --------------------------------------------------------------------------- #


def test_sugerir_con_generacion_mock(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa("#gol\n#liga\n#mundial"))
    r = cli.post(
        "/api/hashtags/sugerir", json={"texto": "resumen del partido", "marca": "unotv"}
    )
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "hashtags"
    assert gen["resultado"]["hashtags"] == ["#gol", "#liga", "#mundial"]


def test_sugerir_con_red(entorno):
    capturado = {}
    base = lanzador_generacion_completa("#x #y")

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    r = _cliente(lanzar_generacion=lanzar).post(
        "/api/hashtags/sugerir",
        json={"texto": "t", "marca": "unotv", "red": "instagram"},
    )
    assert r.status_code == 200
    assert "Instagram" in capturado["prompt"]


def test_sugerir_red_invalida_400(entorno):
    r = _cliente().post(
        "/api/hashtags/sugerir", json={"texto": "t", "marca": "unotv", "red": "myspace"}
    )
    assert r.status_code == 400


def test_sugerir_marca_invalida_400(entorno):
    r = _cliente().post("/api/hashtags/sugerir", json={"texto": "t", "marca": "marca_falsa"})
    assert r.status_code == 400


def test_sugerir_sin_texto_400(entorno):
    r = _cliente().post("/api/hashtags/sugerir", json={"marca": "unotv"})
    assert r.status_code == 400


def test_sugerir_sin_salida_devuelve_lista_vacia(entorno):
    # Salida sin nada utilizable (solo espacios) => hashtags vacios al completar.
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa("   \n   "))
    r = cli.post("/api/hashtags/sugerir", json={"texto": "t", "marca": "unotv"})
    assert r.status_code == 200
    assert r.json()["generacion"]["resultado"]["hashtags"] == []


# --------------------------------------------------------------------------- #
# El prompt de sugerencia vive en la Biblioteca (prompt/hashtags). PURO.       #
# --------------------------------------------------------------------------- #


def test_prompt_sugerencia_sale_de_la_biblioteca_y_sustituye(monkeypatch, tmp_path):
    # Store aislado y vacío => el cuerpo efectivo es la SEMILLA del paquete; las variables
    # {{RED}}, {{MARCA}} y {{TEXTO}} no pueden quedar crudas.
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    p = hashtags.construir_prompt_sugerencia("resumen del partido", "unotv", "instagram")
    for marcador in ("{{RED}}", "{{MARCA}}", "{{TEXTO}}"):
        assert marcador not in p
    assert "Instagram" in p and "unotv" in p and "resumen del partido" in p


def test_prompt_sugerencia_sin_red_usa_generico(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    p = hashtags.construir_prompt_sugerencia("texto base", "unotv")
    assert "redes sociales" in p and "{{RED}}" not in p


def test_prompt_sugerencia_editado_en_biblioteca_gana(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    from keni_consola import libtexto

    libtexto.importar_semilla()
    libtexto.guardar("prompt/hashtags", cuerpo="MIO: {{MARCA}} / {{RED}}\n{{TEXTO}}")
    p = hashtags.construir_prompt_sugerencia("cuerpo", "unotv", "tiktok")
    assert p == "MIO: unotv / TikTok\ncuerpo"


def test_prompt_sugerencia_sin_doc_ni_semilla_cae_al_fallback(monkeypatch, tmp_path):
    # Robustez ante stores sin re-seed: sin doc NI semilla, el módulo usa su respaldo.
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_TEXTO_SEMILLA", str(tmp_path / "semilla-vacia"))
    p = hashtags.construir_prompt_sugerencia("texto base", "unotv", "instagram")
    assert "Sugiere entre 8 y 15 hashtags" in p
    assert "Instagram" in p and "{{TEXTO}}" not in p and "texto base" in p
