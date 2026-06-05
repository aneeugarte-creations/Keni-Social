"""Tests del HISTÓRICO de métricas por pieza (`metricas_pieza_snapshots`, ADR 0007).

Serie temporal GENERAL (todas las piezas, no solo el módulo Comercial), alimentada por el
daemon de refresco. Cubre: escritura/lectura con los campos correctos, idempotencia por
`(pieza_id, ts)`, filtros de `listar_snapshots_piezas`, poda por retención (corte recibido
como parámetro, sin reloj del sistema en db.py) y el hook del refresco. SKIP sin Postgres
(fixture `pg` autodescubierta vía `pytest_plugins` en conftest).
"""

from __future__ import annotations

from datetime import datetime

from keni_consola import db, metricas_pieza, repos


# --------------------------------------------------------------------------- #
# Esquema + escritura/lectura básica                                          #
# --------------------------------------------------------------------------- #


def test_esquema_se_crea_y_serie_vacia(pg):
    # La primera operación crea/migra el esquema sin error y la serie de una pieza
    # inexistente es vacía.
    assert db.serie_pieza("no-existe") == []


def test_registrar_y_leer_serie_con_campos(pg):
    metricas = {
        "visualizaciones": 1000,
        "interacciones": 120,
        "alcance": 800,
        "engagement_pct": 12.5,
        "likes": 90,
        "comentarios": 12,
        "compartidos": 10,
        "guardados": 8,
        "video_views": 950,
        "tiempo_medio_vis_s": 14,
        "clics_enlace": 5,
        # `seguidores_netos_atribuidos` ausente a propósito -> debe leerse como 0.
    }
    assert db.registrar_snapshot_pieza(
        "post-1", "unotv", "instagram", "reel", "2026-06-01T08:00:00", metricas
    ) is True

    serie = db.serie_pieza("post-1")
    assert len(serie) == 1
    p = serie[0]
    assert p["pieza_id"] == "post-1"
    assert p["marca"] == "unotv" and p["red"] == "instagram" and p["formato"] == "reel"
    assert p["ts"] == "2026-06-01T08:00:00"
    assert p["visualizaciones"] == 1000 and p["interacciones"] == 120 and p["alcance"] == 800
    assert p["engagement_pct"] == 12.5  # REAL
    assert p["likes"] == 90 and p["comentarios"] == 12
    assert p["video_views"] == 950 and p["tiempo_medio_vis_s"] == 14 and p["clics_enlace"] == 5
    assert p["seguidores_netos_atribuidos"] == 0  # ausente -> 0


def test_serie_ordenada_por_ts(pg):
    db.registrar_snapshot_pieza("p", "m", "r", "reel", "2026-06-01T12:00:00", {"interacciones": 30})
    db.registrar_snapshot_pieza("p", "m", "r", "reel", "2026-06-01T08:00:00", {"interacciones": 10})
    db.registrar_snapshot_pieza("p", "m", "r", "reel", "2026-06-01T10:00:00", {"interacciones": 20})
    serie = db.serie_pieza("p")
    assert [s["ts"] for s in serie] == [
        "2026-06-01T08:00:00",
        "2026-06-01T10:00:00",
        "2026-06-01T12:00:00",
    ]
    assert [s["interacciones"] for s in serie] == [10, 20, 30]


def test_idempotencia_por_pieza_ts(pg):
    assert db.registrar_snapshot_pieza(
        "post-x", "m", "r", "foto", "2026-06-02T00:00:00", {"interacciones": 5}
    ) is True
    # Mismo (pieza_id, ts): el índice ÚNICO -> ON CONFLICT DO NOTHING -> no inserta (False).
    assert db.registrar_snapshot_pieza(
        "post-x", "m", "r", "foto", "2026-06-02T00:00:00", {"interacciones": 999}
    ) is False
    serie = db.serie_pieza("post-x")
    assert len(serie) == 1 and serie[0]["interacciones"] == 5  # gana el primero


def test_metricas_ausentes_defaultean_a_cero(pg):
    assert db.registrar_snapshot_pieza("p0", "m", "r", "", "2026-06-01T00:00:00", {}) is True
    serie = db.serie_pieza("p0")
    p = serie[0]
    for col, _tipo in db._METRICAS_PIEZA_SNAPSHOT:
        assert p[col] == 0


# --------------------------------------------------------------------------- #
# Filtros agregados                                                           #
# --------------------------------------------------------------------------- #


