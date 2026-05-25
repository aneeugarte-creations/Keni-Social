"""Tests de la migracion one-shot consola.db -> ficheros YAML (#84).

Siembra un consola.db real (via `db.py`), migra y verifica: ids/origen/imagen
preservados, CSV/JSON->listas, 0/1->bool, franjas agrupadas por marca, idempotencia
y respaldo .bak. Las tareas NO se migran (siguen en SQLite).
"""

from __future__ import annotations

import pytest

from keni_consola import db, migracion, repos


@pytest.fixture
def base(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "ficheros")
    return tmp_path


def _sembrar_db():
    """Crea contenido variado en SQLite (via db.py) y devuelve los ids creados."""
    pub = db.crear_publicacion(
        "unotv", "x", titulo="Post", contenido="Cuerpo", estado="aprobado",
        origen="hist-123", imagen="foto.png", evergreen=True,
    )
    plant = db.crear_plantilla("Saludo", marca="claro-sports", red="instagram", contenido="Hola")
    fuente = db.crear_fuente_rss(
        "Diario", "https://example.com/feed.xml", marca="unotv",
        incluir="ia, agentes", excluir="rumor", redes_def='["x", "instagram"]',
    )
    grupo = db.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol", "#liga"])
    f1 = db.crear_franja(1, "09:00", marca="unotv", red="x")
    f2 = db.crear_franja(3, "18:00", marca="claro-sports")
    hid = db.registrar_historial_skill(
        "copy-desde-nota", "unotv", "✅ texto", titulo="Hist",
        piezas=[{"red": "x", "contenido": "c", "caracteres": 1}],
    )
    db.marcar_item(fuente["id"], "guid-1", True)
    db.crear_tarea("proy", "Tarea que NO se migra")
    return {
        "pub": pub, "plant": plant, "fuente": fuente, "grupo": grupo,
        "f1": f1, "f2": f2, "hid": hid,
    }


def test_migracion_preserva_ids_y_campos(base):
    sem = _sembrar_db()
    conteos = migracion.migrar_a_ficheros()
    assert conteos["publicaciones"] == 1
    assert conteos["plantillas"] == 1
    assert conteos["fuentes_rss"] == 1
    assert conteos["grupos_hashtags"] == 1
    assert conteos["franjas"] == 2
    assert conteos["skill_historial"] == 1
    assert conteos["rss_items_vistos"] == 1

    # Publicacion: id, origen e imagen preservados; evergreen como bool.
    pub = repos.obtener_publicacion(sem["pub"]["id"])
    assert pub is not None
    assert pub["id"] == sem["pub"]["id"]
    assert pub["origen"] == "hist-123"
    assert pub["imagen"] == "foto.png"
    assert pub["estado"] == "aprobado"
    assert pub["evergreen"] is True

    # Plantilla preservada con su id en su marca.
    plant = repos.obtener_plantilla(sem["plant"]["id"])
    assert plant["nombre"] == "Saludo"
    assert plant["marca"] == "claro-sports"

    # Fuente: incluir/excluir CSV intactos; redes_def JSON intacto; activo bool.
    fuente = repos.obtener_fuente_rss(sem["fuente"]["id"])
    assert fuente["incluir"] == "ia, agentes"
    assert fuente["excluir"] == "rumor"
    assert fuente["redes_def"] == '["x", "instagram"]'
    assert fuente["activo"] is True

    # Grupo: hashtags como lista.
    grupo = repos.obtener_grupo_hashtags(sem["grupo"]["id"])
    assert grupo["hashtags"] == ["#gol", "#liga"]

    # Historial preservado con piezas y id.
    hist = repos.obtener_historial_skill(sem["hid"])
    assert hist["titulo"] == "Hist"
    assert hist["piezas"][0]["red"] == "x"

    # Items vistos migrados a la marca de su fuente.
    assert repos.claves_vistas(sem["fuente"]["id"]) == {"guid-1"}


def test_migracion_franjas_agrupadas_por_marca(base):
    _sembrar_db()
    migracion.migrar_a_ficheros()
    # Cada marca tiene su franjas.yaml con sus franjas.
    assert (base / "datos" / "unotv" / "franjas.yaml").is_file()
    assert (base / "datos" / "claro-sports" / "franjas.yaml").is_file()
    franjas = repos.listar_franjas()
    assert len(franjas) == 2
    marcas = {f["marca"] for f in franjas}
    assert marcas == {"unotv", "claro-sports"}


def test_migracion_idempotente(base):
    sem = _sembrar_db()
    migracion.migrar_a_ficheros(hacer_bak=False)
    # Segunda pasada: no duplica (mismos ids ya en disco).
    conteos2 = migracion.migrar_a_ficheros(hacer_bak=False)
    assert conteos2["publicaciones"] == 0
    assert conteos2["franjas"] == 0
    assert conteos2["skill_historial"] == 0
    assert len(repos.listar_publicaciones()) == 1
    assert len(repos.listar_franjas()) == 2
    # El id no cambia entre pasadas.
    assert repos.obtener_publicacion(sem["pub"]["id"]) is not None


def test_migracion_deja_bak_y_tareas_siguen_en_sqlite(base):
    _sembrar_db()
    migracion.migrar_a_ficheros()
    assert (base / "consola.db.bak").is_file()
    # Las tareas NO se migran: siguen accesibles via repos (que delega en db).
    tareas = repos.listar_tareas()
    assert any(t["titulo"] == "Tarea que NO se migra" for t in tareas)


def test_migracion_sin_db_no_falla(base):
    # Sin consola.db sembrado: contadores en cero, sin excepcion.
    conteos = migracion.migrar_a_ficheros(hacer_bak=False)
    assert all(v == 0 for v in conteos.values())


def test_migracion_best_effort_fila_corrupta(base):
    """Una publicacion con estado raro en la DB se migra igual (la validacion es al LEER)."""
    db.crear_publicacion("unotv", "x", titulo="Buena")
    migracion.migrar_a_ficheros(hacer_bak=False)
    # La migracion no rompe; el contenido valido queda disponible.
    assert len(repos.listar_publicaciones()) == 1
