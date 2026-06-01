"""Tests de la API del Termometro mundial (/api/termometro/*). OFFLINE: nunca se llama a claude.

Cubre:
  - GET config: defectos + si la skill esta instalada + marcas + regiones sugeridas.
  - PUT config: guarda y valida (numero 5-8, hora HH:MM, marca del catalogo).
  - POST generar: con la skill sembrada y el lanzador mockeado, completa la generacion
    (salida documento: registra historial, sin auto-crear publicaciones); valida marca,
    noticias y skill ausente.
"""

from __future__ import annotations

import os
from pathlib import Path

from .conftest import _cliente, lanzador_generacion_completa, sembrar_skills

# Skill del termometro sembrada en el catalogo FALSO (salida documento, sin redes).
_SKILL_TERMOMETRO = {
    "termometro-mundial": {
        "md": "# termometro-mundial\n\nArma el termometro. Carga contexto-editorial/.\n",
        "meta": {
            "nombre": "Termómetro mundial",
            "explicacion": "Galería diaria con las 5–8 internacionales más importantes.",
            "grupo": "experimentales",
            "aplica_redes": False,
            "salida": "documento",
            "media": False,
            "orden": 46,
            "campos": [
                {"id": "noticias", "etiqueta": "Noticias", "tipo": "textarea", "requerido": True,
                 "placeholder": "", "ayuda": "", "opciones": [], "media_tipos": ""},
                {"id": "numero", "etiqueta": "Número", "tipo": "select", "requerido": False,
                 "placeholder": "", "ayuda": "", "opciones": ["5", "6", "7", "8"], "media_tipos": ""},
                {"id": "regiones", "etiqueta": "Regiones", "tipo": "texto", "requerido": False,
                 "placeholder": "", "ayuda": "", "opciones": [], "media_tipos": ""},
                {"id": "fecha", "etiqueta": "Fecha", "tipo": "fecha", "requerido": False,
                 "placeholder": "", "ayuda": "", "opciones": [], "media_tipos": ""},
            ],
            "plantilla_invocacion": (
                "usa termometro-mundial, marca {marca}.\nFecha: {fecha}\nNúmero: {numero}\n"
                "Regiones: {regiones}\nNoticias:\n{noticias}\n"
            ),
        },
    },
}

# Salida canned de la skill (documento con veredicto). Sin red, sin claude real.
_SALIDA_DOC = """✅ Termómetro listo.

PORTADA
Termómetro mundial · 2026-05-25

SLIDES
2/5. [Europa] Algo pasó en Europa.
"""


def _sembrar_termometro() -> None:
    """Anade la skill termometro-mundial al catalogo FALSO ya sembrado por `entorno`."""
    sembrar_skills(Path(os.environ["KENI_SKILLS_DIR"]), _SKILL_TERMOMETRO)


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


def test_skill_disponible_true_si_sembrada(entorno):
    _sembrar_termometro()
    cli = _cliente()
    assert cli.get("/api/termometro").json()["skill_disponible"] is True


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
    _sembrar_termometro()
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


def test_generar_inyecta_noticias_y_numero_en_el_prompt(entorno):
    _sembrar_termometro()
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
    _sembrar_termometro()
    cli = _cliente()
    r = cli.post("/api/termometro/generar", json={"marca": "marca_falsa", "noticias": "algo"})
    assert r.status_code == 400


def test_generar_sin_noticias_400(entorno):
    _sembrar_termometro()
    cli = _cliente()
    assert cli.post("/api/termometro/generar", json={"marca": "unotv"}).status_code == 400
    assert cli.post("/api/termometro/generar", json={"marca": "unotv", "noticias": "  "}).status_code == 400


def test_generar_funciona_sin_sembrar_skill(cliente):
    # El prompt del termometro viaja en la semilla del paquete: la generacion se arma sin
    # necesidad de un catalogo de skills (que ya no existe).
    r = cliente.post("/api/termometro/generar", json={"marca": "unotv", "noticias": "algo"})
    assert r.status_code == 200
