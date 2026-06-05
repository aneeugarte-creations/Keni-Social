"""Tests de los Agentes de investigacion (Ola 6). OFFLINE.

Cubre:
  - CRUD de briefs (crear/listar/actualizar/borrar).
  - POST /api/investigacion/correr con ejecutor falso (sin claude/net).
  - POST /api/investigacion/candidatos/{id}/aceptar -> crea borrador en tablero.
  - POST /api/investigacion/candidatos/{id}/descartar.
  - Logica de dedup del daemon (`investigacion_daemon._filtrar_nuevos`).

Requiere el Postgres de pruebas (fixture `cliente`); en CI corre con el service postgres.
"""

from __future__ import annotations

import json

# --------------------------------------------------------------------------- #
# Helpers / fixtures                                                           #
# --------------------------------------------------------------------------- #


def _fake_ejecutor(candidatos: list[dict]) -> object:
    """Ejecutor fake: devuelve los candidatos dados sin tocar red ni binario."""

    def _ejecutor(prompt: str) -> str:
        return json.dumps({"candidatos": candidatos})

    return _ejecutor


def _brief_base():
    return {
        "nombre": "Noticias de deportes MX",
        "marca": "claro-sports",
        "linea": "Deportes",
        "instrucciones": "Busca los principales eventos deportivos del dia en Mexico.",
        "idiomas": "es",
    }


# --------------------------------------------------------------------------- #
# CRUD de briefs                                                               #
# --------------------------------------------------------------------------- #


def test_crear_brief_y_listar(cliente):
    r = cliente.post("/api/investigacion/briefs", json=_brief_base())
    assert r.status_code == 200, r.text
    brief = r.json()["brief"]
    assert brief["nombre"] == "Noticias de deportes MX"
    assert brief["marca"] == "claro-sports"
    assert brief["activo"] is True
    assert brief["id"]

    listado = cliente.get("/api/investigacion/briefs").json()
    ids = [b["id"] for b in listado["briefs"]]
    assert brief["id"] in ids


def test_crear_brief_sin_instrucciones_400(cliente):
    r = cliente.post("/api/investigacion/briefs", json={"nombre": "X", "instrucciones": ""})
    assert r.status_code == 400


def test_crear_brief_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/investigacion/briefs",
        json={"instrucciones": "Algo", "marca": "no-existe"},
    )
    assert r.status_code == 400


def test_actualizar_brief(cliente):
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]
    r = cliente.put(
        f"/api/investigacion/briefs/{brief_id}",
        json={"nombre": "Actualizado", "activo": False},
    )
    assert r.status_code == 200, r.text
    b = r.json()["brief"]
    assert b["nombre"] == "Actualizado"
    assert b["activo"] is False


def test_actualizar_brief_inexistente_404(cliente):
    r = cliente.put("/api/investigacion/briefs/nope", json={"nombre": "X"})
    assert r.status_code == 404


