"""Tests del backend de FICHEROS YAML (#84): la verdad vive en disco.

OFFLINE, todo aislado en tmp (raiz de datos + indice via env vars). Cubre:
  - round-trip: crear via repos -> existe el .yaml legible -> editar el .yaml a
    mano -> repos lo lee actualizado.
  - orden por fecha-hora (determinista, sin apoyarse en rowid).
  - validacion: YAML corrupto / estado o red invalidos se omiten sin romper.
  - escritura atomica (no quedan ficheros .tmp).
  - regeneracion del indice si se borra.
  - layout agente=marca=carpeta + marca.yaml/CLAUDE.md sembrados.
"""

from __future__ import annotations

import time

import pytest
import yaml

from keni_consola import ficheros, indice, repos


@pytest.fixture
def base(monkeypatch, tmp_path):
    """Aisla la raiz de datos de ficheros, el indice y la DB (tareas) en tmp."""
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "ficheros")
    return tmp_path


def _ruta_pub(base, marca, pub_id):
    return base / "datos" / marca / "publicaciones" / f"{pub_id}.yaml"


# --------------------------------------------------------------------------- #
# Layout: agente = marca = carpeta (+ marca.yaml / CLAUDE.md)                  #
# --------------------------------------------------------------------------- #


def test_carpeta_marca_siembra_meta_y_claude(base):
    pub = repos.crear_publicacion("unotv", "x", titulo="Hola")
    carpeta = base / "datos" / "unotv"
    assert carpeta.is_dir()
    assert (carpeta / "marca.yaml").is_file()
    assert (carpeta / "CLAUDE.md").is_file()
    meta = yaml.safe_load((carpeta / "marca.yaml").read_text())
    assert meta["id"] == "unotv"
    assert meta["etiqueta"] == "UnoTV"
    assert meta["id_metricas"] == "unotv"
    # El YAML de la publicacion existe y NO repite id ni marca dentro.
    cuerpo = yaml.safe_load(_ruta_pub(base, "unotv", pub["id"]).read_text())
    assert "id" not in cuerpo
    assert "marca" not in cuerpo
    assert cuerpo["titulo"] == "Hola"


# --------------------------------------------------------------------------- #
# Round-trip: crear via repos -> .yaml legible -> editar a mano -> repos lo lee #
# --------------------------------------------------------------------------- #


def test_round_trip_publicacion(base):
    pub = repos.crear_publicacion("unotv", "x", titulo="T", contenido="Cuerpo largo\nmultilinea")
    ruta = _ruta_pub(base, "unotv", pub["id"])
    assert ruta.is_file()
    # Editamos el YAML A MANO (como haria una persona en su editor).
    datos = yaml.safe_load(ruta.read_text())
    datos["titulo"] = "Editado a mano"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False))
    # repos lo lee actualizado (re-indexa por mtime distinto).
    leida = repos.obtener_publicacion(pub["id"])
    assert leida["titulo"] == "Editado a mano"
    assert leida["contenido"] == "Cuerpo largo\nmultilinea"


def test_contenido_largo_en_bloque_literal(base):
    largo = "linea1\nlinea2\nlinea3 con texto\n"
    pub = repos.crear_publicacion("unotv", "x", contenido=largo)
    texto = _ruta_pub(base, "unotv", pub["id"]).read_text()
    # PyYAML usa bloque '|' para multilinea: el texto crudo aparece sin escapes \n.
    assert "linea1" in texto and "\\n" not in texto
    assert repos.obtener_publicacion(pub["id"])["contenido"] == largo


def test_round_trip_plantilla_y_hashtags_y_fuente(base):
    p = repos.crear_plantilla("Saludo", marca="unotv", red="x", contenido="Hola")
    assert repos.obtener_plantilla(p["id"])["nombre"] == "Saludo"
    g = repos.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol", "#liga"])
    assert repos.obtener_grupo_hashtags(g["id"])["hashtags"] == ["#gol", "#liga"]
    # hashtags como lista YAML nativa (no JSON embebido).
    ruta_g = base / "datos" / "unotv" / "hashtags" / f"{g['id']}.yaml"
    cuerpo = yaml.safe_load(ruta_g.read_text())
    assert cuerpo["hashtags"] == ["#gol", "#liga"]
    fr = repos.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    assert repos.obtener_fuente_rss(fr["id"])["nombre"] == "Diario"


