"""Tests del CATALOGO de skills respaldado por archivos (files-as-truth).

TODO OFFLINE y aislado: el `entorno` siembra un catalogo de skills FALSO en un tmp
(`KENI_SKILLS_DIR`), de modo que estos tests NUNCA leen ni escriben el `skills-copy/`
real del repo. Cubre:
  - `GET /api/skills` (opciones): catalogo agrupado + marcas + redes + skills_media.
  - CRUD de `/api/skills/catalogo` (listar/crear/obtener/actualizar/skill-md/borrar).
  - `POST /api/skills/catalogo/{id}/vista-prompt` (render del prompt, sin claude).
  - El modulo de dominio `skills_catalogo` (round-trip en disco).
"""

from __future__ import annotations

from keni_consola import skills_catalogo

from .conftest import _cliente

# --------------------------------------------------------------------------- #
# GET /api/skills (opciones): catalogo agrupado + marcas + redes               #
# --------------------------------------------------------------------------- #


def test_opciones_devuelve_catalogo_agrupado(entorno):
    cuerpo = _cliente().get("/api/skills").json()
    # Grupos por `grupo` con etiqueta humana y bandera experimental.
    grupos = cuerpo["grupos"]
    por_grupo = {g["grupo"]: g for g in grupos}
    assert "validadas" in por_grupo
    assert por_grupo["validadas"]["etiqueta"] == "Validadas con el equipo"
    assert por_grupo["validadas"]["experimental"] is False
    assert por_grupo["experimentales"]["experimental"] is True

    # Cada skill trae lo necesario para el formulario dinamico.
    ids = {s["id"] for g in grupos for s in g["skills"]}
    assert {"copy-desde-nota", "resumen-tendencia", "clip-a-copy"} <= ids
    copy = next(s for g in grupos for s in g["skills"] if s["id"] == "copy-desde-nota")
    for clave in ("id", "nombre", "explicacion", "aplica_redes", "salida", "media", "campos"):
        assert clave in copy
    assert copy["aplica_redes"] is True
    assert copy["salida"] == "piezas"
    assert copy["campos"][0]["id"] == "fuente"
    assert copy["campos"][0]["requerido"] is True

    # Marcas y redes presentes (id + nombre).
    assert all("id" in m and "nombre" in m for m in cuerpo["marcas"])
    assert all("id" in r and "nombre" in r for r in cuerpo["redes"])
    assert {r["id"] for r in cuerpo["redes"]} == {"x", "instagram", "facebook", "tiktok", "youtube"}

    # skills_media derivado del catalogo (clip-a-copy tiene campo archivo).
    assert "clip-a-copy" in cuerpo["skills_media"]
    assert "copy-desde-nota" not in cuerpo["skills_media"]


# --------------------------------------------------------------------------- #
# GET /api/skills/catalogo (definiciones completas)                            #
# --------------------------------------------------------------------------- #


def test_catalogo_listar_definiciones_completas(entorno):
    cuerpo = _cliente().get("/api/skills/catalogo").json()
    skills = cuerpo["skills"]
    por_id = {s["id"]: s for s in skills}
    assert {"copy-desde-nota", "resumen-tendencia", "clip-a-copy"} <= set(por_id)
    # La definicion completa incluye la plantilla y el grupo/orden.
    copy = por_id["copy-desde-nota"]
    assert copy["grupo"] == "validadas"
    assert "plantilla_invocacion" in copy
    assert "{fuente}" in copy["plantilla_invocacion"]
    # Orden ascendente (copy=10 antes que clip=20 antes que resumen=40).
    ids_orden = [s["id"] for s in skills]
    assert ids_orden.index("copy-desde-nota") < ids_orden.index("clip-a-copy")
    assert ids_orden.index("clip-a-copy") < ids_orden.index("resumen-tendencia")


# --------------------------------------------------------------------------- #
# CRUD: crear / obtener / actualizar / skill-md / borrar (round-trip)          #
# --------------------------------------------------------------------------- #