def test_borrar_brief(cliente):
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]
    r = cliente.delete(f"/api/investigacion/briefs/{brief_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Ya no aparece en el listado.
    ids = [b["id"] for b in cliente.get("/api/investigacion/briefs").json()["briefs"]]
    assert brief_id not in ids


def test_borrar_brief_inexistente_404(cliente):
    assert cliente.delete("/api/investigacion/briefs/nope").status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/investigacion/correr (con ejecutor falso)                          #
# --------------------------------------------------------------------------- #


def test_correr_brief_devuelve_candidatos(cliente, monkeypatch):
    # Crea el brief.
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]

    # Inyecta el ejecutor falso.
    fake = _fake_ejecutor([
        {
            "titulo": "Mexico gana el Mundial",
            "resumen": "La seleccion mexicana logro un hito historico.",
            "por_que": "Es tendencia hoy en todas las redes.",
            "fuente": "ESPN",
            "enlace": "https://espn.com/mexico-mundial",
            "idioma": "es",
        },
        {
            "titulo": "Liga MX jornada 10",
            "resumen": "Resultados de la jornada.",
            "por_que": "Partido clave para el liderato.",
            "fuente": "Marca",
            "enlace": "https://marca.com/ligamx",
            "idioma": "es",
        },
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.investigacion_agente._ejecutar_claude_json", fake
    )

    r = cliente.post("/api/investigacion/correr", json={"brief_id": brief_id})
    assert r.status_code == 200, r.text
    data = r.json()
    candidatos = data["candidatos"]
    assert len(candidatos) == 2
    assert candidatos[0]["titulo"] == "Mexico gana el Mundial"
    assert candidatos[0]["marca"] == "claro-sports"
    assert candidatos[0]["estado"] == "nuevo"
    assert candidatos[0]["brief_id"] == brief_id
    assert data["errores"] == []


def test_correr_adhoc_sin_brief_guardado(cliente, monkeypatch):
    """Correr un brief ad-hoc (sin guardarlo) tambien funciona."""
    fake = _fake_ejecutor([
        {"titulo": "Breaking news", "resumen": "...", "por_que": "hoy", "fuente": "CNN", "enlace": "", "idioma": "es"},
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.investigacion_agente._ejecutar_claude_json", fake
    )
    r = cliente.post(
        "/api/investigacion/correr",
        json={"instrucciones": "Busca noticias de tecnologia MX", "marca": "unotv"},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["candidatos"]) == 1


def test_correr_sin_brief_id_ni_instrucciones_400(cliente):
    r = cliente.post("/api/investigacion/correr", json={})
    assert r.status_code == 400


def test_correr_brief_inexistente_404(cliente):
    r = cliente.post("/api/investigacion/correr", json={"brief_id": "no-existe"})
    assert r.status_code == 404


def test_correr_almacena_y_se_puede_listar(cliente, monkeypatch):
    """Los candidatos insertados aparecen en GET /api/investigacion/candidatos."""
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]
    fake = _fake_ejecutor([
        {
            "titulo": "Candidato A", "resumen": "r", "por_que": "p",
            "fuente": "f", "enlace": "https://a.com", "idioma": "es",
        },
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.investigacion_agente._ejecutar_claude_json", fake
    )
    cliente.post("/api/investigacion/correr", json={"brief_id": brief_id})

    r = cliente.get("/api/investigacion/candidatos")
    assert r.status_code == 200
    titulos = [c["titulo"] for c in r.json()["candidatos"]]
    assert "Candidato A" in titulos


# --------------------------------------------------------------------------- #
# POST /api/investigacion/candidatos/{id}/aceptar                              #
# --------------------------------------------------------------------------- #


def test_aceptar_candidato_crea_borrador_y_marca_aceptado(cliente, monkeypatch):
    """Aceptar un candidato crea un item del tablero (origen=investigacion) y marca aceptado."""
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]
    fake = _fake_ejecutor([
        {
            "titulo": "Semifinal Copa MX", "resumen": "Gran partido.",
            "por_que": "Hoy es el partido.", "fuente": "ESPN",
            "enlace": "https://espn.com/copa", "idioma": "es",
        },
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.investigacion_agente._ejecutar_claude_json", fake
    )
    candidatos = cliente.post("/api/investigacion/correr", json={"brief_id": brief_id}).json()["candidatos"]
    candidato_id = candidatos[0]["id"]

    # Acepta sin generar copy para no depender del worker.
    r = cliente.post(
        f"/api/investigacion/candidatos/{candidato_id}/aceptar",
        json={"generar": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["candidato"]["estado"] == "aceptado"
    contenido_id = data["contenido_id"]
    assert contenido_id

    # El candidato ya tiene contenido_id.
    listado = cliente.get("/api/investigacion/candidatos?estado=aceptado").json()["candidatos"]
    aceptados = [c for c in listado if c["id"] == candidato_id]
    assert len(aceptados) == 1
    assert aceptados[0]["contenido_id"] == contenido_id

    # El contenido del tablero existe con origen='investigacion': aparece en el listado.
    r2 = cliente.get("/api/contenido")
    assert r2.status_code == 200, r2.text
    contenidos = r2.json()["contenidos"]
    investigacion_items = [it for it in contenidos if it.get("id") == contenido_id]
    assert len(investigacion_items) == 1
    assert investigacion_items[0]["origen"] == "investigacion"
    assert investigacion_items[0]["titulo"] == "Semifinal Copa MX"


def test_aceptar_candidato_inexistente_404(cliente):
    r = cliente.post("/api/investigacion/candidatos/nope/aceptar", json={})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/investigacion/candidatos/{id}/descartar                            #
# --------------------------------------------------------------------------- #


def test_descartar_candidato(cliente, monkeypatch):
    brief_id = cliente.post("/api/investigacion/briefs", json=_brief_base()).json()["brief"]["id"]
    fake = _fake_ejecutor([
        {"titulo": "Descartable", "resumen": "r", "por_que": "p", "fuente": "f", "enlace": "", "idioma": "es"},
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.investigacion_agente._ejecutar_claude_json", fake
    )
    candidato_id = cliente.post("/api/investigacion/correr", json={"brief_id": brief_id}).json()["candidatos"][0]["id"]

    r = cliente.post(f"/api/investigacion/candidatos/{candidato_id}/descartar")
    assert r.status_code == 200, r.text
    assert r.json()["candidato"]["estado"] == "descartado"

    # Aparece en el filtro de descartados.
    listado = cliente.get("/api/investigacion/candidatos?estado=descartado").json()["candidatos"]
    assert any(c["id"] == candidato_id for c in listado)


def test_descartar_candidato_inexistente_404(cliente):
    assert cliente.post("/api/investigacion/candidatos/nope/descartar").status_code == 404


# --------------------------------------------------------------------------- #
# Logica de dedup del daemon (PURA, sin base de datos)                         #
# --------------------------------------------------------------------------- #


def test_daemon_dedup_por_enlace():
    from keni_consola.investigacion_daemon import _filtrar_nuevos

    ya = {"https://espn.com/a"}
    cand = {"resumen": "", "por_que": "", "fuente": "", "idioma": "es"}
    candidatos = [
        {**cand, "titulo": "Nuevo tema", "enlace": "https://espn.com/a"},
        {**cand, "titulo": "Otro tema", "enlace": "https://espn.com/b"},
    ]
    nuevos = _filtrar_nuevos(candidatos, fecha="2026-06-05", ya_existentes=ya, cap_restante=10)
    assert len(nuevos) == 1
    assert nuevos[0]["titulo"] == "Otro tema"


def test_daemon_dedup_por_titulo():
    from keni_consola.investigacion_daemon import _filtrar_nuevos

    fecha = "2026-06-05"
    ya = {"mexico gana el mundial|2026-06-05"}
    cand = {"enlace": "", "resumen": "", "por_que": "", "fuente": "", "idioma": "es"}
    candidatos = [
        {**cand, "titulo": "Mexico gana el Mundial"},
        {**cand, "titulo": "Liga MX jornada"},
    ]
    nuevos = _filtrar_nuevos(candidatos, fecha=fecha, ya_existentes=ya, cap_restante=10)
    assert len(nuevos) == 1
    assert nuevos[0]["titulo"] == "Liga MX jornada"


def test_daemon_dedup_respeta_cap():
    from keni_consola.investigacion_daemon import _filtrar_nuevos

    ya: set[str] = set()
    candidatos = [
        {"titulo": f"Tema {i}", "enlace": f"https://x.com/{i}",
         "resumen": "", "por_que": "", "fuente": "", "idioma": "es"}
        for i in range(10)
    ]
    nuevos = _filtrar_nuevos(candidatos, fecha="2026-06-05", ya_existentes=ya, cap_restante=3)
    assert len(nuevos) == 3


def test_daemon_dedup_mismo_brief_no_duplica_en_barrido():
    """Dentro de un barrido dos briefs no repiten el mismo enlace."""
    from keni_consola.investigacion_daemon import _filtrar_nuevos

    ya: set[str] = set()
    fecha = "2026-06-05"
    cand = {"resumen": "", "por_que": "", "fuente": "", "idioma": "es"}
    # Primer brief produce "Tema 1".
    cands1 = [{**cand, "titulo": "Tema 1", "enlace": "https://a.com/1"}]
    n1 = _filtrar_nuevos(cands1, fecha=fecha, ya_existentes=ya, cap_restante=10)
    assert len(n1) == 1

    # El segundo brief trae el mismo enlace: ya esta en `ya` y se descarta.
    cands2 = [{**cand, "titulo": "Tema 1 bis", "enlace": "https://a.com/1"}]
    n2 = _filtrar_nuevos(cands2, fecha=fecha, ya_existentes=ya, cap_restante=10)
    assert len(n2) == 0
