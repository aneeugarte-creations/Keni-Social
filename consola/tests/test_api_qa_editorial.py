"""Tests de la API de QA editorial (/api/qa-editorial/*). OFFLINE: nunca se llama a claude.

Ficha F3 (#143). NUEVO MODO: revisar el copy YA escrito por el community manager y devolver
un INFORME (veredicto 🟢/🟡/🔴 + hallazgos clasificados con corrección sugerida). SEÑALA; no
publica ni reescribe. Cubre:

  - GET opciones: marcas + plataformas + si la skill esta instalada.
  - POST revisar: con la skill sembrada y el lanzador mockeado, completa la generacion,
    parsea el bloque ```json de hallazgos y registra el historial SIN auto-crear publicaciones;
    valida marca, texto vacio y skill ausente; el prompt inyecta texto/plataforma/contexto.
  - parsear_informe (unidad): JSON valido, degradacion sin JSON, semaforo, no_verificable.
"""

from __future__ import annotations

import os
from pathlib import Path

from keni_consola.api import qa_editorial

from .conftest import _cliente, lanzador_generacion_completa, sembrar_skills

# Skill de QA sembrada en el catalogo FALSO (salida documento, sin redes).
_SKILL_QA = {
    "qa-editorial": {
        "md": "# qa-editorial\n\nRevisa el copy ajeno. Carga contexto-editorial/reglas-legales.md.\n",
        "meta": {
            "nombre": "QA editorial",
            "explicacion": "Revisa el copy del community y señala typos/datos/legal/voz.",
            "grupo": "validadas",
            "aplica_redes": False,
            "salida": "documento",
            "media": False,
            "orden": 35,
            "campos": [
                {"id": "texto", "etiqueta": "Copy a revisar", "tipo": "textarea", "requerido": True,
                 "placeholder": "", "ayuda": "", "opciones": [], "media_tipos": ""},
                {"id": "plataforma", "etiqueta": "Plataforma", "tipo": "select", "requerido": False,
                 "placeholder": "", "ayuda": "", "opciones": ["X / Twitter", "Instagram"], "media_tipos": ""},
                {"id": "contexto", "etiqueta": "Contexto", "tipo": "textarea", "requerido": False,
                 "placeholder": "", "ayuda": "", "opciones": [], "media_tipos": ""},
            ],
            "plantilla_invocacion": (
                "usa qa-editorial, marca {marca}.\nPlataforma: {plataforma}\n"
                "Contexto:\n{contexto}\nCopy a revisar:\n{texto}\n"
            ),
        },
    },
}

# Salida canned de la skill: informe con veredicto 🟡 + un bloque json de hallazgos.
_SALIDA_INFORME = """🟡 REVISAR ANTES DE PUBLICAR
🟢 LISTO PARA APROBAR · 🟡 REVISAR ANTES DE PUBLICAR · 🔴 NO PUBLICAR

Leyenda: 🟢 sin problemas · 🟡 revísalo tú · 🔴 no publicar

Hallazgos:
- Ortografía: "Mexcio" debería ser "México".

```json
{
  "veredicto": "🟡",
  "resumen": "Un typo y un dato sin fuente.",
  "hallazgos": [
    {"tipo": "ortografia", "gravedad": "aviso", "fragmento": "Mexcio",
     "explicacion": "Está mal escrito.", "sugerencia": "México", "no_verificable": false},
    {"tipo": "dato", "gravedad": "aviso", "fragmento": "ganó 3-0",
     "explicacion": "No hay fuente para el marcador.", "sugerencia": "Confirma el marcador con la fuente.",
     "no_verificable": true}
  ]
}
```
"""


def _sembrar_qa() -> None:
    """Anade la skill qa-editorial al catalogo FALSO ya sembrado por `entorno`."""
    sembrar_skills(Path(os.environ["KENI_SKILLS_DIR"]), _SKILL_QA)


# --------------------------------------------------------------------------- #
# GET /api/qa-editorial                                                        #
# --------------------------------------------------------------------------- #


def test_opciones_por_defecto(cliente):
    datos = cliente.get("/api/qa-editorial").json()
    assert {"id": "unotv", "nombre": "UnoTV"} in datos["marcas"]
    assert "Instagram" in datos["plataformas"]
    # El prompt de QA viaja en la semilla del paquete: siempre disponible.
    assert datos["skill_disponible"] is True


def test_opciones_skill_disponible_si_sembrada(entorno):
    _sembrar_qa()
    cli = _cliente()
    assert cli.get("/api/qa-editorial").json()["skill_disponible"] is True


# --------------------------------------------------------------------------- #
# POST /api/qa-editorial/revisar                                               #
# --------------------------------------------------------------------------- #


