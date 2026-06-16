"""Tests del dominio Comercial: captura real, aviso y reporte.

Todo OFFLINE y determinista. Usa la fixture `entorno` (conftest) para aislar el
SQLite en tmp; no toca la red ni el disco real. AQUI NO HAY DATOS SINTETICOS:
las lecturas "reales" se inyectan monkeypatcheando `metricas_pieza.recalcular`
(la frontera con Metricool); sin datos en la fuente, la serie queda VACIA.
"""

from __future__ import annotations

from datetime import date, timedelta

from keni_consola import comercial, db

URL = "https://facebook.com/unotv/posts/123456"


def _hace_dias(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _con_lectura(monkeypatch, interacciones=1500, visualizaciones=42000, **extra):
    """Inyecta una lectura "real" fija en la frontera con Metricool."""
    lectura = {
        "encontrado": True,
        "interacciones": interacciones,
        "visualizaciones": visualizaciones,
        **extra,
    }
    monkeypatch.setattr(comercial.metricas_pieza, "recalcular", lambda m, r, i: lectura)
    return lectura


def test_registrar_sin_fuente_deja_serie_vacia_y_ceros(entorno):
    """Sin dato en la fuente NO se inventa nada: serie vacia y resumen en ceros."""
    pub = comercial.registrar(URL, titulo="Spot", publicado=_hace_dias(14), objetivo=0)
    assert comercial.serie(pub["id"]) == []
    actual = comercial.resumen_actual(pub)
    assert actual["interacciones"] == 0
    assert actual["visualizaciones"] == 0
    assert actual["alcance"] == 0


def test_aviso_se_marca_cuando_supera_objetivo(entorno, monkeypatch):
    """Con una lectura real por encima de la meta, queda 'alcanzado' con su instante."""
    _con_lectura(monkeypatch, interacciones=1500)
    pub = comercial.registrar(
        id_post_metricool="post-aviso", marca="unotv", red="instagram",
        publicado=_hace_dias(20), metrica_objetivo="interacciones", objetivo=100,
    )
    assert pub["aviso_en"]  # cruce detectado y marcado
    assert comercial.evaluar_aviso(pub) is True


def test_aviso_no_se_marca_si_no_se_alcanza(entorno, monkeypatch):
    _con_lectura(monkeypatch, interacciones=10, visualizaciones=100)
    pub = comercial.registrar(
        id_post_metricool="post-bajo", marca="unotv", red="instagram",
        publicado=_hace_dias(20), metrica_objetivo="interacciones", objetivo=999_999_999,
    )
    assert pub["aviso_en"] == ""
    assert comercial.evaluar_aviso(pub) is False


def test_capturar_pendientes_solo_activas(entorno):
    """La captura programada solo toca piezas activas (no pausadas/cerradas)."""
    comercial.registrar(URL + "/a", estado="activa", publicado=_hace_dias(3))
    pausada = comercial.registrar(URL + "/b", estado="pausada", publicado=_hace_dias(3))

    procesadas = comercial.capturar_pendientes()
    assert procesadas == 1  # solo la activa

    # La pausada no cambia su serie (vacia: sin fuente no hay snapshots).
    assert comercial.serie(pausada["id"]) == []


def test_reporte_publicacion_estructura(entorno, monkeypatch):
    _con_lectura(monkeypatch, interacciones=1500, visualizaciones=42000)
    pub = comercial.registrar(
        id_post_metricool="post-rep", marca="unotv", red="instagram",
        titulo="Lanzamiento", cliente="ACME", campania="Verano", publicado=_hace_dias(7),
        metrica_objetivo="interacciones", objetivo=100,
    )
    rep = comercial.reporte_publicacion(pub)
    assert rep["tipo"] == "publicacion"
    assert rep["publicacion"]["cliente"] == "ACME"
    assert rep["objetivo"]["alcanzado"] is True
    assert "es_muestra" not in rep  # no existen flags de muestra: cifras reales o nada
    md = comercial.render_markdown_reporte(rep)
    assert "Reporte comercial" in md
    assert "Lanzamiento" in md
    assert "Engagement" in md
    assert "Datos de muestra" not in md


def test_reporte_campania_agrega(entorno, monkeypatch):
    _con_lectura(monkeypatch, interacciones=200, visualizaciones=9000)
    comercial.registrar(
        id_post_metricool="post-c1", marca="unotv", red="instagram",
        campania="Mundial", publicado=_hace_dias(10),
    )
    comercial.registrar(
        id_post_metricool="post-c2", marca="unotv", red="instagram",
        campania="Mundial", publicado=_hace_dias(10),
    )
    pubs = db.listar_publicaciones_comerciales(campania="Mundial")
    rep = comercial.reporte_campania(pubs, campania="Mundial")
    assert rep["tipo"] == "campania"
    assert rep["total"]["piezas"] == 2
    assert rep["total"]["visualizaciones"] == 18000
    assert "es_muestra" not in rep
    md = comercial.render_markdown_reporte(rep)
    assert "Detalle por pieza" in md
    assert "Datos de muestra" not in md


def test_post_real_arranca_serie_hacia_delante(entorno, monkeypatch):
    """La captura lee el dato real y la serie NO se rellena hacia atrás."""
    lectura = {
        "interacciones": 1500,
        "visualizaciones": 42000,
        "encontrado": True,
        # Desglose granular por pieza + formato estatico, tal como lo da la fuente.
        "likes": 1200,
        "comentarios": 150,
        "compartidos": 90,
        "guardados": 60,
        "video_views": 38000,
        "tiempo_medio_vis_s": 9,
        "clics_enlace": 30,
        "seguidores_netos_atribuidos": 12,
        "formato": "reel",
    }
    monkeypatch.setattr(comercial.metricas_pieza, "recalcular", lambda m, r, i: lectura)

    pub = comercial.registrar(
        id_post_metricool="post-1",
        marca="unotv",
        red="instagram",
        titulo="Real",
        publicado=_hace_dias(30),
        metrica_objetivo="interacciones",
        objetivo=1000,
    )
    serie = comercial.serie(pub["id"])
    assert len(serie) == 1  # solo el punto "ahora": Metricool no da histórico por pieza
    assert serie[0]["visualizaciones"] == 42000
    assert serie[0]["alcance"] == 0  # el alcance no viene por pieza en modo real
    # El desglose granular del snapshot se persiste y se relee.
    assert serie[0]["likes"] == 1200
    assert serie[0]["comentarios"] == 150
    assert serie[0]["video_views"] == 38000
    assert serie[0]["seguidores_netos_atribuidos"] == 12
    # El formato estatico se capturó en la primera captura real.
    assert pub["formato"] == "reel"

    actual = comercial.resumen_actual(pub)
    assert actual["visualizaciones"] == 42000
    assert actual["interacciones"] == 1500
    assert actual["engagement_pct"] == round(1500 / 42000 * 100, 2)
    assert pub["aviso_en"]  # 1500 interacciones >= objetivo 1000


def test_captura_real_sin_datos_no_inserta(entorno, monkeypatch):
    """Si Metricool aún no tiene datos del post, NO se inserta un snapshot falso."""
    monkeypatch.setattr(
        comercial.metricas_pieza,
        "recalcular",
        lambda m, r, i: {"encontrado": False, "interacciones": 0, "visualizaciones": 0},
    )
    pub = comercial.registrar(
        id_post_metricool="post-x", marca="unotv", red="instagram", publicado=_hace_dias(1)
    )
    assert comercial.serie(pub["id"]) == []  # serie vacía, sin ceros falsos
    actual = comercial.resumen_actual(pub)
    assert actual["interacciones"] == 0
    assert actual["visualizaciones"] == 0


def test_reporte_lleva_procedencia_y_volumen(entorno, monkeypatch):
    """El reporte lleva la procedencia en `fuente` y el volumen en visualizaciones."""
    monkeypatch.setattr(comercial, "fuente_actual", lambda: "metricool")
    _con_lectura(monkeypatch, interacciones=200, visualizaciones=9000)
    pub = comercial.registrar(
        id_post_metricool="post-2", marca="unotv", red="instagram", titulo="Pieza"
    )
    rep = comercial.reporte_publicacion(pub)
    assert rep["fuente"] == "metricool"
    md = comercial.render_markdown_reporte(rep)
    assert "Datos de muestra" not in md
    assert "Visualizaciones" in md