def test_catalogo_crud_round_trip(entorno):
    cli = _cliente()

    # CREAR
    r = cli.post("/api/skills/catalogo", json={
        "nombre": "Mi Skill Nueva",
        "explicacion": "Hace algo útil.",
        "grupo": "experimentales",
        "aplica_redes": False,
        "salida": "documento",
    })
    assert r.status_code == 200
    creada = r.json()["skill"]
    assert creada["id"] == "mi-skill-nueva"
    assert creada["grupo"] == "experimentales"
    assert creada["salida"] == "documento"
    # Arranca con un campo textarea "fuente" requerido.
    assert creada["campos"][0]["id"] == "fuente"
    assert creada["campos"][0]["requerido"] is True

    # OBTENER (metadata + SKILL.md)
    r = cli.get("/api/skills/catalogo/mi-skill-nueva")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["skill"]["nombre"] == "Mi Skill Nueva"
    assert cuerpo["skill_md"].startswith("---")  # frontmatter
    assert "mi-skill-nueva" in cuerpo["skill_md"]

    # ACTUALIZAR metadata (cambia campos + salida)
    nueva_meta = {
        "nombre": "Mi Skill Renombrada",
        "explicacion": "Ahora produce piezas.",
        "grupo": "validadas",
        "aplica_redes": True,
        "salida": "piezas",
        "orden": 5,
        "campos": [
            {"id": "fuente", "etiqueta": "Fuente", "tipo": "textarea", "requerido": True},
            {"id": "extra", "etiqueta": "Extra", "tipo": "texto", "requerido": False},
        ],
        "plantilla_invocacion": "usa mi-skill-nueva, marca {marca}: {fuente} / {extra}",
    }
    r = cli.put("/api/skills/catalogo/mi-skill-nueva", json=nueva_meta)
    assert r.status_code == 200
    actualizada = r.json()["skill"]
    assert actualizada["nombre"] == "Mi Skill Renombrada"
    assert actualizada["salida"] == "piezas"
    assert actualizada["aplica_redes"] is True
    assert [c["id"] for c in actualizada["campos"]] == ["fuente", "extra"]
    assert actualizada["orden"] == 5

    # Persistio: el listado lo refleja.
    skills = cli.get("/api/skills/catalogo").json()["skills"]
    assert any(s["id"] == "mi-skill-nueva" and s["nombre"] == "Mi Skill Renombrada" for s in skills)

    # SKILL.md
    r = cli.put("/api/skills/catalogo/mi-skill-nueva/skill-md",
                json={"contenido": "# mi-skill-nueva\n\nNuevo cuerpo del SKILL.md.\n"})
    assert r.status_code == 200
    cuerpo = cli.get("/api/skills/catalogo/mi-skill-nueva").json()
    assert "Nuevo cuerpo del SKILL.md." in cuerpo["skill_md"]

    # BORRAR
    r = cli.delete("/api/skills/catalogo/mi-skill-nueva")
    assert r.status_code == 200
    assert cli.get("/api/skills/catalogo/mi-skill-nueva").status_code == 404
    skills = cli.get("/api/skills/catalogo").json()["skills"]
    assert all(s["id"] != "mi-skill-nueva" for s in skills)


def test_catalogo_crear_duplicado_da_400(entorno):
    cli = _cliente()
    # copy-desde-nota ya existe (sembrado) -> "Copy desde nota" derivaria a copy-desde-nota.
    r = cli.post("/api/skills/catalogo", json={"nombre": "Copy desde nota"})
    assert r.status_code == 400
    assert "ya existe" in r.json()["error"].lower()


def test_catalogo_crear_nombre_invalido_da_400(entorno):
    cli = _cliente()
    r = cli.post("/api/skills/catalogo", json={"nombre": "   "})
    assert r.status_code == 400


def test_catalogo_obtener_inexistente_da_404(entorno):
    assert _cliente().get("/api/skills/catalogo/no-existe").status_code == 404