def test_revisar_completa_y_parsea_informe(entorno):
    _sembrar_qa()
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_INFORME))
    r = cli.post(
        "/api/qa-editorial/revisar",
        json={"marca": "claro-sports", "texto": "El equipo de Mexcio ganó 3-0.", "plataforma": "Instagram"},
    )
    assert r.status_code == 200
    res = r.json()["generacion"]["resultado"]
    informe = res["informe"]
    assert informe["verdicto"] == "revisar"
    assert res["verdicto"] == "revisar"
    assert len(informe["hallazgos"]) == 2
    tipos = {h["tipo"] for h in informe["hallazgos"]}
    assert tipos == {"ortografia", "dato"}
    # El dato sin fuente quedo marcado como no verificable.
    dato = next(h for h in informe["hallazgos"] if h["tipo"] == "dato")
    assert dato["no_verificable"] is True
    # SEÑALA, no publica: sin publicaciones auto-creadas.
    assert res["publicaciones"] == []
    # El bloque json no contamina el informe legible.
    assert "```json" not in informe["informe_texto"]
    # Se registro en el historial (descubrible desde "Generar copy").
    historial = cli.get("/api/skills/historial").json()["historial"]
    assert any(h["skill"] == "qa-editorial" for h in historial)


def test_revisar_inyecta_texto_plataforma_contexto_en_prompt(entorno):
    _sembrar_qa()
    capturado = {}
    base = lanzador_generacion_completa(_SALIDA_INFORME)

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    cli = _cliente(lanzar_generacion=lanzar)
    cli.post(
        "/api/qa-editorial/revisar",
        json={
            "marca": "unotv",
            "texto": "Un copy con un dedazo.",
            "plataforma": "X / Twitter",
            "contexto": "La nota dice X.",
        },
    )
    assert "Un copy con un dedazo." in capturado["prompt"]
    assert "X / Twitter" in capturado["prompt"]
    assert "La nota dice X." in capturado["prompt"]


def test_revisar_marca_invalida_400(entorno):
    _sembrar_qa()
    cli = _cliente()
    r = cli.post("/api/qa-editorial/revisar", json={"marca": "marca_falsa", "texto": "algo"})
    assert r.status_code == 400


def test_revisar_sin_texto_400(entorno):
    _sembrar_qa()
    cli = _cliente()
    assert cli.post("/api/qa-editorial/revisar", json={"marca": "unotv"}).status_code == 400
    assert cli.post("/api/qa-editorial/revisar", json={"marca": "unotv", "texto": "  "}).status_code == 400


def test_revisar_plataforma_desconocida_se_ignora(entorno):
    _sembrar_qa()
    capturado = {}
    base = lanzador_generacion_completa(_SALIDA_INFORME)

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    cli = _cliente(lanzar_generacion=lanzar)
    r = cli.post(
        "/api/qa-editorial/revisar",
        json={"marca": "unotv", "texto": "copy", "plataforma": "MySpace"},
    )
    assert r.status_code == 200
    # La plataforma desconocida no se cuela en el prompt (se sustituye por vacio).
    assert "MySpace" not in capturado["prompt"]


def test_revisar_funciona_sin_sembrar_skill(cliente):
    # El prompt de QA viaja en la semilla del paquete: la revision se arma sin catalogo de skills.
    r = cliente.post("/api/qa-editorial/revisar", json={"marca": "unotv", "texto": "algo"})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# parsear_informe (unidad pura)                                                #
# --------------------------------------------------------------------------- #


def test_parsear_informe_json_valido():
    informe = qa_editorial.parsear_informe(_SALIDA_INFORME)
    assert informe["verdicto"] == "revisar"
    assert informe["resumen"] == "Un typo y un dato sin fuente."
    assert len(informe["hallazgos"]) == 2
    assert "```json" not in informe["informe_texto"]


def test_parsear_informe_sin_json_degrada():
    """Sin bloque JSON: hallazgos vacio, verdicto del semaforo, texto intacto (sin emojis)."""
    salida = "🔴 NO PUBLICAR\n\nHay un incumplimiento legal: bandera con escudo."
    informe = qa_editorial.parsear_informe(salida)
    assert informe["verdicto"] == "no_publicar"
    assert informe["hallazgos"] == []
    assert "incumplimiento legal" in informe["informe_texto"]


def test_parsear_informe_descarta_tipo_desconocido_y_acota_gravedad():
    salida = """🟢 LISTO PARA APROBAR

```json
{"veredicto": "🟢", "resumen": "ok", "hallazgos": [
  {"tipo": "inventado", "gravedad": "error", "fragmento": "x", "explicacion": "y", "sugerencia": "z"},
  {"tipo": "voz", "gravedad": "rarisima", "fragmento": "a", "explicacion": "b", "sugerencia": "c"}
]}
```
"""
    informe = qa_editorial.parsear_informe(salida)
    # El tipo desconocido se descarta; el de gravedad invalida cae a "aviso".
    assert len(informe["hallazgos"]) == 1
    assert informe["hallazgos"][0]["tipo"] == "voz"
    assert informe["hallazgos"][0]["gravedad"] == "aviso"


def test_parsear_informe_no_verificable_solo_en_dato():
    salida = """🟡 REVISAR

```json
{"veredicto": "🟡", "resumen": "r", "hallazgos": [
  {"tipo": "ortografia", "gravedad": "aviso", "fragmento": "x", "explicacion": "y",
   "sugerencia": "z", "no_verificable": true}
]}
```
"""
    informe = qa_editorial.parsear_informe(salida)
    # no_verificable solo aplica a tipo=dato; en ortografia se ignora (queda False).
    assert informe["hallazgos"][0]["no_verificable"] is False
