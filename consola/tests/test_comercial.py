"""Tests del dominio Comercial: curva de muestra, captura, aviso y reporte.

Todo OFFLINE y determinista. Usa la fixture `entorno` (conftest) para aislar el
SQLite en tmp; no toca la red ni el disco real.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from keni_consola import comercial, db

URL = "https://facebook.com/unotv/posts/123456"


def _hace_dias(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def test_metrica_en_monotona_y_acotada():
    """La curva sintetica crece con el tiempo, parte de 0 y no se dispara."""
    publicado = _hace_dias(10)
    inicio = datetime.combine(date.today() - timedelta(days=10), datetime.min.time())
    inter0, alc0 = comercial.metrica_en(URL, publicado, inicio)
    assert (inter0, alc0) == (0, 0)  # en el instante de publicacion, cero

    inter_mid, alc_mid = comercial.metrica_en(URL, publicado, datetime.now() - timedelta(days=5))
    inter_now, alc_now = comercial.metrica_en(URL, publicado, datetime.now())
    assert alc_mid > 0
    assert alc_now >= alc_mid  # monotona creciente
    assert inter_now >= inter_mid
    # Las interacciones son una fraccion del alcance (engagement < 10 %).
    assert 0 < inter_now < alc_now


def test_registrar_siembra_historico(entorno):
    """Registrar una pieza siembra su serie y deja un valor consultable."""
    pub = comercial.registrar(URL, titulo="Spot", publicado=_hace_dias(14), objetivo=0)
    serie = comercial.serie(pub["id"])
    assert len(serie) >= 2
    # La serie es no decreciente (acumulada).
    alcances = [s["alcance"] for s in serie]
    assert alcances == sorted(alcances)
    actual = comercial.resumen_actual(pub)
    assert actual["alcance"] > 0
    assert actual["interacciones"] > 0


def test_aviso_se_marca_cuando_supera_objetivo(entorno):
    """Con un objetivo bajo en una pieza antigua, queda 'alcanzado' con su instante."""
    pub = comercial.registrar(
        URL, publicado=_hace_dias(20), metrica_objetivo="interacciones", objetivo=100
    )
    assert pub["aviso_en"]  # cruce detectado y marcado
    assert comercial.evaluar_aviso(pub) is True


def test_aviso_no_se_marca_si_no_se_alcanza(entorno):
    pub = comercial.registrar(
        URL, publicado=_hace_dias(20), metrica_objetivo="alcance", objetivo=999_999_999
    )
    assert pub["aviso_en"] == ""
    assert comercial.evaluar_aviso(pub) is False


def test_capturar_pendientes_solo_activas(entorno):
    """La captura programada solo toca piezas activas (no pausadas/cerradas)."""
    activa = comercial.registrar(URL + "/a", estado="activa", publicado=_hace_dias(3))
    pausada = comercial.registrar(URL + "/b", estado="pausada", publicado=_hace_dias(3))

    n_antes_activa = len(comercial.serie(activa["id"]))
    n_antes_pausada = len(comercial.serie(pausada["id"]))

    # Forzamos que el snapshot "ahora" sea NUEVO (otro minuto) avanzando el reloj logico
    # no es posible aqui; en su lugar comprobamos el conteo de piezas procesadas.
    procesadas = comercial.capturar_pendientes()
    assert procesadas == 1  # solo la activa

    # La pausada no cambia su serie.
    assert len(comercial.serie(pausada["id"])) == n_antes_pausada
    assert len(comercial.serie(activa["id"])) >= n_antes_activa


def test_reporte_publicacion_estructura(entorno):
    pub = comercial.registrar(
        URL, titulo="Lanzamiento", cliente="ACME", campania="Verano", publicado=_hace_dias(7),
        metrica_objetivo="interacciones", objetivo=100,
    )
    rep = comercial.reporte_publicacion(pub)
    assert rep["tipo"] == "publicacion"
    assert rep["publicacion"]["cliente"] == "ACME"
    assert rep["objetivo"]["alcanzado"] is True
    # Cifras sintéticas: el reporte se marca como dato de muestra (#124).
    assert rep["es_muestra"] is True
    assert rep["fuente"] == "muestra"
    md = comercial.render_markdown_reporte(rep)
    assert "Reporte comercial" in md
    assert "Lanzamiento" in md
    assert "Engagement" in md
    assert "Datos de muestra" in md


def test_reporte_campania_agrega(entorno):
    comercial.registrar(URL + "/1", campania="Mundial", publicado=_hace_dias(10))
    comercial.registrar(URL + "/2", campania="Mundial", publicado=_hace_dias(10))
    pubs = db.listar_publicaciones_comerciales(campania="Mundial")
    rep = comercial.reporte_campania(pubs, campania="Mundial")
    assert rep["tipo"] == "campania"
    assert rep["total"]["piezas"] == 2
    assert rep["total"]["alcance"] > 0
    assert rep["es_muestra"] is True
    assert rep["fuente"] == "muestra"
    md = comercial.render_markdown_reporte(rep)
    assert "Detalle por pieza" in md
    assert "Datos de muestra" in md


def test_post_real_arranca_serie_hacia_delante(entorno, monkeypatch):
    """En modo real (Metricool) la captura lee el dato real y la serie NO se rellena hacia atrás."""
    monkeypatch.setattr(comercial, "fuente_actual", lambda: "metricool")
    lectura = {"interacciones": 1500, "visualizaciones": 42000, "encontrado": True}
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

    actual = comercial.resumen_actual(pub)
    assert actual["visualizaciones"] == 42000
    assert actual["interacciones"] == 1500
    assert actual["engagement_pct"] == round(1500 / 42000 * 100, 2)
    assert pub["aviso_en"]  # 1500 interacciones >= objetivo 1000


def test_captura_real_sin_datos_no_inserta(entorno, monkeypatch):
    """Si Metricool aún no tiene datos del post, NO se inserta un snapshot falso."""
    monkeypatch.setattr(comercial, "fuente_actual", lambda: "metricool")
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


def test_reporte_real_no_marca_muestra(entorno, monkeypatch):
    """Con fuente real, el reporte deja de marcarse como dato de muestra."""
    monkeypatch.setattr(comercial, "fuente_actual", lambda: "metricool")
    monkeypatch.setattr(
        comercial.metricas_pieza,
        "recalcular",
        lambda m, r, i: {"interacciones": 200, "visualizaciones": 9000, "encontrado": True},
    )
    pub = comercial.registrar(
        id_post_metricool="post-2", marca="unotv", red="instagram", titulo="Pieza"
    )
    rep = comercial.reporte_publicacion(pub)
    assert rep["es_muestra"] is False
    assert rep["fuente"] == "metricool"
    md = comercial.render_markdown_reporte(rep)
    assert "Datos de muestra" not in md
    assert "Visualizaciones" in md


def test_iniciar_captura_programada_arranca_hilo(entorno):
    """El scheduler arranca un hilo demonio y captura al menos una vez."""
    comercial.registrar(URL, estado="activa", publicado=_hace_dias(2))
    hilo = comercial.iniciar_captura_programada(intervalo_segundos=3600)
    assert hilo.daemon is True
    assert hilo.is_alive()