def test_listar_snapshots_piezas_filtros(pg):
    db.registrar_snapshot_pieza("a", "unotv", "instagram", "reel", "2026-06-01T00:00:00", {})
    db.registrar_snapshot_pieza("b", "unotv", "facebook", "foto", "2026-06-02T00:00:00", {})
    db.registrar_snapshot_pieza("c", "clarosports", "instagram", "reel", "2026-06-03T00:00:00", {})

    # Sin filtros: todo, ordenado por ts.
    todo = db.listar_snapshots_piezas()
    assert [s["pieza_id"] for s in todo] == ["a", "b", "c"]

    # Por marca.
    assert {s["pieza_id"] for s in db.listar_snapshots_piezas(marca="unotv")} == {"a", "b"}
    # Por red.
    assert {s["pieza_id"] for s in db.listar_snapshots_piezas(red="instagram")} == {"a", "c"}
    # Marca + red.
    assert [s["pieza_id"] for s in db.listar_snapshots_piezas(marca="unotv", red="instagram")] == ["a"]
    # Ventana de ts (inclusiva).
    ventana = db.listar_snapshots_piezas(desde="2026-06-02T00:00:00", hasta="2026-06-02T23:59:59")
    assert [s["pieza_id"] for s in ventana] == ["b"]


# --------------------------------------------------------------------------- #
# Poda por retención (corte recibido como parámetro)                          #
# --------------------------------------------------------------------------- #


def test_podar_borra_antiguos_conserva_recientes(pg):
    # ahora = 2026-06-10; retención 90 días -> corte = 2026-03-12.
    db.registrar_snapshot_pieza("viejo", "m", "r", "reel", "2026-01-01T00:00:00", {})  # > 90d
    db.registrar_snapshot_pieza("borde", "m", "r", "reel", "2026-03-01T00:00:00", {})  # > 90d
    db.registrar_snapshot_pieza("nuevo", "m", "r", "reel", "2026-06-09T00:00:00", {})  # reciente

    borrados = db.podar_snapshots_piezas(90, "2026-06-10T00:00:00")
    assert borrados == 2

    restantes = {s["pieza_id"] for s in db.listar_snapshots_piezas()}
    assert restantes == {"nuevo"}


def test_podar_retencion_no_positiva_no_borra(pg):
    db.registrar_snapshot_pieza("x", "m", "r", "reel", "2020-01-01T00:00:00", {})
    assert db.podar_snapshots_piezas(0, "2026-06-10T00:00:00") == 0
    assert len(db.listar_snapshots_piezas()) == 1


def test_podar_ahora_invalido_no_borra(pg):
    db.registrar_snapshot_pieza("x", "m", "r", "reel", "2020-01-01T00:00:00", {})
    assert db.podar_snapshots_piezas(90, "no-es-iso") == 0
    assert len(db.listar_snapshots_piezas()) == 1


# --------------------------------------------------------------------------- #
# Repos wrappers                                                              #
# --------------------------------------------------------------------------- #


def test_repos_wrappers_delegan(pg):
    assert repos.registrar_snapshot_pieza(
        "rp", "m", "r", "reel", "2026-06-01T00:00:00", {"interacciones": 7}
    ) is True
    serie = repos.serie_pieza("rp")
    assert len(serie) == 1 and serie[0]["interacciones"] == 7
    assert [s["pieza_id"] for s in repos.listar_snapshots_piezas(marca="m")] == ["rp"]
    assert repos.podar_snapshots_piezas(1, "2030-01-01T00:00:00") == 1


# --------------------------------------------------------------------------- #
# Hook del refresco: recalcular escribe el histórico cuando hay datos          #
# --------------------------------------------------------------------------- #


def test_recalcular_escribe_historico_cuando_encontrado(pg, monkeypatch):
    """Cuando `recalcular` encuentra la pieza, además de cachear escribe un punto histórico."""
    payload = {
        "id_post": "ID-9",
        "plataforma": "instagram",
        "encontrado": True,
        "visualizaciones": 500,
        "interacciones": 60,
        "engagement_pct": 12.0,
        "alcance": 400,
        "likes": 40,
        "comentarios": 5,
        "compartidos": 4,
        "guardados": 3,
        "video_views": 480,
        "tiempo_medio_vis_s": 11,
        "clics_enlace": 2,
        "seguidores_netos_atribuidos": 1,
        "formato": "reel",
        "fuente": "muestra",
    }
    # Evita golpear la fuente real: el `_calcular` interno usa servicio.construir_metricas_pieza.
    monkeypatch.setattr(
        "keni_metricas.servicio.construir_metricas_pieza",
        lambda *a, **k: dict(payload),
    )
    # Reloj determinista para el ts del snapshot.
    monkeypatch.setattr(metricas_pieza, "_ahora", lambda: datetime(2026, 6, 5, 9, 0, 0))

    datos = metricas_pieza.recalcular("unotv", "instagram", "ID-9")
    assert datos["encontrado"] is True

    serie = db.serie_pieza("ID-9")
    assert len(serie) == 1
    p = serie[0]
    assert p["ts"] == "2026-06-05T09:00:00"
    assert p["marca"] == "unotv" and p["red"] == "instagram" and p["formato"] == "reel"
    assert p["visualizaciones"] == 500 and p["interacciones"] == 60
    assert p["engagement_pct"] == 12.0 and p["likes"] == 40


