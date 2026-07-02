"""Tests de la purga de borradores MUERTOS del tablero (retencion a N dias, def 90).

Politica: un tema auto-generado (origen pipeline/portal/historia) SIN NINGUNA huella humana se
borra pasados N dias; cualquier señal de "tocado" lo conserva para siempre, igual que cualquier
origen fuera de la allowlist. Postgres (`entorno`). La edad se fija por SQL directo sobre
`publicacion.creado` (timestamptz) para no depender del reloj.
"""

from __future__ import annotations

from keni_consola import limpiador_piezas, repos
from keni_consola.db import latidos as db_latidos
from keni_consola.db import purga_piezas as db_purga_piezas

_MARCA = "claro-sports"
# Muy anterior a cualquier retencion razonable.
_VIEJO = "2020-01-01T00:00:00+00:00"


def _tema(origen: str = "pipeline", marca: str = _MARCA, **kw):
    return repos.crear_publicacion(
        clase="contenido", titulo="Tema de prueba", marca=marca, origen=origen, **kw
    )


def _pieza(publicacion_id: str, red: str = "instagram", **kw):
    kw.setdefault("estado", "borrador")
    return repos.crear_pieza_fila(publicacion_id=publicacion_id, red=red, **kw)


def _envejecer(publicacion_id: str, creado: str = _VIEJO) -> None:
    con = db_purga_piezas._conectar()
    try:
        con.execute(
            "UPDATE publicacion SET creado = ? WHERE id = ?", (creado, publicacion_id)
        )
        con.commit()
    finally:
        con.close()


def _sql(sentencia: str, params: tuple = ()) -> None:
    con = db_purga_piezas._conectar()
    try:
        con.execute(sentencia, params)
        con.commit()
    finally:
        con.close()


def _muerto_viejo(origen: str = "pipeline", marca: str = _MARCA) -> tuple[str, str]:
    """Tema viejo + pieza en borrador, sin ninguna huella humana. Devuelve (tema_id, pieza_id)."""
    tema = _tema(origen=origen, marca=marca)
    pieza = _pieza(tema["id"])
    _envejecer(tema["id"])
    return tema["id"], pieza["id"]


# --------------------------------------------------------------------------- #
# Purga completa del muerto + cascada                                          #
# --------------------------------------------------------------------------- #


def test_purga_el_borrador_muerto_viejo_con_cascada_completa(entorno):
    """Un tema de maquina viejo y jamas tocado cae ENTERO: tema, piezas y puente de etiquetas."""
    tema = _tema()
    p1 = _pieza(tema["id"], red="instagram")
    p2 = _pieza(tema["id"], red="facebook")
    # Etiquetas que estampa la MAQUINA: taxonomia (clase categoria) + marcador autogen. NO son
    # huella humana y no salvan al tema.
    cat = repos.crear_etiqueta(nombre="Futbol", clase="categoria", marca=_MARCA)
    marcador = repos.crear_etiqueta(nombre="autogen")  # clase por defecto 'campania'
    repos.asignar_etiqueta(tema["id"], cat["id"])
    repos.asignar_etiqueta(tema["id"], marcador["id"])
    _envejecer(tema["id"])

    res = db_purga_piezas.purgar_borradores_muertos(90)

    assert res["purgadas"] == 1
    assert res["por_marca"] == {_MARCA: 1}
    assert repos.obtener_publicacion(tema["id"]) is None
    assert repos.obtener_pieza_fila(p1["id"]) is None
    assert repos.obtener_pieza_fila(p2["id"]) is None
    assert repos.etiqueta_ids_de_contenido(tema["id"]) == []


def test_purga_por_origen_y_marca_mixtos(entorno):
    """Purga cada origen de la allowlist y agrupa el conteo por marca."""
    for origen in db_purga_piezas.ORIGENES_PURGABLES:
        _muerto_viejo(origen=origen)
    _muerto_viejo(origen="pipeline", marca="unotv")

    res = db_purga_piezas.purgar_borradores_muertos(90)

    assert res["purgadas"] == 4
    assert res["por_marca"] == {_MARCA: 3, "unotv": 1}


def test_no_purga_lo_reciente(entorno):
    """El mismo tema muerto pero DENTRO de la ventana de retencion se conserva."""
    tema = _tema()
    _pieza(tema["id"])  # creado = ahora: dentro de la ventana

    assert db_purga_piezas.purgar_borradores_muertos(90)["purgadas"] == 0
    assert repos.obtener_publicacion(tema["id"]) is not None


def test_no_purga_origenes_fuera_de_la_allowlist(entorno):
    """`equipo`, alta tecleada ('') y hasta origenes automaticos NO enumerados se conservan."""
    for origen in ("equipo", "", "post-directo", "presidencia", "clips", "rss", "evergreen"):
        tema = _tema(origen=origen)
        _pieza(tema["id"])
        _envejecer(tema["id"])

    assert db_purga_piezas.purgar_borradores_muertos(90)["purgadas"] == 0


# --------------------------------------------------------------------------- #
# Cada señal de "tocado" protege POR SI SOLA                                   #
# --------------------------------------------------------------------------- #


def _sigue_vivo(tema_id: str) -> bool:
    db_purga_piezas.purgar_borradores_muertos(90)
    return repos.obtener_publicacion(tema_id) is not None


def test_responsable_protege(entorno):
    tema_id, _ = _muerto_viejo()
    repos.reclamar_publicacion(tema_id, responsable_id="u1", responsable_nombre="Ana")
    assert _sigue_vivo(tema_id)


