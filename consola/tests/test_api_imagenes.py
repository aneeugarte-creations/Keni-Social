"""Tests de la API del Estudio de imagen (/api/imagenes). OFFLINE: nunca se toca la red.

El dominio (`estudio_imagen.generar_variante/editar/expandir`) se mockea; el lanzador de
imagen EJECUTA el callable sincronicamente (`lanzador_imagen_ejecuta`) para cubrir el
pipeline endpoint -> registro de generacion -> resultado.
"""

from __future__ import annotations

from keni_consola import media
from keni_consola.dominio import estudio_imagen

from .conftest import _cliente, lanzador_generacion_completa, lanzador_imagen_ejecuta

# --------------------------------------------------------------------------- #
# POST /api/imagenes/generar                                                  #
# --------------------------------------------------------------------------- #


def test_generar_no_configurado_400(cliente):
    r = cliente.post("/api/imagenes/generar", json={"prompt": "un estadio"})
    assert r.status_code == 400
    assert "no esta configurada" in r.json()["error"].lower() or "configurada" in r.json()["error"]


def test_generar_sin_prompt_400(cliente):
    r = cliente.post("/api/imagenes/generar", json={})
    assert r.status_code == 400


def test_generar_marca_invalida_400(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    cli = _cliente()
    r = cli.post("/api/imagenes/generar", json={"prompt": "x", "marca": "no-existe"})
    assert r.status_code == 400


def test_generar_n_variantes(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(
        estudio_imagen, "generar_variante", lambda prompt: {"id": "v.png", "url": "/api/media/v.png"}
    )
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/generar", json={"prompt": "estadio", "marca": "claro-sports", "variantes": 3})
    assert r.status_code == 200
    gens = r.json()["generaciones"]
    assert len(gens) == 3
    assert all(g["estado"] == "completado" for g in gens)
    assert gens[0]["resultado"]["url"] == "/api/media/v.png"


def test_generar_variantes_se_acota(entorno, monkeypatch):
    """variantes fuera de rango se acota a [1, 4]."""
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(estudio_imagen, "generar_variante", lambda prompt: {"id": "v.png", "url": "/x"})
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/generar", json={"prompt": "x", "variantes": 99})
    assert len(r.json()["generaciones"]) == 4


# --------------------------------------------------------------------------- #
# POST /api/imagenes/editar                                                   #
# --------------------------------------------------------------------------- #


def test_editar_op_invalida_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"imagen": "x.png", "op": "destruir"})
    assert r.status_code == 400


def test_editar_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"op": "recortar"})
    assert r.status_code == 400


def test_editar_redimensionar_sin_max_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"imagen": "x.png", "op": "redimensionar"})
    assert r.status_code == 400


def test_editar_placa_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/imagenes/editar",
        json={"op": "placa", "texto": "Gol", "marca": "piso-15", "formato": "feed"},
    )
    assert r.status_code == 400  # placa solo unotv/claro-sports


def test_editar_recortar_ok(entorno, monkeypatch):
    captado = {}

    def _fake_editar(imagen, op, params):
        captado.update(imagen=imagen, op=op, params=params)
        return {"id": "r.png", "url": "/api/media/r.png", "imagenes": [{"id": "r.png", "url": "/api/media/r.png"}]}

    monkeypatch.setattr(estudio_imagen, "editar", _fake_editar)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/editar", json={"imagen": "src.png", "op": "recortar", "formato": "cuadrado"})
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["estado"] == "completado"
    assert gen["resultado"]["id"] == "r.png"
    assert captado["op"] == "recortar"
    assert captado["params"]["formato"] == "cuadrado"


# --------------------------------------------------------------------------- #
# POST /api/imagenes/expandir                                                 #
# --------------------------------------------------------------------------- #


def test_expandir_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/expandir", json={"formato": "feed"})
    assert r.status_code == 400


def test_expandir_no_configurado_400(cliente):
    r = cliente.post("/api/imagenes/expandir", json={"imagen": "x.png"})
    assert r.status_code == 400