def test_historial_round_trip_y_layout_por_fecha(base):
    hid = repos.registrar_historial_skill(
        "copy-desde-nota", "unotv", "Resultado largo\ncon saltos", titulo="T",
        piezas=[{"red": "x", "contenido": "c", "caracteres": 1}],
    )
    leido = repos.obtener_historial_skill(hid)
    assert leido["skill"] == "copy-desde-nota"
    assert leido["piezas"][0]["red"] == "x"
    # Sin metricas => None.
    assert leido["metricas"] is None
    # Vive bajo historial/<YYYY>/<MM>/<id>.yaml
    encontrados = list((base / "datos" / "unotv" / "historial").rglob(f"{hid}.yaml"))
    assert len(encontrados) == 1


def test_historial_guarda_y_devuelve_metricas(base):
    metricas = {"tokens_in": 10, "tokens_out": 5, "num_turns": 1,
                "total_cost_usd": 0.02, "duration_ms": 99, "modelo": "m"}
    hid = repos.registrar_historial_skill(
        "copy-desde-nota", "unotv", "RES", metricas=metricas
    )
    leido = repos.obtener_historial_skill(hid)
    assert leido["metricas"] == metricas
    assert repos.listar_historial_skills()[0]["metricas"] == metricas


# --------------------------------------------------------------------------- #
# Orden por fecha-hora (determinista)                                          #
# --------------------------------------------------------------------------- #


def test_orden_publicaciones_por_fecha_hora(base):
    a = repos.crear_publicacion("unotv", "x", titulo="A")
    time.sleep(1.05)  # fecha_creacion tiene resolucion de segundos
    b = repos.crear_publicacion("unotv", "x", titulo="B")
    ids = [p["id"] for p in repos.listar_publicaciones()]
    # Mas reciente primero (B antes que A).
    assert ids.index(b["id"]) < ids.index(a["id"])


def test_orden_franjas_determinista(base):
    repos.crear_franja(4, "08:00", marca="unotv")
    repos.crear_franja(1, "12:00", marca="unotv")
    repos.crear_franja(1, "09:00", marca="claro-sports")
    orden = [(f["dia_semana"], f["hora"]) for f in repos.listar_franjas()]
    assert orden == [(1, "09:00"), (1, "12:00"), (4, "08:00")]


# --------------------------------------------------------------------------- #
# Validacion: YAML corrupto / estado o red invalidos se OMITEN sin romper      #
# --------------------------------------------------------------------------- #


def test_yaml_corrupto_se_omite(base):
    ok = repos.crear_publicacion("unotv", "x", titulo="Buena")
    mala = repos.crear_publicacion("unotv", "x", titulo="Mala")
    # Corrompemos el YAML de 'mala' a mano.
    _ruta_pub(base, "unotv", mala["id"]).write_text(":\n  - [esto no es yaml valido")
    pubs = repos.listar_publicaciones()
    ids = {p["id"] for p in pubs}
    assert ok["id"] in ids
    assert mala["id"] not in ids  # omitida, no rompe el listado
    assert repos.obtener_publicacion(mala["id"]) is None


def test_estado_invalido_se_omite(base):
    pub = repos.crear_publicacion("unotv", "x", titulo="X")
    ruta = _ruta_pub(base, "unotv", pub["id"])
    datos = yaml.safe_load(ruta.read_text())
    datos["estado"] = "estado-inventado"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True))
    assert all(p["id"] != pub["id"] for p in repos.listar_publicaciones())
    assert repos.obtener_publicacion(pub["id"]) is None


def test_red_invalida_se_omite(base):
    pub = repos.crear_publicacion("unotv", "x", titulo="X")
    ruta = _ruta_pub(base, "unotv", pub["id"])
    datos = yaml.safe_load(ruta.read_text())
    datos["red"] = "myspace"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True))
    assert all(p["id"] != pub["id"] for p in repos.listar_publicaciones())


# --------------------------------------------------------------------------- #
# Escritura atomica (no quedan .tmp)                                          #
# --------------------------------------------------------------------------- #