def test_recalcular_no_escribe_historico_si_no_encontrado(pg, monkeypatch):
    monkeypatch.setattr(
        "keni_metricas.servicio.construir_metricas_pieza",
        lambda *a, **k: {"encontrado": False, "interacciones": 0},
    )
    datos = metricas_pieza.recalcular("unotv", "instagram", "ID-NO")
    assert datos["encontrado"] is False
    assert db.serie_pieza("ID-NO") == []


# --------------------------------------------------------------------------- #
# Tope / downsampling de la serie temporal (cota de puntos para las gráficas)  #
# --------------------------------------------------------------------------- #


def _sembrar_serie(pieza_id: str, n: int) -> list[str]:
    """Inserta `n` snapshots de una pieza con ts crecientes; devuelve los ts en orden ASC."""
    tss = [f"2026-06-01T{h // 60:02d}:{h % 60:02d}:00" for h in range(n)]
    for i, ts in enumerate(tss):
        db.registrar_snapshot_pieza(pieza_id, "m", "r", "reel", ts, {"interacciones": i})
    return tss


def test_serie_pieza_capada_al_maximo_con_ultimo_punto(pg, monkeypatch):
    # Con un tope bajo, una serie más larga que el tope devuelve a lo sumo `tope` puntos, y
    # SIEMPRE incluye el ÚLTIMO (el más reciente, el dato actual) en orden ASC de graficado.
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "5")
    tss = _sembrar_serie("cap", 20)
    serie = db.serie_pieza("cap")
    assert len(serie) == 5
    # Son los 5 MÁS RECIENTES, en orden ascendente, con el último punto presente.
    assert [s["ts"] for s in serie] == tss[-5:]
    assert serie[-1]["ts"] == tss[-1]
    assert serie[-1]["interacciones"] == 19


def test_serie_pieza_por_debajo_del_tope_intacta(pg, monkeypatch):
    # Si la serie es más corta que el tope, se devuelve completa (sin recortar) y ordenada ASC.
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "100")
    tss = _sembrar_serie("corta", 3)
    serie = db.serie_pieza("corta")
    assert [s["ts"] for s in serie] == tss


def test_serie_pieza_limite_cero_devuelve_completa(pg, monkeypatch):
    # `limite<=0` => SIN tope: serie COMPLETA aunque exceda el cap por defecto (ruta para
    # barridos/exportaciones que necesitan todo el histórico).
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "5")
    tss = _sembrar_serie("full", 12)
    serie = db.serie_pieza("full", limite=0)
    assert [s["ts"] for s in serie] == tss


def test_serie_pieza_limite_explicito(pg, monkeypatch):
    # Un `limite>0` explícito gana al cap por defecto (los N más recientes).
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "500")
    tss = _sembrar_serie("explic", 10)
    serie = db.serie_pieza("explic", limite=3)
    assert [s["ts"] for s in serie] == tss[-3:]


def test_listar_snapshots_piezas_capada(pg, monkeypatch):
    # El cap también aplica al agregado filtrado, conservando el punto más reciente del conjunto.
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "4")
    tss = _sembrar_serie("agg", 15)
    filas = db.listar_snapshots_piezas(marca="m")
    assert len(filas) == 4
    assert [s["ts"] for s in filas] == tss[-4:]
    # `limite=0` devuelve todo el conjunto filtrado.
    assert len(db.listar_snapshots_piezas(marca="m", limite=0)) == 15


def test_serie_comercial_capada_con_ultimo_punto(pg, monkeypatch):
    # Misma cota para la serie comercial: cap por defecto, último punto garantizado; `limite=0`
    # devuelve la serie completa (la usa el cruce de objetivo, que recorre TODO el histórico).
    monkeypatch.setenv("KENI_METRICAS_SERIE_MAX", "5")
    pub = repos.crear_publicacion_comercial(id_post_metricool="POST-1", marca="m", red="r")
    tss = [f"2026-06-01T{h:02d}:00:00" for h in range(12)]
    for i, ts in enumerate(tss):
        db.registrar_snapshot_comercial(pub["id"], ts, interacciones=i, alcance=i)
    serie = db.listar_snapshots_comerciales(pub["id"])
    assert len(serie) == 5
    assert [s["ts"] for s in serie] == tss[-5:]
    assert len(db.listar_snapshots_comerciales(pub["id"], limite=0)) == 12