def test_expandir_ok(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(
        estudio_imagen, "expandir",
        lambda imagen, **kw: {"id": "e.png", "url": "/api/media/e.png", "imagenes": []},
    )
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/expandir", json={"imagen": "src.png", "formato": "feed", "strength": 0.4})
    assert r.status_code == 200
    assert r.json()["generacion"]["resultado"]["id"] == "e.png"


# --------------------------------------------------------------------------- #
# POST /api/imagenes/retocar (retoque generativo por instruccion)             #
# --------------------------------------------------------------------------- #


def test_retocar_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/retocar", json={"instruccion": "oscurece el cielo"})
    assert r.status_code == 400


def test_retocar_sin_instruccion_400(cliente):
    r = cliente.post("/api/imagenes/retocar", json={"imagen": "x.png"})
    assert r.status_code == 400


def test_retocar_no_configurado_400(cliente):
    r = cliente.post("/api/imagenes/retocar", json={"imagen": "x.png", "instruccion": "oscurece"})
    assert r.status_code == 400


def test_retocar_ok(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    captado = {}

    def _fake_retocar(imagen, instruccion, **kw):
        captado.update(imagen=imagen, instruccion=instruccion, **kw)
        return {"id": "r.png", "url": "/api/media/r.png", "imagenes": []}

    monkeypatch.setattr(estudio_imagen, "retocar", _fake_retocar)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post(
        "/api/imagenes/retocar",
        json={"imagen": "src.png", "instruccion": "oscurece el cielo", "strength": 0.6},
    )
    assert r.status_code == 200
    assert r.json()["generacion"]["resultado"]["id"] == "r.png"
    assert captado["imagen"] == "src.png"
    assert captado["instruccion"] == "oscurece el cielo"


# --------------------------------------------------------------------------- #
# POST /api/imagenes/componer (estampar la plantilla de marca, determinista)   #
# --------------------------------------------------------------------------- #


def test_componer_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/componer", json={"marca": "unotv"})
    assert r.status_code == 400


def test_componer_marca_invalida_400(cliente):
    r = cliente.post("/api/imagenes/componer", json={"imagen": "x.png", "marca": "no-existe"})
    assert r.status_code == 400


def test_componer_ok(entorno, monkeypatch):
    captado = {}

    def _fake_componer(imagen, **kw):
        captado.update(imagen=imagen, **kw)
        return {"id": "c.png", "url": "/api/media/c.png", "imagenes": [{"id": "c.png", "url": "/api/media/c.png"}]}

    monkeypatch.setattr(estudio_imagen, "componer", _fake_componer)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post(
        "/api/imagenes/componer",
        json={"imagen": "src.png", "marca": "claro-sports", "formato": "vertical", "titular": "Gol"},
    )
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["estado"] == "completado"
    assert gen["resultado"]["id"] == "c.png"
    assert captado["imagen"] == "src.png"
    assert captado["marca"] == "claro-sports"
    assert captado["formato"] == "vertical"
    assert captado["titular"] == "Gol"
    # etiqueta ausente => None (el dominio usa la etiqueta_default de la plantilla).
    assert captado["etiqueta"] is None


def test_componer_horizontal_se_pasa_tal_cual(entorno, monkeypatch):
    """El endpoint deja pasar `horizontal`; el dominio lo compone con su SPEC 16:9 propio."""
    captado = {}
    monkeypatch.setattr(
        estudio_imagen, "componer",
        lambda imagen, **kw: captado.update(**kw) or {"id": "c.png", "url": "/x", "imagenes": []},
    )
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/componer", json={"imagen": "s.png", "marca": "unotv", "formato": "horizontal"})
    assert r.status_code == 200
    assert captado["formato"] == "horizontal"


# --------------------------------------------------------------------------- #
# POST /api/imagenes/revisar (gate humano: job claude que VE la imagen)        #
# --------------------------------------------------------------------------- #

# Checklist canned que devolveria la revision legal/editorial.
_SALIDA_REVISION = """Revisión de la imagen `imagen.png`:

✅ Bandera de México: no aparece la bandera con escudo.
⚠️ Menores: hay una persona que podría ser menor; confírmalo.
❌ Marca de agua de terceros visible en la esquina inferior.

La decisión de publicar es del humano.
"""


def test_revisar_sin_imagen_400(cliente):
    assert cliente.post("/api/imagenes/revisar", json={}).status_code == 400
    assert cliente.post("/api/imagenes/revisar", json={"imagen": "  "}).status_code == 400


def test_revisar_marca_invalida_400(cliente):
    r = cliente.post("/api/imagenes/revisar", json={"imagen": "x.png", "marca": "no-existe"})
    assert r.status_code == 400


def test_revisar_imagen_inexistente_400(entorno, monkeypatch):
    # `media.leer_media` devuelve None -> el dominio lanza EstudioError -> 400 sin traceback.
    monkeypatch.setattr(media, "leer_media", lambda _n: None)
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_REVISION))
    r = cli.post("/api/imagenes/revisar", json={"imagen": "fantasma.png"})
    assert r.status_code == 400


def test_revisar_ok_completa_con_checklist(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda _n: b"\x89PNG\r\n\x1a\n datos")
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_REVISION))
    r = cli.post("/api/imagenes/revisar", json={"imagen": "src.png", "marca": "unotv"})
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["estado"] == "completado"
    assert gen["tipo"] == "qa-editorial"
    # El checklist viaja como texto en vivo en `salida` (lo que sondea el frontend).
    assert "✅" in gen["salida"] and "❌" in gen["salida"]


def test_revisar_inyecta_reglas_e_imagen_en_prompt(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda _n: b"\x89PNG bytes")
    capturado = {}
    base = lanzador_generacion_completa(_SALIDA_REVISION)

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        capturado["dir_temporal"] = dir_temporal
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    cli = _cliente(lanzar_generacion=lanzar)
    r = cli.post("/api/imagenes/revisar", json={"imagen": "src.png"})
    assert r.status_code == 200
    # El prompt referencia el archivo adjunto y pide el checklist; la imagen va por --add-dir.
    assert "imagen.png" in capturado["prompt"]
    assert "✅" in capturado["prompt"] and "❌" in capturado["prompt"]
    assert capturado["dir_temporal"] is not None
