"""API de métricas: contrato del reporte consolidado, comparativa y exports.

TODO OFFLINE: la fuente es de muestra (`KENI_METRICAS_CONFIG` inexistente, lo fija
`entorno`). Cubre en particular que la respuesta exponga el campo `fuente`
("muestra"|"real") — N3: el frontend pinta un badge para distinguir datos ficticios
de reales (riesgo operativo del piloto).
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


def test_reporte_trae_cobertura_por_marca_con_todas_las_redes(cliente):
    # La auditoría de cobertura lista TODAS las redes auditables por marca (aunque no
    # tengan datos), cada una con estado + motivo (responde a "¿por qué solo veo 1 red?").
    r = cliente.get("/api/metricas/reporte?rango=mes")
    assert r.status_code == 200
    data = r.json()
    assert "cobertura_redes" in data
    auditables = {"facebook", "instagram", "x", "tiktok", "youtube"}
    for marca in data["cobertura_redes"]:
        assert {"marca_id", "marca", "redes"} <= marca.keys()
        # Universo COMPLETO de redes, no solo las que tienen datos.
        assert {red["red"] for red in marca["redes"]} == auditables
        for red in marca["redes"]:
            assert red["estado"]  # siempre clasificada
            # Una red sin datos no inventa un 0: sus métricas van null + motivo.
            if red["estado"] != "con_datos":
                assert red["visualizaciones"] is None
                assert red["motivo"]


def test_reporte_filtra_por_red(cliente):
    # Con `?red=`, el reporte queda restringido a ESA red: por_red solo trae esa red,
    # cobertura_redes lista solo esa red por marca, y los totales se re-suman sobre ella.
    full = cliente.get("/api/metricas/reporte?rango=mes").json()
    red = full["por_red"][0]["red"]  # una red con datos en la muestra
    r = cliente.get(f"/api/metricas/reporte?rango=mes&red={red}")
    assert r.status_code == 200
    data = r.json()
    assert data["red"] == red
    assert [x["red"] for x in data["por_red"]] == [red]
    for marca in data["cobertura_redes"]:
        assert {x["red"] for x in marca["redes"]} == {red}
    # El total de la red nunca supera el global (es un subconjunto).
    assert data["total"]["visualizaciones"] <= full["total"]["visualizaciones"]
    # El conteo de piezas de la red sale del LISTADO filtrado por plataforma (no del
    # resumen, que no cuenta piezas por red).
    listado = cliente.get("/api/metricas/piezas-listado?rango=mes").json()
    esperado = sum(1 for p in listado["piezas"] if p["plataforma"] == red)
    assert data["total"]["piezas"] == esperado


def test_reporte_sin_red_no_lleva_campo_red(cliente):
    # Sin filtro, la respuesta es idéntica a la de siempre: ni campo `red` ni recorte.
    data = cliente.get("/api/metricas/reporte?rango=mes").json()
    assert "red" not in data
    auditables = {"facebook", "instagram", "x", "tiktok", "youtube"}
    for marca in data["cobertura_redes"]:
        assert {x["red"] for x in marca["redes"]} == auditables


def test_reporte_red_invalida_devuelve_400(cliente):
    r = cliente.get("/api/metricas/reporte?rango=mes&red=linkedin")
    assert r.status_code == 400
    assert "error" in r.json()


def test_cobertura_por_marca_clasifica_los_cuatro_estados():
    from keni_consola.api.metricas import _cobertura_por_marca

    rep = {
        "nombres": {"unotv": "UnoTV"},
        "cuentas": [
            {
                "resumen": {
                    "cuenta": "unotv",
                    "por_plataforma": [
                        {
                            "plataforma": "tiktok",
                            "visualizaciones": 1000,
                            "alcance": None,
                            "interacciones": 50,
                            "engagement_pct": 5.0,
                        },
                        {
                            "plataforma": "instagram",
                            "visualizaciones": 0,
                            "alcance": None,
                            "interacciones": 0,
                            "engagement_pct": 0.0,
                        },
                    ],
                    "cobertura": {
                        "ok": ["tiktok", "instagram"],
                        "omitidas": ["facebook"],
                        "motivo": {"facebook": "error_api"},
                    },
                }
            }
        ],
    }
    salida = _cobertura_por_marca(rep)
    assert len(salida) == 1
    assert salida[0]["marca"] == "UnoTV"  # nombre resuelto, no el id crudo
    por_red = {r["red"]: r for r in salida[0]["redes"]}
    # con datos -> métricas reales.
    assert por_red["tiktok"]["estado"] == "con_datos"
    assert por_red["tiktok"]["visualizaciones"] == 1000
    # respondió pero todo a 0 -> conectada sin métricas en el rango: métricas null (no un
    # 0/0.0% falso) + motivo, igual que el resto de estados no-con_datos.
    assert por_red["instagram"]["estado"] == "sin_metricas"
    assert por_red["instagram"]["visualizaciones"] is None
    assert por_red["instagram"]["interacciones"] is None
    assert por_red["instagram"]["engagement_pct"] is None
    assert por_red["instagram"]["motivo"]
    # omitida por error_api -> "sin lectura", métricas null.
    assert por_red["facebook"]["estado"] == "sin_lectura"
    assert por_red["facebook"]["visualizaciones"] is None
    assert por_red["facebook"]["motivo"]
    # ni respondió ni está configurada -> "no configurada".
    assert por_red["x"]["estado"] == "no_configurada"
    assert por_red["youtube"]["estado"] == "no_configurada"


def test_opciones_trae_marcas_y_rangos(cliente):
    r = cliente.get("/api/metricas/opciones")
    assert r.status_code == 200
    data = r.json()
    assert data["marcas"]
    ids_rango = {x["id"] for x in data["rangos"]}
    assert {"semana", "mes", "anio"} <= ids_rango  # "Último año" se ofrece en el menu
    # "7d"/"30d" son identicos a "semana"/"mes" (mismas ventanas rodantes): no se OFRECEN
    # en el menu aunque sigan siendo tokens de entrada validos (lo cubre test_comparar/_validar).
    assert {"7d", "30d"}.isdisjoint(ids_rango)


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


def test_comparar_totales_mide_b_respecto_a_a_y_recalcula_engagement():
    # A = "antes", B = "actual". La UI pinta B como valor grande y A como "antes", así que
    # la variación debe medir B respecto a A: subir 170M→236M es +39 %, NO −28 % (la base es A
    # y el signo va de A a B). El engagement se RECALCULA int/vis por periodo (el total no
    # lo trae con varias redes) para no salir "—".
    from keni_consola.api.metricas import _comparar_totales

    total_a = {"visualizaciones": 170, "interacciones": 10}
    total_b = {"visualizaciones": 236, "interacciones": 20}
    metricas = {m["metrica"]: m for m in _comparar_totales(total_a, total_b)["metricas"]}
    vis = metricas["visualizaciones"]
    assert (vis["a"], vis["b"]) == (170, 236)
    assert vis["diferencia"] == 66  # b - a (actual menos antes)
    assert vis["variacion_pct"] == round((236 - 170) / 170 * 100, 1)
    assert vis["variacion_pct"] > 0  # una subida sale positiva, flecha arriba
    eng = metricas["engagement_pct"]
    assert eng["a"] == round(10 / 170 * 100, 1)
    assert eng["b"] == round(20 / 236 * 100, 1)
    assert eng["variacion_pct"] is not None  # ya no es "—"


def test_comparar_totales_incluye_granulares_y_seguidores_cuando_estan():
    # Las métricas que faltaban (likes/comentarios/…/seguidores) se comparan cuando el
    # total las trae (las inyecta `_total_comparable` desde desglose + serie de seguidores).
    from keni_consola.api.metricas import _comparar_totales

    total_a = {"visualizaciones": 100, "interacciones": 10, "likes": 8, "clics_enlace": 3, "seguidores_netos": 40}
    total_b = {"visualizaciones": 120, "interacciones": 15, "likes": 12, "clics_enlace": 7, "seguidores_netos": 50}
    claves = {m["metrica"] for m in _comparar_totales(total_a, total_b)["metricas"]}
    assert {"likes", "clics_enlace", "seguidores_netos"} <= claves


def test_suma_clics_none_si_ninguna_pieza_lo_expone():
    # clics se suma del listado de piezas; None (no 0) si ninguna lo trae (degradación honesta).
    from keni_consola.api.metricas import _suma_clics

    assert _suma_clics({"piezas": [{"clics_enlace": 3}, {"clics_enlace": None}, {"clics_enlace": 4}]}) == 7
    assert _suma_clics({"piezas": [{"clics_enlace": None}, {}]}) is None
    assert _suma_clics({}) is None


def test_comparar_totales_omite_metricas_ausentes():
    # A nivel "por marca" solo llegan vistas/interacciones: no se pinta una tarjeta de
    # likes/seguidores con datos a medias (se omite la métrica ausente).
    from keni_consola.api.metricas import _comparar_totales

    solo_base = {"visualizaciones": 100, "interacciones": 10}
    claves = {m["metrica"] for m in _comparar_totales(solo_base, solo_base)["metricas"]}
    assert "likes" not in claves
    assert "seguidores_netos" not in claves
    assert {"visualizaciones", "interacciones", "engagement_pct"} <= claves


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


def test_analisis_devuelve_narrativa_con_procedencia(cliente):
    # Lectura "qué cambió y por qué" + siguiente paso. La procedencia de los
    # datos viaja en `fuente` (en tests, la fuente offline del paquete).
    r = cliente.get("/api/metricas/analisis?rango=semana")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    assert "es_muestra" not in data
    assert isinstance(data["movimientos"], list)
    # cierra con un siguiente paso accionable (loop a la acción)
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


def test_rango_mes_desnudo_se_normaliza(cliente):
    """`?rango=2026-05` (AAAA-MM sin prefijo) se normaliza a `mes:2026-05`.

    Regresión: caía al fallback 'mes' (últimos 30 días) EN SILENCIO, así que pedir
    "mayo" devolvía números de otro periodo sin ningún aviso — p.ej. el contador de
    piezas de un mes cerrado salía con el del rango rodante."""
    r = cliente.get("/api/metricas/reporte?rango=2026-05")
    assert r.status_code == 200
    data = r.json()
    assert data["rango"] == "mes:2026-05"
    assert data["etiqueta_rango"] == "Mayo 2026"


def test_analisis_y_comparar_llevan_generado_en(cliente):
    # Igual que /reporte, las lecturas cacheadas exponen cuándo se calcularon.
    a = cliente.get("/api/metricas/analisis?rango=semana")
    assert a.status_code == 200
    assert a.json()["generado_en"]
    c = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert c.status_code == 200
    assert c.json()["generado_en"]


def test_estado_devuelve_contrato_y_generado_en_del_combo(cliente):
    # Inicializamos la cache del combo leyéndolo una vez.
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
    # El barrido (fuente de muestra) corre en un HILO DE FONDO; en local termina en ms, pero
    # bajo la carga del CI (host compartido, varios agentes + Postgres) puede tardar bastante
    # más. Esperamos con un presupuesto AMPLIO (~20 s): el bucle SALE en cuanto `corriendo`
    # baja, así que el camino feliz sigue siendo instantáneo; el tope solo evita colgar el test
    # si algo va mal. Un presupuesto corto produciría un flake bajo contención sin medir nada real.
    est = cuerpo
    for _ in range(400):
        est = cliente.get("/api/metricas/estado?rango=mes").json()
        if not est["corriendo"]:
            break
        time.sleep(0.05)
    assert est["corriendo"] is False, "el refresco de métricas no terminó dentro del presupuesto de espera"
    assert est["ultimo_error"] == ""


def test_piezas_devuelve_estadisticas_y_top(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["cuenta"] == "claro_sports"
    assert data["total"] > 0
    assert len(data["top"]) == 10 and len(data["peores"]) == 10
    assert data["engagement"]["media"] is not None
    assert data["generado_en"]
    assert data["etiqueta_rango"]


def test_piezas_global_sin_marca(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes")
    assert r.status_code == 200
    assert r.json()["cuenta"] is None


def test_piezas_filtra_por_red(cliente):
    full = cliente.get("/api/metricas/piezas?rango=mes").json()
    red = full["top"][0]["plataforma"]  # una red presente sin filtrar
    r = cliente.get(f"/api/metricas/piezas?rango=mes&red={red}")
    assert r.status_code == 200
    data = r.json()
    assert all(p["plataforma"] == red for p in data["top"])
    assert all(p["plataforma"] == red for p in data["peores"])
    assert data["total"] <= full["total"]


def test_piezas_red_invalida_devuelve_400(cliente):
    r = cliente.get("/api/metricas/piezas?rango=mes&red=mastodon")
    assert r.status_code == 400
    assert "error" in r.json()


def test_filtrar_reporte_por_red_resume_solo_esa_red():
    from keni_consola.api.metricas import _filtrar_reporte_por_red

    rep = {
        "total": {"visualizaciones": 999, "interacciones": 99, "alcance": 5, "piezas": 7},
        "cuentas": [
            {
                "resumen": {
                    "cuenta": "unotv",
                    "por_plataforma": [
                        {"plataforma": "instagram", "visualizaciones": 100,
                         "alcance": 10, "interacciones": 20, "engagement_pct": 20.0},
                        {"plataforma": "tiktok", "visualizaciones": 500,
                         "alcance": None, "interacciones": 5, "engagement_pct": 1.0},
                    ],
                }
            }
        ],
    }
    out = _filtrar_reporte_por_red(rep, "instagram", piezas_red=3)
    r = out["cuentas"][0]["resumen"]
    assert [p["plataforma"] for p in r["por_plataforma"]] == ["instagram"]
    assert r["visualizaciones"] == 100 and r["interacciones"] == 20 and r["alcance"] == 10
    # Total re-sumado sobre la red, NO el global; piezas vienen del listado (no del resumen).
    assert out["total"]["visualizaciones"] == 100
    assert out["total"]["interacciones"] == 20
    assert out["total"]["alcance"] == 10
    assert out["total"]["piezas"] == 3


def test_filtrar_reporte_por_red_marca_sin_esa_red_queda_en_cero():
    from keni_consola.api.metricas import _filtrar_reporte_por_red

    rep = {
        "total": {"visualizaciones": 500, "interacciones": 5, "alcance": None, "piezas": 2},
        "cuentas": [
            {
                "resumen": {
                    "cuenta": "unotv",
                    "por_plataforma": [
                        {"plataforma": "tiktok", "visualizaciones": 500,
                         "alcance": None, "interacciones": 5, "engagement_pct": 1.0},
                    ],
                }
            }
        ],
    }
    out = _filtrar_reporte_por_red(rep, "instagram", piezas_red=0)
    r = out["cuentas"][0]["resumen"]
    # La cuenta no tiene esa red: métricas en 0 / alcance None, sin inventar datos.
    assert r["por_plataforma"] == []
    assert r["visualizaciones"] == 0 and r["interacciones"] == 0 and r["alcance"] is None
    assert out["total"]["visualizaciones"] == 0 and out["total"]["alcance"] is None


def test_filtrar_reporte_por_red_combina_varias_redes():
    """Combinación a antojo: con varias redes, cada cuenta SUMA sus plataformas elegidas."""
    from keni_consola.api.metricas import _filtrar_reporte_por_red

    rep = {
        "total": {"visualizaciones": 999, "interacciones": 99, "alcance": 5, "piezas": 7},
        "cuentas": [
            {
                "resumen": {
                    "cuenta": "unotv",
                    "por_plataforma": [
                        {"plataforma": "instagram", "visualizaciones": 100,
                         "alcance": 10, "interacciones": 20, "engagement_pct": 20.0},
                        {"plataforma": "tiktok", "visualizaciones": 500,
                         "alcance": None, "interacciones": 5, "engagement_pct": 1.0},
                        {"plataforma": "youtube", "visualizaciones": 1,
                         "alcance": 1, "interacciones": 1, "engagement_pct": 1.0},
                    ],
                }
            }
        ],
    }
    out = _filtrar_reporte_por_red(rep, ("instagram", "tiktok"), piezas_red=4)
    r = out["cuentas"][0]["resumen"]
    assert {p["plataforma"] for p in r["por_plataforma"]} == {"instagram", "tiktok"}
    # Suma de instagram + tiktok (no youtube); alcance suma solo los no-null.
    assert r["visualizaciones"] == 600 and r["interacciones"] == 25 and r["alcance"] == 10
    assert out["total"]["visualizaciones"] == 600 and out["total"]["piezas"] == 4


def test_validar_redes_acepta_csv_y_rechaza_desconocidas():
    from keni_consola.api.metricas._comun import _validar_redes

    assert _validar_redes(None) == ()
    assert _validar_redes("") == ()
    assert _validar_redes("instagram") == ("instagram",)
    assert _validar_redes("instagram,youtube") == ("instagram", "youtube")
    # Dedup y orden de aparición.
    assert _validar_redes("youtube,instagram,youtube") == ("youtube", "instagram")
    with pytest.raises(ValueError):
        _validar_redes("instagram,marte")


def test_tendencia_serie_diaria(cliente):
    r = cliente.get("/api/metricas/tendencia?rango=rango:2026-05-01_2026-05-07&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert len(data["puntos"]) == 7
    assert data["puntos"][0]["fecha"] == "2026-05-01"
    assert data["generado_en"]


def test_tendencia_filtra_por_red(cliente):
    full = cliente.get("/api/metricas/piezas?rango=mes&marca=claro_sports").json()
    red = full["top"][0]["plataforma"]
    r = cliente.get(f"/api/metricas/tendencia?rango=mes&marca=claro_sports&red={red}")
    assert r.status_code == 200
    data = r.json()
    assert "puntos" in data
    assert data["generado_en"]


def test_tendencia_red_invalida_devuelve_400(cliente):
    r = cliente.get("/api/metricas/tendencia?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


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


def _inicializar_pieza_publicada(marca: str, red: str, id_post: str, titulo: str = "Gol") -> str:
    """Crea una pieza publicada (contenido + plataforma con id_post_metricool). Devuelve publicacion_id."""
    from keni_consola import repos

    item = repos.crear_publicacion(clase="contenido", titulo=titulo, marca=marca)
    repos.crear_pieza_fila(
        publicacion_id=item["id"], red=red, id_post_metricool=id_post, es_publicacion=True
    )
    return item["id"]


def test_piezas_rendimiento_lista_publicadas_con_rendimiento(cliente):
    # claro-sports (Consola) -> claro_sports (id_metricas). La muestra devuelve datos
    # deterministas por id_post, así que la pieza sale como `encontrado`.
    publicacion_id = _inicializar_pieza_publicada("claro-sports", "facebook", "post-123")
    r = cliente.get("/api/metricas/piezas-rendimiento?marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["fuente"] == "muestra"
    pieza = data["piezas"][0]
    assert pieza["publicacion_id"] == publicacion_id  # enlace al tablero
    assert pieza["red"] == "facebook"
    assert pieza["encontrado"] is True
    assert pieza["visualizaciones"] > 0


def test_piezas_rendimiento_sin_id_post_se_omite(cliente):
    # Una pieza publicada SIN id_post_metricool no aparece (no se puede leer su rendimiento).
    from keni_consola import repos

    item = repos.crear_publicacion(clase="contenido", titulo="Borrador", marca="claro-sports")
    repos.crear_pieza_fila(publicacion_id=item["id"], red="facebook", es_publicacion=True)
    r = cliente.get("/api/metricas/piezas-rendimiento?marca=claro_sports")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_piezas_rendimiento_acota_por_marca(cliente):
    _inicializar_pieza_publicada("claro-sports", "facebook", "post-a")
    _inicializar_pieza_publicada("unotv", "instagram", "post-b")
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
    # Cabecera + las dos categorías (Top / Peores, con su conteo) presentes en el cuerpo.
    assert "Engagement %" in r.text
    assert "Top" in r.text and "Peores" in r.text


def test_piezas_export_json_trae_top_y_peores(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&fmt=json")
    assert r.status_code == 200
    import json

    data = json.loads(r.text)
    assert len(data["top"]) == 10 and len(data["peores"]) == 10
    assert len(data["filas"]) == 20  # top (10) + peores (10)


def test_piezas_export_fmt_desconocido_cae_a_csv(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&fmt=xml")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_piezas_export_filtra_por_red(cliente):
    import json

    full = cliente.get("/api/metricas/piezas?rango=mes").json()
    red = full["top"][0]["plataforma"]
    r = cliente.get(f"/api/metricas/piezas-export?rango=mes&red={red}&fmt=json")
    assert r.status_code == 200
    data = json.loads(r.text)
    assert all(p["plataforma"] == red for p in data["top"])
    assert all(p["plataforma"] == red for p in data["peores"])


def test_piezas_export_red_invalida_devuelve_400(cliente):
    r = cliente.get("/api/metricas/piezas-export?rango=mes&red=nope")
    assert r.status_code == 400


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
    item = repos.crear_publicacion(
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


def test_cobertura_x_no_conectada_aclara_licencia_extra():
    # X (Twitter) es una licencia aparte de Metricool: cuando sale "no conectada" el
    # motivo lo aclara, para que nadie del equipo intente "conectarla".
    from keni_consola.api.metricas import _cobertura_por_marca

    rep = {
        "nombres": {"unotv": "UnoTV"},
        "cuentas": [
            {
                "resumen": {
                    "cuenta": "unotv",
                    "por_plataforma": [],
                    "cobertura": {"ok": [], "omitidas": ["x"], "motivo": {"x": "no_conectada"}},
                }
            }
        ],
    }
    por_red = {r["red"]: r for r in _cobertura_por_marca(rep)[0]["redes"]}
    assert por_red["x"]["estado"] == "no_conectada"
    assert "licencia adicional" in por_red["x"]["motivo"].lower()