def test_escritura_no_deja_temporales(base):
    for i in range(5):
        repos.crear_publicacion("unotv", "x", titulo=f"P{i}")
    tmp = list((base / "datos").rglob(".tmp-*"))
    assert tmp == []
    # Y los .yaml definitivos si estan.
    yamls = list((base / "datos" / "unotv" / "publicaciones").glob("*.yaml"))
    assert len(yamls) == 5


# --------------------------------------------------------------------------- #
# Regeneracion del indice si se borra                                         #
# --------------------------------------------------------------------------- #


def test_indice_se_regenera_si_se_borra(base):
    a = repos.crear_publicacion("unotv", "x", titulo="A")
    b = repos.crear_publicacion("claro-sports", "instagram", titulo="B")
    # Borra el indice (NO es la verdad): los YAML siguen en disco.
    indice.ruta_indice().unlink()
    # Listar lo reconstruye desde los ficheros.
    ids = {p["id"] for p in repos.listar_publicaciones()}
    assert {a["id"], b["id"]} <= ids
    # Y obtener por id tambien funciona tras el borrado.
    indice.ruta_indice().unlink()
    assert repos.obtener_publicacion(a["id"])["titulo"] == "A"


def test_reconstruir_indice_completo(base):
    repos.crear_publicacion("unotv", "x", titulo="A")
    repos.crear_plantilla("P", marca="unotv")
    indice.ruta_indice().unlink()
    ficheros.reconstruir_indice()
    assert len(repos.listar_publicaciones()) == 1
    assert len(repos.listar_plantillas()) == 1


# --------------------------------------------------------------------------- #
# Filtros (delegados al indice)                                               #
# --------------------------------------------------------------------------- #


def test_filtros_listar_publicaciones(base):
    repos.crear_publicacion("unotv", "x", evergreen=True)
    repos.crear_publicacion("unotv", "instagram", evergreen=False)
    repos.crear_publicacion("claro-sports", "x", estado="aprobado")
    assert len(repos.listar_publicaciones(marca="unotv")) == 2
    assert len(repos.listar_publicaciones(red="x")) == 2
    assert len(repos.listar_publicaciones(estado="aprobado")) == 1
    assert len(repos.listar_publicaciones(evergreen=True)) == 1
    assert len(repos.listar_publicaciones(evergreen=False)) == 2


# --------------------------------------------------------------------------- #
# Borrado y edicion (incl. cambio de marca mueve de carpeta)                  #
# --------------------------------------------------------------------------- #


def test_borrar_publicacion(base):
    pub = repos.crear_publicacion("unotv", "x")
    assert repos.borrar_publicacion(pub["id"]) is True
    assert repos.obtener_publicacion(pub["id"]) is None
    assert repos.borrar_publicacion(pub["id"]) is False


def test_editar_grupo_cambia_de_marca_mueve_fichero(base):
    g = repos.crear_grupo_hashtags("G", marca="unotv", hashtags=["#a"])
    act = repos.actualizar_grupo_hashtags(g["id"], {"marca": "claro-sports"})
    assert act["marca"] == "claro-sports"
    # El fichero ya no esta en unotv y si en claro-sports.
    assert not (base / "datos" / "unotv" / "hashtags" / f"{g['id']}.yaml").exists()
    assert (base / "datos" / "claro-sports" / "hashtags" / f"{g['id']}.yaml").exists()
    assert repos.obtener_grupo_hashtags(g["id"])["marca"] == "claro-sports"


# --------------------------------------------------------------------------- #
# Items RSS vistos por marca                                                  #
# --------------------------------------------------------------------------- #


def test_items_vistos_por_marca(base):
    fr = repos.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    repos.marcar_item(fr["id"], "guid-1", True)
    repos.marcar_item(fr["id"], "guid-2", True)
    assert repos.claves_vistas(fr["id"]) == {"guid-1", "guid-2"}
    # Vive en el .keni de la marca de la fuente.
    ruta = base / "datos" / "unotv" / ".keni" / "rss-vistos.yaml"
    assert ruta.is_file()
    repos.marcar_item(fr["id"], "guid-1", False)
    assert repos.claves_vistas(fr["id"]) == {"guid-2"}
    # Borrar la fuente limpia sus items vistos.
    repos.borrar_fuente_rss(fr["id"])
    assert repos.claves_vistas(fr["id"]) == set()