def test_catalogo_actualizar_inexistente_da_404(entorno):
    r = _cliente().put("/api/skills/catalogo/no-existe", json={"nombre": "X"})
    assert r.status_code == 404


def test_catalogo_actualizar_salida_invalida_da_400(entorno):
    cli = _cliente()
    r = cli.put("/api/skills/catalogo/copy-desde-nota", json={
        "nombre": "Copy", "salida": "loquesea", "campos": [],
    })
    assert r.status_code == 400


def test_catalogo_borrar_inexistente_da_404(entorno):
    assert _cliente().delete("/api/skills/catalogo/no-existe").status_code == 404


# --------------------------------------------------------------------------- #
# vista-prompt: render del prompt (sin claude)                                 #
# --------------------------------------------------------------------------- #


def test_vista_prompt_piezas_incluye_redes(entorno):
    cli = _cliente()
    r = cli.post("/api/skills/catalogo/copy-desde-nota/vista-prompt", json={
        "marca": "unotv",
        "valores": {"fuente": "Mi nota de prueba"},
        "redes": ["x", "instagram"],
    })
    assert r.status_code == 200
    prompt = r.json()["prompt"]
    assert "Mi nota de prueba" in prompt
    assert "unotv" in prompt
    # aplica_redes=true => incluye la instruccion de redes + bloque json.
    assert "```json" in prompt
    assert "No uses emojis en el copy." in prompt


def test_vista_prompt_documento_sin_instruccion_redes(entorno):
    cli = _cliente()
    r = cli.post("/api/skills/catalogo/resumen-tendencia/vista-prompt", json={
        "marca": "claro-sports",
        "valores": {"fuentes": "Tema de prueba"},
        "redes": ["x"],
    })
    assert r.status_code == 200
    prompt = r.json()["prompt"]
    assert "Tema de prueba" in prompt
    # aplica_redes=false => SIN bloque json ni instruccion de redes.
    assert "```json" not in prompt
    assert "SOLO para estas redes" not in prompt
    assert "No uses emojis en el copy." in prompt


def test_vista_prompt_skill_inexistente_da_404(entorno):
    r = _cliente().post("/api/skills/catalogo/no-existe/vista-prompt", json={"marca": "unotv"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Modulo de dominio skills_catalogo (round-trip en disco)                      #
# --------------------------------------------------------------------------- #


def test_dominio_crear_obtener_borrar(entorno):
    skill = skills_catalogo.crear("Otra Skill", explicacion="prueba", salida="documento")
    assert skill.id == "otra-skill"
    assert skills_catalogo.existe("otra-skill")
    leida = skills_catalogo.obtener("otra-skill")
    assert leida is not None and leida.nombre == "Otra Skill"
    skills_catalogo.borrar("otra-skill")
    assert not skills_catalogo.existe("otra-skill")


def test_dominio_render_invocacion_documento_sin_redes(entorno):
    skill = skills_catalogo.obtener("resumen-tendencia")
    assert skill is not None
    prompt = skills_catalogo.render_invocacion(
        skill, "unotv", {"fuentes": "contenido"}, ["x", "instagram"]
    )
    assert "contenido" in prompt
    assert "```json" not in prompt  # aplica_redes=false


def test_dominio_obtener_id_invalido_es_none(entorno):
    # Anti-traversal: un id con separadores no resuelve.
    assert skills_catalogo.obtener("../escape") is None
    assert skills_catalogo.obtener("a/b") is None


def test_dominio_listar_salta_carpetas_sin_keni_yaml(entorno):
    # Una carpeta sin keni.yaml no aparece en el listado (tolerante).
    base = skills_catalogo.dir_skills()
    (base / "carpeta-vacia").mkdir(parents=True, exist_ok=True)
    ids = {s.id for s in skills_catalogo.listar()}
    assert "carpeta-vacia" not in ids
    assert "copy-desde-nota" in ids