def test_estado_del_padre_avanzado_protege(entorno):
    tema_id, _ = _muerto_viejo()
    repos.actualizar_publicacion(tema_id, {"estado": "en_curso"})
    assert _sigue_vivo(tema_id)


def test_pieza_fuera_de_borrador_protege(entorno):
    tema_id, pieza_id = _muerto_viejo()
    _sql("UPDATE pieza SET estado = 'en_revision' WHERE id = ?", (pieza_id,))
    assert _sigue_vivo(tema_id)


def test_traza_de_revision_o_programacion_en_la_pieza_protege(entorno):
    for campo, valor in (
        ("fecha_programada", "2020-02-01T10:00:00"),
        ("enviado_a_revision_en", "2020-02-01T10:00:00"),
        ("revisor_id", "u1"),
        ("id_post_metricool", "mp-1"),
        ("enlace", "https://x.test/post"),
    ):
        tema_id, pieza_id = _muerto_viejo()
        _sql(f"UPDATE pieza SET {campo} = ? WHERE id = ?", (valor, pieza_id))
        assert _sigue_vivo(tema_id), campo


def test_imagen_autorizada_por_humano_protege(entorno):
    tema_id, pieza_id = _muerto_viejo()
    _sql("UPDATE pieza SET imagen_autorizada = 1 WHERE id = ?", (pieza_id,))
    assert _sigue_vivo(tema_id)


def test_comentario_protege(entorno):
    tema_id, _ = _muerto_viejo()
    repos.crear_comentario(
        publicacion_id=tema_id, texto="ojo con esto", autor={"id": "u1", "usuario": "Ana"}
    )
    assert _sigue_vivo(tema_id)


def test_historial_de_copy_protege(entorno):
    tema_id, pieza_id = _muerto_viejo()
    repos.registrar_copy_version(
        pieza_id=pieza_id, publicacion_id=tema_id, copy="version previa",
        autor={"id": "u1", "usuario": "Ana"},
    )
    assert _sigue_vivo(tema_id)


def test_cadena_de_aprobacion_protege(entorno):
    tema_id, pieza_id = _muerto_viejo()
    repos.crear_cadena_aprobacion(
        pieza_id=pieza_id, publicacion_id=tema_id, etiquetas=["Edición"]
    )
    assert _sigue_vivo(tema_id)


def test_version_de_documento_del_editor_protege(entorno):
    tema_id, pieza_id = _muerto_viejo()
    repos.crear_documento_version(
        publicacion_id=tema_id, pieza_id=pieza_id, documento="{}",
        autor={"id": "u1", "usuario": "Ana"},
    )
    assert _sigue_vivo(tema_id)


def test_etiqueta_humana_protege(entorno):
    """Una etiqueta que NO es taxonomia de maquina ni marcador autogen cuenta como huella."""
    tema_id, _ = _muerto_viejo()
    campania = repos.crear_etiqueta(nombre="Mundial 2026", clase="campania", marca=_MARCA)
    repos.asignar_etiqueta(tema_id, campania["id"])
    assert _sigue_vivo(tema_id)


def test_id_post_metricool_del_padre_protege(entorno):
    tema_id, _ = _muerto_viejo()
    _sql("UPDATE publicacion SET id_post_metricool = ? WHERE id = ?", ("mp-9", tema_id))
    assert _sigue_vivo(tema_id)


def test_tarea_libre_nunca_se_purga(entorno):
    tema = repos.crear_publicacion(clase="tarea", titulo="Tarea", marca=_MARCA, origen="pipeline")
    _envejecer(tema["id"])
    assert _sigue_vivo(tema["id"])


# --------------------------------------------------------------------------- #
# Apagado (0 dias), gate vivo y latido del barrido                             #
# --------------------------------------------------------------------------- #


def test_cero_dias_apaga_la_purga(entorno):
    tema_id, _ = _muerto_viejo()
    assert db_purga_piezas.purgar_borradores_muertos(0)["purgadas"] == 0
    assert repos.obtener_publicacion(tema_id) is not None


def test_ejecutar_purga_respeta_el_gate_vivo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PIEZAS_PURGA_DIAS", "0")
    tema_id, _ = _muerto_viejo()

    res = limpiador_piezas.ejecutar_purga()

    assert res["activo"] is False
    assert res["purgadas"] == 0
    assert repos.obtener_publicacion(tema_id) is not None
    # Apagada NO deja latido (igual que un daemon gateado OFF).
    assert db_latidos.listar_barridos(limpiador_piezas.DAEMON) == []


def test_ejecutar_purga_activa_purga_y_deja_historial(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PIEZAS_PURGA_DIAS", "90")
    tema_id, _ = _muerto_viejo()

    res = limpiador_piezas.ejecutar_purga()

    assert res["activo"] is True
    assert res["purgadas"] == 1
    assert repos.obtener_publicacion(tema_id) is None
    barridos = db_latidos.listar_barridos(limpiador_piezas.DAEMON)
    assert len(barridos) == 1
    assert barridos[0]["ok"] is True
    assert _MARCA in barridos[0]["resumen"]


def test_config_default_y_clamp(entorno, monkeypatch):
    from keni_consola import config

    monkeypatch.delenv("KENI_PIEZAS_PURGA_DIAS", raising=False)
    assert config.piezas_purga_dias() == 90
    monkeypatch.setenv("KENI_PIEZAS_PURGA_DIAS", "-5")
    assert config.piezas_purga_dias() == 0
