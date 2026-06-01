"""Tests de la API del Termometro mundial (/api/termometro/*). OFFLINE: nunca se llama a claude.

Cubre:
  - GET config: defectos + disponibilidad del prompt (semilla) + marcas + regiones sugeridas.
  - PUT config: guarda y valida (numero 5-8, hora HH:MM, marca del catalogo).
  - POST generar: con el lanzador mockeado, completa la generacion (salida documento:
    registra historial, sin auto-crear publicaciones); valida marca y noticias.
"""

from __future__ import annotations

from .conftest import _cliente, lanzador_generacion_completa

# Salida canned (documento con veredicto). Sin red, sin claude real.
_SALIDA_DOC = """✅ Termómetro listo.

PORTADA
Termómetro mundial · 2026-05-25

SLIDES
2/5. [Europa] Algo pasó en Europa.
"""


# --------------------------------------------------------------------------- #
# GET /api/termometro                                                          #
# --------------------------------------------------------------------------- #


def test_config_por_defecto(cliente):
    datos = cliente.get("/api/termometro").json()
    assert datos["config"] == {"numero": 8, "regiones": "", "hora": "07:00", "marca": ""}
    # El prompt del termometro viaja en la semilla del paquete: siempre disponible.
    assert datos["skill_disponible"] is True
    assert {"id": "unotv", "nombre": "UnoTV"} in datos["marcas"]
    assert "Europa" in datos["regiones_sugeridas"]
    # Sin generaciones previas no hay resultado persistente.
    assert datos["ultimo"] is None


# --------------------------------------------------------------------------- #
# PUT /api/termometro/config                                                   #
# --------------------------------------------------------------------------- #


def test_guardar_config_persiste(cliente):
    r = cliente.put(
        "/api/termometro/config",
        json={"numero": 6, "regiones": "Asia, Europa", "hora": "06:30", "marca": "claro-sports"},
    )
    assert r.status_code == 200
    assert r.json()["config"] == {
        "numero": 6, "regiones": "Asia, Europa", "hora": "06:30", "marca": "claro-sports",
    }
    # Persiste entre peticiones.
    assert cliente.get("/api/termometro").json()["config"]["numero"] == 6


def test_guardar_config_parcial(cliente):
    cliente.put("/api/termometro/config", json={"numero": 7})
    datos = cliente.get("/api/termometro").json()["config"]
    assert datos["numero"] == 7
    assert datos["hora"] == "07:00"  # intacto


def test_guardar_config_numero_fuera_de_rango_400(cliente):
    assert cliente.put("/api/termometro/config", json={"numero": 4}).status_code == 400
    assert cliente.put("/api/termometro/config", json={"numero": 9}).status_code == 400


def test_guardar_config_hora_invalida_400(cliente):
    assert cliente.put("/api/termometro/config", json={"hora": "25:00"}).status_code == 400
    assert cliente.put("/api/termometro/config", json={"hora": "mañana"}).status_code == 400


def test_guardar_config_marca_invalida_400(cliente):
    assert cliente.put("/api/termometro/config", json={"marca": "marca_falsa"}).status_code == 400


# --------------------------------------------------------------------------- #
# POST /api/termometro/generar                                                 #
# --------------------------------------------------------------------------- #


def test_generar_completa_y_registra_historial(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_DOC))
    r = cli.post(
        "/api/termometro/generar",
        json={"marca": "unotv", "noticias": "China: algo grande.\nEuropa: otra cosa.", "numero": "5"},
    )
    assert r.status_code == 200
    res = r.json()["generacion"]["resultado"]
    # Salida documento: hay `documento`, sin publicaciones auto-creadas.
    assert "documento" in res
    assert res["verdicto"] == "listo"
    assert res["publicaciones"] == []
    # Se registro en el historial (descubrible desde "Generar copy").
    historial = cli.get("/api/skills/historial").json()["historial"]
    assert any(h["skill"] == "termometro-mundial" for h in historial)


def test_get_devuelve_ultimo_termometro_persistente(entorno):
    # El resultado del termometro es PERSISTENTE: tras generar, GET /api/termometro lo
    # devuelve en `ultimo` (la pagina lo repinta al navegar/recargar sin estado de cliente).
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_DOC))
    cli.post(
        "/api/termometro/generar",
        json={"marca": "unotv", "noticias": "China: algo grande.", "numero": "5"},
    )
    ultimo = cli.get("/api/termometro").json()["ultimo"]
    assert ultimo is not None
    assert ultimo["historial_id"]
    assert "Termómetro mundial" in ultimo["documento"]
    assert ultimo["marca"] == "unotv"
    # Nota: que `ultimo` apunte al MÁS RECIENTE es responsabilidad del orden
    # "recientes primero" de `listar_historial_skills` (cubierto en su módulo); aquí no se
    # reasevera con dos generaciones porque `fecha_creacion` tiene resolución de segundos y
    # ambas caerían en el mismo segundo (empate de orden no determinista).


def test_generar_inyecta_noticias_y_numero_en_el_prompt(entorno):
    capturado = {}
    base = lanzador_generacion_completa(_SALIDA_DOC)

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    cli = _cliente(lanzar_generacion=lanzar)
    cli.post(
        "/api/termometro/generar",
        json={"marca": "unotv", "noticias": "Japón: terremoto.", "numero": "6", "regiones": "Asia"},
    )
    # El prompt autocontenido del termometro (semilla) + las noticias/parametros inyectados.
    assert "Termómetro" in capturado["prompt"]
    assert "Japón: terremoto." in capturado["prompt"]
    assert "6" in capturado["prompt"] and "Asia" in capturado["prompt"]


def test_generar_marca_invalida_400(entorno):
    cli = _cliente()
    r = cli.post("/api/termometro/generar", json={"marca": "marca_falsa", "noticias": "algo"})
    assert r.status_code == 400


def test_generar_sin_noticias_400(entorno):
    cli = _cliente()
    assert cli.post("/api/termometro/generar", json={"marca": "unotv"}).status_code == 400
    assert cli.post("/api/termometro/generar", json={"marca": "unotv", "noticias": "  "}).status_code == 400


def test_generar_funciona_sin_sembrar_skill(cliente):
    # El prompt del termometro viaja en la semilla del paquete: la generacion se arma sin
    # necesidad de un catalogo de skills (que ya no existe).
    r = cliente.post("/api/termometro/generar", json={"marca": "unotv", "noticias": "algo"})
    assert r.status_code == 200
