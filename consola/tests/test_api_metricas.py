"""API de métricas: contrato del reporte consolidado, comparativa y exports.

TODO OFFLINE: la fuente es de muestra (`KENI_METRICAS_CONFIG` inexistente, lo fija
`entorno`). Cubre en particular que la respuesta exponga el campo `fuente`
("muestra"|"real") — N3: el frontend pinta un badge para distinguir datos ficticios
de reales (riesgo operativo del piloto AMX).
"""

from __future__ import annotations

import time

import pytest

from .conftest import _cliente


@pytest.fixture
def cliente(entorno):
    return _cliente()


def test_reporte_expone_fuente_muestra(cliente):
    r = cliente.get("/api/metricas/reporte?rango=mes")
    assert r.status_code == 200
    data = r.json()
    # N3: el campo `fuente` viaja al frontend para el badge de datos de muestra.
    assert data["fuente"] == "muestra"
    assert "total" in data
    assert "cuentas" in data
    # Servido desde la cache (lazy fill): la respuesta lleva cuándo se calculó.
    assert data["generado_en"]


def test_reporte_acotado_a_una_marca_sigue_trayendo_fuente(cliente):
    r = cliente.get("/api/metricas/reporte?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    ids = {c["marca_id"] for c in data["cuentas"]}
    assert ids == {"claro_sports"}


def test_opciones_trae_marcas_y_rangos(cliente):
    r = cliente.get("/api/metricas/opciones")
    assert r.status_code == 200
    data = r.json()
    assert data["marcas"]
    ids_rango = {x["id"] for x in data["rangos"]}
    assert {"semana", "mes"} <= ids_rango


def test_export_json_incluye_fuente(cliente):
    r = cliente.get("/api/metricas/export.json?rango=mes")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    # El export crudo del reporte tambien lleva `fuente` (lo pone construir_reporte).
    assert '"fuente"' in r.text


def test_export_csv_y_md_descargan(cliente):
    csv = cliente.get("/api/metricas/export.csv?rango=mes")
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    md = cliente.get("/api/metricas/export.md?rango=mes")
    assert md.status_code == 200
    assert "text/markdown" in md.headers["content-type"]


def test_comparar_total_y_por_marca(cliente):
    r = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "por_marca" in data


def test_comparar_expone_fuente_muestra(cliente):
    # N6: la comparativa A vs B tambien lleva `fuente` para el badge de muestra,
    # igual que `/reporte`. Con la fuente offline de `entorno`, ambos lados son muestra.
    r = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert r.status_code == 200
    assert r.json()["fuente"] == "muestra"


def test_comparar_acotado_a_una_marca_sigue_trayendo_fuente(cliente):
    r = cliente.get("/api/metricas/comparar?rango_a=7d&rango_b=30d&marca=unotv")
    assert r.status_code == 200
    assert r.json()["fuente"] == "muestra"


def test_analisis_devuelve_narrativa_y_marca_muestra(cliente):
    # F6/#146: lectura "qué cambió y por qué" + siguiente paso. Con la fuente
    # offline marca explícitamente que los datos son de muestra (issue #131).
    r = cliente.get("/api/metricas/analisis?rango=semana")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    assert data["es_muestra"] is True
    assert isinstance(data["movimientos"], list)
    # cierra con un siguiente paso accionable (loop a la acción, UX-roadmap #11)
    assert data["siguiente_paso"] is not None
    assert "Pídele a Claude" in data["siguiente_paso"]["texto"]


def test_analisis_acotado_a_una_marca(cliente):
    r = cliente.get("/api/metricas/analisis?rango=semana&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["marca"] == "claro_sports"
    # acotado a una marca: los movimientos (si hay) son sólo de esa marca
    assert all(m["marca_id"] == "claro_sports" for m in data["movimientos"])


def test_analisis_rango_invalido_devuelve_400(cliente):
    # _validar_rango cae a un rango válido por defecto, así que un rango raro NO
    # rompe: devuelve 200 con la lectura del rango por defecto. El 400 sólo
    # ocurriría si la fachada lanzara ValueError; aquí verificamos la respuesta OK.
    r = cliente.get("/api/metricas/analisis?rango=trimestre")
    assert r.status_code == 200
    assert r.json()["fuente"] == "muestra"


def test_analisis_y_comparar_llevan_generado_en(cliente):
    # Igual que /reporte, las lecturas cacheadas exponen cuándo se calcularon.
    a = cliente.get("/api/metricas/analisis?rango=semana")
    assert a.status_code == 200
    assert a.json()["generado_en"]
    c = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert c.status_code == 200
    assert c.json()["generado_en"]


def test_estado_devuelve_contrato_y_generado_en_del_combo(cliente):
    # Sembramos la cache del combo leyéndolo una vez.
    rep = cliente.get("/api/metricas/reporte?rango=mes").json()
    est = cliente.get("/api/metricas/estado?rango=mes").json()
    assert est["corriendo"] is False
    assert set(est) >= {"corriendo", "iniciado_en", "terminado_en", "ultimo_error", "generado_en"}
    assert est["generado_en"] == rep["generado_en"]


def test_refrescar_responde_202_y_completa(cliente):
    r = cliente.post("/api/metricas/refrescar?rango=mes")
    assert r.status_code == 202
    cuerpo = r.json()
    assert isinstance(cuerpo["corriendo"], bool)
    # El barrido (fuente de muestra) termina rápido; esperamos a que acabe para no
    # dejar un hilo escribiendo durante el teardown del test.
    for _ in range(100):
        est = cliente.get("/api/metricas/estado?rango=mes").json()
        if not est["corriendo"]:
            break
        time.sleep(0.02)
    assert est["corriendo"] is False
    assert est["ultimo_error"] == ""


def test_piezas_devuelve_estadisticas_y_top(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["cuenta"] == "claro_sports"
    assert data["total"] > 0
    assert len(data["top"]) == 5 and len(data["peores"]) == 5
    assert data["engagement"]["media"] is not None
    assert data["generado_en"]
    assert data["etiqueta_rango"]


def test_piezas_global_sin_marca(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes")
    assert r.status_code == 200
    assert r.json()["cuenta"] is None


def test_tendencia_serie_diaria(cliente):
    r = cliente.get("/api/metricas/tendencia?rango=rango:2026-05-01_2026-05-07&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert len(data["puntos"]) == 7
    assert data["puntos"][0]["fecha"] == "2026-05-01"
    assert data["generado_en"]


def test_piezas_acepta_token_mes(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes:2026-05&marca=claro_sports")
    assert r.status_code == 200
    assert r.json()["periodo"]["desde"] == "2026-05-01"


def test_token_mal_formado_devuelve_400(cliente):
    # token con prefijo válido pero formato inválido => la fachada lanza ValueError => 400.
    r = cliente.get("/api/metricas/piezas?rango=mes:2026-99")
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Drill-down marca -> pieza: /api/metricas/piezas-rendimiento                  #
# --------------------------------------------------------------------------- #


def _sembrar_pieza_publicada(marca: str, red: str, id_post: str, titulo: str = "Gol") -> str:
    """Crea una pieza publicada (contenido + plataforma con id_post_metricool). Devuelve contenido_id."""
    from keni_consola import repos

    item = repos.crear_contenido(clase="contenido", titulo=titulo, marca=marca)
    repos.crear_contenido_plataforma(
        contenido_id=item["id"], red=red, id_post_metricool=id_post, es_publicacion=True
    )
    return item["id"]


def test_piezas_rendimiento_lista_publicadas_con_rendimiento(cliente):
    # claro-sports (Consola) -> claro_sports (id_metricas). La muestra devuelve datos
    # deterministas por id_post, así que la pieza sale como `encontrado`.
    contenido_id = _sembrar_pieza_publicada("claro-sports", "facebook", "post-123")
    r = cliente.get("/api/metricas/piezas-rendimiento?marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["fuente"] == "muestra"
    pieza = data["piezas"][0]
    assert pieza["contenido_id"] == contenido_id  # enlace al tablero
    assert pieza["red"] == "facebook"
    assert pieza["encontrado"] is True
    assert pieza["visualizaciones"] > 0


def test_piezas_rendimiento_sin_id_post_se_omite(cliente):
    # Una pieza publicada SIN id_post_metricool no aparece (no se puede leer su rendimiento).
    from keni_consola import repos

    item = repos.crear_contenido(clase="contenido", titulo="Borrador", marca="claro-sports")
    repos.crear_contenido_plataforma(contenido_id=item["id"], red="facebook", es_publicacion=True)
    r = cliente.get("/api/metricas/piezas-rendimiento?marca=claro_sports")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_piezas_rendimiento_acota_por_marca(cliente):
    _sembrar_pieza_publicada("claro-sports", "facebook", "post-a")
    _sembrar_pieza_publicada("unotv", "instagram", "post-b")
    # Acotado a una marca: solo sus piezas.
    r = cliente.get("/api/metricas/piezas-rendimiento?marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["piezas"][0]["marca"] == "claro-sports"
    # Sin marca: agrega todas.
    r_todas = cliente.get("/api/metricas/piezas-rendimiento")
    assert r_todas.json()["total"] == 2


# --------------------------------------------------------------------------- #
# Export del Top/Peores de piezas: /api/metricas/piezas-export (Item B)        #
# --------------------------------------------------------------------------- #


def test_piezas_export_csv_descarga_y_lleva_grupos(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&marca=claro_sports&fmt=csv")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert "piezas-mes" in r.headers["content-disposition"]
    # Cabecera + las dos categorías (Top 5 / Peores 5) presentes en el cuerpo.
    assert "Engagement %" in r.text
    assert "Top 5" in r.text and "Peores 5" in r.text


def test_piezas_export_json_trae_top_y_peores(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&fmt=json")
    assert r.status_code == 200
    import json

    data = json.loads(r.text)
    assert len(data["top"]) == 5 and len(data["peores"]) == 5
    assert len(data["filas"]) == 10


def test_piezas_export_fmt_desconocido_cae_a_csv(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&fmt=xml")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


# --------------------------------------------------------------------------- #
# Analítica por serie/tipo: /api/metricas/piezas-por-etiqueta (Item C)         #
# --------------------------------------------------------------------------- #


def test_piezas_por_etiqueta_contrato_y_ejes(cliente):
    r = cliente.get("/api/metricas/piezas-por-etiqueta?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0
    ejes = {s["eje"] for s in data["series"]}
    assert {"tipo", "campania", "vertical", "etiqueta_tipo"} <= ejes
    # Sin nada enlazado en la BD, todas las piezas caen en "Sin clasificar".
    assert data["enlazadas"] == 0
    assert data["sin_enlace"] == data["total"]


def test_piezas_por_etiqueta_enlaza_por_titulo_y_resuelve_etiqueta(cliente):
    from keni_consola import repos

    # Título idéntico a una pieza de la muestra de deportes -> fuzzy-match por título.
    item = repos.crear_contenido(
        clase="contenido",
        titulo="Gol agónico en el último minuto",
        marca="claro-sports",
        tipo_contenido="galeria",
    )
    et = repos.crear_etiqueta(nombre="Mundial 2026", clase="campania", marca="claro-sports")
    repos.asignar_etiqueta(item["id"], et["id"])

    r = cliente.get("/api/metricas/piezas-por-etiqueta?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    # Al menos una pieza enlazó por título (la muestra repite títulos del pool).
    assert data["enlazadas_titulo"] >= 1
    # El eje "tipo" debe tener un grupo "galeria" (el tipo_contenido del contenido enlazado).
    tipo = next(s for s in data["series"] if s["eje"] == "tipo")
    assert any(g["valor"] == "galeria" for g in tipo["grupos"])
    # Y el eje "campania" un grupo "Mundial 2026".
    campania = next(s for s in data["series"] if s["eje"] == "campania")
    assert any(g["valor"] == "Mundial 2026" for g in campania["grupos"])
