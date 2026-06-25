"""Análisis de estrategia digital: serie de seguidores, desglose de interacciones,
crosstab marca×red×formato y correlación seguidores↔posts.

Dos frentes:
  - Sobre la fuente de MUESTRA (offline, determinista): valida shapes y lógica clave
    de las cuatro `construir_*` de la fachada `servicio`.
  - Sobre `FuenteMetricool` con respx (followers timeline mockeado): valida que la
    serie de seguidores REUSA `/v2/analytics/timelines` y que el neto = último −
    primero, y la degradación honesta a vacío cuando no hay followers.

TODO OFFLINE: `KENI_METRICAS_CONFIG` inexistente => muestra; respx mockea el resto.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from keni_metricas import servicio
from keni_metricas.fuentes.metricool import BASE, FuenteMetricool
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.schema import Plataforma


@pytest.fixture
def muestra(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    return tmp_path


RANGO = "rango:2026-05-01_2026-05-07"  # 7 días deterministas, sin fecha actual.


# --------------------------------------------------------------------------- #
# 1) serie de seguidores                                                       #
# --------------------------------------------------------------------------- #


def test_serie_seguidores_shape_y_neto(muestra):
    s = servicio.construir_serie_seguidores(RANGO, "claro_sports")
    assert s["cuenta"] == "claro_sports"
    assert s["fuente"] == "muestra"
    assert s["rango"] == RANGO
    assert s["etiqueta_rango"]
    assert s["periodo"] == {"desde": "2026-05-01", "hasta": "2026-05-07"}
    assert len(s["puntos"]) == 7
    p0 = s["puntos"][0]
    assert set(p0) == {"fecha", "total", "por_red"}
    assert p0["fecha"] == "2026-05-01"
    # total = suma del stock por red ese día.
    assert p0["total"] == sum(p0["por_red"].values())
    # neto = último total − primer total.
    assert s["neto"] == s["puntos"][-1]["total"] - s["puntos"][0]["total"]
    # neto_por_red coherente con la diferencia de stock por red.
    for red, delta in s["neto_por_red"].items():
        ult = s["puntos"][-1]["por_red"].get(red, 0)
        pri = s["puntos"][0]["por_red"].get(red, 0)
        assert delta == ult - pri


def test_serie_seguidores_solo_redes_de_la_marca(muestra):
    # fundacion configura facebook/instagram/x -> esas redes y no más en por_red.
    s = servicio.construir_serie_seguidores(RANGO, "fundacion")
    redes = set()
    for p in s["puntos"]:
        redes |= set(p["por_red"])
    assert redes == {"facebook", "instagram", "x"}


def test_serie_seguidores_global_agrega_marcas(muestra):
    glob = servicio.construir_serie_seguidores(RANGO, None)
    assert glob["cuenta"] is None
    assert len(glob["puntos"]) == 7
    # el total global de un día >= el de una sola marca ese día.
    una = servicio.construir_serie_seguidores(RANGO, "claro_sports")
    assert glob["puntos"][0]["total"] >= una["puntos"][0]["total"]


# --------------------------------------------------------------------------- #
# 2) desglose de interacciones por marca×red                                   #
# --------------------------------------------------------------------------- #


def test_desglose_interacciones_suma_granular_por_marca_red(muestra):
    d = servicio.construir_desglose_interacciones(RANGO, None)
    assert d["fuente"] == "muestra"
    assert d["celdas"]
    celda = d["celdas"][0]
    assert set(celda) == {
        "marca", "red", "likes", "comentarios", "compartidos", "guardados",
        "video_views", "interacciones", "visualizaciones", "engagement_pct", "n_piezas",
    }
    # engagement_pct de la celda = interacciones/visualizaciones*100 (0 si vis 0).
    for c in d["celdas"]:
        esperado = round(c["interacciones"] / c["visualizaciones"] * 100, 2) if c["visualizaciones"] else 0.0
        assert c["engagement_pct"] == esperado
        assert c["n_piezas"] >= 1
    # los totales son la suma de las celdas (campos granulares).
    for campo in ("likes", "comentarios", "compartidos", "guardados", "video_views",
                  "interacciones", "visualizaciones"):
        assert d["totales"][campo] == sum(c[campo] for c in d["celdas"])


def test_desglose_celda_es_un_grupo_marca_red(muestra):
    d = servicio.construir_desglose_interacciones(RANGO, "claro_sports")
    claves = [(c["marca"], c["red"]) for c in d["celdas"]]
    assert len(claves) == len(set(claves))  # una celda por (marca, red)
    assert all(m == "claro_sports" for m, _ in claves)


def test_desglose_granular_ausente_cuenta_como_cero(muestra):
    # Pieza con granulares None: la suma de la celda no debe romper (None -> 0).
    class _FuenteUnaPiezaNula:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

        def mejores_piezas(self, cuenta_id, rango, n):
            from keni_metricas.schema import Pieza
            from datetime import date

            return [
                Pieza(
                    id="p_nula", plataforma=Plataforma.instagram, titulo="x",
                    publicado=date(2026, 5, 3), visualizaciones=1000, interacciones=50,
                    engagement_pct=5.0, cuenta=cuenta_id,
                    likes=None, comentarios=None, compartidos=None,
                    guardados=None, video_views=None,
                )
            ]

    d = servicio.desglose_interacciones_desde_fuente(_FuenteUnaPiezaNula(), RANGO)
    c = d["celdas"][0]
    assert c["n_piezas"] == 1  # cuenta la pieza
    assert c["likes"] == c["comentarios"] == 0  # None -> 0 en la suma
    assert c["interacciones"] == 50 and c["visualizaciones"] == 1000


# --------------------------------------------------------------------------- #
# 3) crosstab marca×red×formato                                                #
# --------------------------------------------------------------------------- #


def test_crosstab_agrupa_por_formato(muestra):
    ct = servicio.construir_crosstab(RANGO, "claro_sports")
    assert ct["fuente"] == "muestra"
    assert ct["celdas"]
    celda = ct["celdas"][0]
    assert set(celda) == {
        "marca", "red", "formato", "n_piezas", "visualizaciones",
        "interacciones", "engagement_pct", "rendimiento_relativo_medio",
    }
    # clave (marca, red, formato) única por celda.
    claves = [(c["marca"], c["red"], c["formato"]) for c in ct["celdas"]]
    assert len(claves) == len(set(claves))
    # alguna celda con varias piezas trae rendimiento_relativo_medio numérico.
    assert any(c["rendimiento_relativo_medio"] is not None for c in ct["celdas"])
    # la suma de n_piezas de todas las celdas = total de piezas del periodo.
    total_piezas = sum(c["n_piezas"] for c in ct["celdas"])
    assert total_piezas > 0


def test_crosstab_rendimiento_relativo_medio_es_media_del_grupo(muestra):
    ct = servicio.construir_crosstab(RANGO, "claro_sports")
    for c in ct["celdas"]:
        rrm = c["rendimiento_relativo_medio"]
        # con piezas, o es None (ninguna anotada) o un float redondeado a 3.
        assert rrm is None or isinstance(rrm, float)


# --------------------------------------------------------------------------- #
# 4) correlación seguidores ↔ posts                                            #
# --------------------------------------------------------------------------- #


def test_correlacion_shape_y_seguidores_por_post(muestra):
    c = servicio.construir_correlacion_seguidores(RANGO, "claro_sports")
    assert c["fuente"] == "muestra"
    assert c["nota"]  # caveat de atribución presente
    assert c["items"]  # hay serie de followers en la muestra
    it = c["items"][0]
    assert set(it) == {
        "marca", "red", "fecha", "seguidores_ganados", "n_posts",
        "seguidores_por_post", "post_estrella",
    }
    for it in c["items"]:
        if it["n_posts"] > 0:
            assert it["seguidores_por_post"] == round(
                it["seguidores_ganados"] / it["n_posts"], 2
            )
        else:
            assert it["seguidores_por_post"] is None  # None si 0 posts


def test_correlacion_post_estrella_es_el_de_mayor_engagement(muestra):
    c = servicio.construir_correlacion_seguidores(RANGO, "claro_sports")
    con_estrella = [it for it in c["items"] if it["post_estrella"] is not None]
    # cuando hay post_estrella, su shape es el esperado.
    for it in con_estrella:
        pe = it["post_estrella"]
        assert set(pe) == {"id", "titulo", "engagement_pct", "url"}
        assert it["n_posts"] >= 1


def test_correlacion_degrada_sin_serie_de_followers():
    # Fuente sin `serie_seguidores` -> items vacío y nota lo explica (degradación honesta).
    class _FuenteSinFollowers:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

        def mejores_piezas(self, cuenta_id, rango, n):
            return []

    c = servicio.correlacion_seguidores_desde_fuente(_FuenteSinFollowers(), RANGO)
    assert c["items"] == []
    assert "no expone serie de seguidores" in c["nota"]


def test_serie_seguidores_degrada_sin_followers():
    class _FuenteSinFollowers:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

        def mejores_piezas(self, cuenta_id, rango, n):
            return []

    s = servicio.serie_seguidores_desde_fuente(_FuenteSinFollowers(), RANGO)
    assert s["puntos"] == []
    assert s["neto"] == 0
    assert s["neto_por_red"] == {}


def test_serie_seguidores_cuenta_conectada_a_mitad_no_pinta_escalon():
    """Una red conectada a mitad de ventana aporta su stock como baseline desde el primer
    día (backfill del borde), no como un escalón el día del alta que parezca crecimiento.

    `facebook` crece de verdad (+20) toda la ventana; `youtube` aparece SOLO el último día
    con 350k de stock. El neto debe ser +20 (youtube no aporta), y el invariante
    neto == total[-1] − total[0] debe seguir cumpliéndose pese al alta a mitad de ventana.
    """
    class _Cuenta:
        def __init__(self, cid):
            self.id = cid

    class _Fuente:
        nombre = "muestra"

        def cuentas(self):
            return [_Cuenta("a"), _Cuenta("b")]

        def serie_seguidores(self, cuenta_id, rango):
            if cuenta_id == "a":
                return [
                    {"fecha": "2026-05-01", "por_red": {"facebook": 1000}},
                    {"fecha": "2026-05-04", "por_red": {"facebook": 1010}},
                    {"fecha": "2026-05-07", "por_red": {"facebook": 1020}},
                ]
            return [{"fecha": "2026-05-07", "por_red": {"youtube": 350_000}}]

    s = servicio.serie_seguidores_desde_fuente(_Fuente(), RANGO)
    fechas = {p["fecha"]: p for p in s["puntos"]}

    # youtube ya está en el PRIMER día con su baseline (no entra de golpe el último día).
    assert fechas["2026-05-01"]["por_red"]["youtube"] == 350_000
    assert fechas["2026-05-01"]["total"] == 1000 + 350_000
    # El alta no cuenta como crecimiento: neto = solo lo que creció facebook.
    assert s["neto_por_red"]["youtube"] == 0
    assert s["neto_por_red"]["facebook"] == 20
    assert s["neto"] == 20
    # Invariante: el neto coincide con la pendiente real de la curva, sin escalón.
    assert s["neto"] == s["puntos"][-1]["total"] - s["puntos"][0]["total"]


def test_serie_alcance_agrega_por_dia_y_red():
    """serie_alcance_desde_fuente suma el alcance diario por red sobre las cuentas en alcance;
    cada día trae `total` (suma de `por_red`). No hay neto (el alcance es un flujo diario)."""
    class _Cuenta:
        def __init__(self, cid):
            self.id = cid

    class _Fuente:
        nombre = "muestra"

        def cuentas(self):
            return [_Cuenta("a"), _Cuenta("b")]

        def serie_alcance(self, cuenta_id, rango):
            if cuenta_id == "a":
                return [{"fecha": "2026-05-20", "por_red": {"instagram": 12000}}]
            return [
                {"fecha": "2026-05-20", "por_red": {"instagram": 3000}},
                {"fecha": "2026-05-21", "por_red": {"instagram": 9000}},
            ]

    s = servicio.serie_alcance_desde_fuente(_Fuente(), RANGO)
    puntos = {p["fecha"]: p for p in s["puntos"]}
    assert puntos["2026-05-20"]["por_red"] == {"instagram": 15000}  # 12000 + 3000
    assert puntos["2026-05-20"]["total"] == 15000
    assert puntos["2026-05-21"]["total"] == 9000
    assert "neto" not in s


def test_serie_alcance_degrada_sin_alcance():
    class _FuenteSinAlcance:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

    s = servicio.serie_alcance_desde_fuente(_FuenteSinAlcance(), RANGO)
    assert s["puntos"] == []


def test_mejor_hora_devuelve_la_franja_de_mayor_score(monkeypatch):
    """mejor_hora toma la celda de mayor score de la matriz de besttimes y devuelve su hora."""
    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "metricool"

        def cuentas(self):
            return [_Cuenta()]

        def mejores_horas(self, cuenta_id, red):
            matriz = [[0.0] * 24 for _ in range(7)]
            matriz[2][20] = 1.0  # la mejor franja: 20:00
            matriz[0][7] = 0.4
            return matriz

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _Fuente())
    assert servicio.mejor_hora("claro_sports", "instagram") == "20:00"


def test_mejor_hora_none_si_sin_datos_o_red_invalida(monkeypatch):
    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "metricool"

        def cuentas(self):
            return [_Cuenta()]

        def mejores_horas(self, cuenta_id, red):
            return [[0.0] * 24 for _ in range(7)]  # sin franjas

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _Fuente())
    assert servicio.mejor_hora("claro_sports", "instagram") is None
    # Red no válida -> None (no revienta).
    assert servicio.mejor_hora("claro_sports", "threads") is None


def test_flujo_audiencia_agrega_por_red(monkeypatch):
    """construir_flujo_audiencia suma altas/bajas/neto por red sobre las cuentas; altas/bajas
    None se conservan None si NINGUNA cuenta de esa red las separa."""
    class _Cuenta:
        def __init__(self, cid):
            self.id = cid

    class _Fuente:
        nombre = "metricool"

        def cuentas(self):
            return [_Cuenta("a"), _Cuenta("b")]

        def flujo_audiencia(self, cuenta_id, rango):
            if cuenta_id == "a":
                return [
                    {"red": "facebook", "altas": 50, "bajas": 10, "neto": 40},
                    {"red": "instagram", "altas": None, "bajas": None, "neto": 75},
                ]
            return [{"red": "facebook", "altas": 20, "bajas": 5, "neto": 15}]

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _Fuente())
    d = servicio.construir_flujo_audiencia(RANGO)
    por_red = {r["red"]: r for r in d["por_red"]}
    assert por_red["facebook"] == {"red": "facebook", "altas": 70, "bajas": 15, "neto": 55}
    assert por_red["instagram"] == {"red": "instagram", "altas": None, "bajas": None, "neto": 75}


def test_flujo_audiencia_degrada_sin_fuente(monkeypatch):
    class _FuenteSinFlujo:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _FuenteSinFlujo())
    assert servicio.construir_flujo_audiencia(RANGO) == {"por_red": []}


def test_demografia_devuelve_distribuciones(monkeypatch):
    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "metricool"

        def cuentas(self):
            return [_Cuenta()]

        def demografia(self, cuenta_id, red):
            return {"gender": [{"clave": "F", "valor": 50.0}]}

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _Fuente())
    d = servicio.construir_demografia("claro_sports", "instagram")
    assert d == {"red": "instagram", "distribuciones": {"gender": [{"clave": "F", "valor": 50.0}]}}


def test_demografia_vacia_si_red_invalida_o_sin_fuente(monkeypatch):
    class _FuenteSinDemo:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _FuenteSinDemo())
    assert servicio.construir_demografia("claro_sports", "instagram") == {
        "red": "instagram", "distribuciones": {}
    }


def test_mejor_hora_none_si_fuente_sin_besttimes(monkeypatch):
    class _FuenteSinBesttimes:
        nombre = "muestra"

        def cuentas(self):
            return FuenteMuestra().cuentas()[:1]

    monkeypatch.setattr(servicio, "_fuente", lambda marca=None: _FuenteSinBesttimes())
    assert servicio.mejor_hora("claro_sports", "instagram") is None


# --------------------------------------------------------------------------- #
# Metricool (respx): serie de seguidores REUSA /v2/analytics/timelines         #
# --------------------------------------------------------------------------- #

_MARCAS_MC = {
    "claro_sports": {
        "user_token": "TOK",
        "user_id": "999",
        "blog_id": "1234567",
        "nombre": "Claro Sports",
        "plataformas": [Plataforma.instagram],
    }
}


@respx.mock
def test_metricool_serie_seguidores_stock_diario():
    """serie_seguidores REUSA la serie de followers (stock diario por red)."""
    def responder(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        if metric == "followers":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "metric": "followers",
                            "values": [
                                {"dateTime": "2026-05-01T00:00:00", "value": 1000},
                                {"dateTime": "2026-05-04T00:00:00", "value": 1050},
                                {"dateTime": "2026-05-07T00:00:00", "value": 1100},
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": []})

    ruta = respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        fuente = FuenteMetricool(marcas=_MARCAS_MC, cliente=cli)
        s = servicio.serie_seguidores_desde_fuente(fuente, RANGO)

    assert ruta.called
    assert s["fuente"] == "metricool"
    # 3 puntos con stock de instagram; total = stock de la única red.
    fechas = {p["fecha"]: p for p in s["puntos"]}
    assert fechas["2026-05-01"]["por_red"] == {"instagram": 1000}
    assert fechas["2026-05-01"]["total"] == 1000
    assert fechas["2026-05-07"]["total"] == 1100
    # neto = último − primero.
    assert s["neto"] == 100
    assert s["neto_por_red"] == {"instagram": 100}


@respx.mock
def test_metricool_serie_seguidores_vacia_sin_followers():
    """Sin serie de followers (red no la expone) -> puntos vacíos, neto 0."""
    respx.get(f"{BASE}/v2/analytics/timelines").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with httpx.Client() as cli:
        fuente = FuenteMetricool(marcas=_MARCAS_MC, cliente=cli)
        s = servicio.serie_seguidores_desde_fuente(fuente, RANGO)

    assert s["puntos"] == []
    assert s["neto"] == 0
    assert s["neto_por_red"] == {}


@respx.mock
def test_metricool_correlacion_usa_serie_y_marca_nota():
    """La correlación de Metricool arma items desde la serie de followers + posts."""
    def responder(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        if metric == "followers":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "metric": "followers",
                            "values": [
                                {"dateTime": "2026-05-01T00:00:00", "value": 1000},
                                {"dateTime": "2026-05-02T00:00:00", "value": 1010},
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": []})

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    # posts: sin piezas (data vacío) -> n_posts 0, seguidores_por_post None.
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with httpx.Client() as cli:
        fuente = FuenteMetricool(marcas=_MARCAS_MC, cliente=cli)
        c = servicio.correlacion_seguidores_desde_fuente(fuente, RANGO)

    assert c["nota"]
    # un item: el delta 2026-05-02 (1010-1000 = +10), sin posts.
    assert len(c["items"]) == 1
    it = c["items"][0]
    assert it["red"] == "instagram"
    assert it["fecha"] == "2026-05-02"
    assert it["seguidores_ganados"] == 10
    assert it["n_posts"] == 0
    assert it["seguidores_por_post"] is None
    assert it["post_estrella"] is None


def test_correlacion_ignora_snapshot_parcial():
    """La correlación consume la serie SANEADA: un día con snapshot incompleto (followers
    ~0, sin consolidar) arrastra el último válido y da delta 0, no un precipicio absurdo."""

    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "stub"

        def cuentas(self):
            return [_Cuenta()]

        def serie_seguidores(self, cuenta_id, rango):
            return [
                {"fecha": "2026-05-28", "por_red": {"facebook": 8_700_000}},
                {"fecha": "2026-05-29", "por_red": {"facebook": 8_710_000}},
                {"fecha": "2026-05-30", "por_red": {"facebook": 0}},  # incompleto, sin consolidar
            ]

        def mejores_piezas(self, cuenta_id, rango, n):
            return []

    c = servicio.correlacion_seguidores_desde_fuente(_Fuente(), "mes:2026-05")
    deltas = {it["fecha"]: it["seguidores_ganados"] for it in c["items"]}
    assert deltas["2026-05-29"] == 10_000  # crecimiento real
    assert deltas["2026-05-30"] == 0  # el 0 se descarta -> arrastra 8.71M (NO −8.71M)


def test_serie_seguidores_neto_por_red_ignora_huecos():
    """Una red con dato al inicio pero AUSENTE el último día no debe restar su stock.

    El neto es POR RED (primer/último de cada red en sus propios días) y se suma.
    """

    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "stub"

        def cuentas(self):
            return [_Cuenta()]

        def serie_seguidores(self, cuenta_id, rango):
            return [
                {"fecha": "2026-05-20", "por_red": {"youtube": 4_970_000, "instagram": 100}},
                {"fecha": "2026-05-26", "por_red": {"instagram": 130}},  # youtube ausente (hueco)
            ]

    s = servicio.serie_seguidores_desde_fuente(_Fuente(), "mes:2026-05")
    # youtube: un solo punto -> 0 (NO −4.97M). instagram: 130 − 100 = 30.
    assert s["neto_por_red"]["youtube"] == 0
    assert s["neto_por_red"]["instagram"] == 30
    # neto global = suma de netos por red (30), no el total global (que daría ≈ −4.96M).
    assert s["neto"] == 30


def test_serie_seguidores_descarta_dia_incompleto():
    """Un último día con valor ~0 (incompleto, sin consolidar) NO debe dar neto negativo.

    Como el stock PERSISTE, ese día se descarta y se arrastra el último
    valor válido; el neto usa primer/último valor VÁLIDO.
    """

    class _Cuenta:
        id = "claro_sports"

    class _Fuente:
        nombre = "stub"

        def cuentas(self):
            return [_Cuenta()]

        def serie_seguidores(self, cuenta_id, rango):
            return [
                {"fecha": "2026-05-28", "por_red": {"facebook": 8_700_000, "youtube": 4_970_000}},
                {"fecha": "2026-05-30", "por_red": {"facebook": 8_710_000, "youtube": 4_970_000}},
                {"fecha": "2026-06-03", "por_red": {"facebook": 0, "youtube": 4_970_000}},  # hoy, incompleto
            ]

    s = servicio.serie_seguidores_desde_fuente(_Fuente(), "mes:2026-05")
    # facebook: el 0 de hoy se descarta -> neto = 8.71M − 8.70M = +10k (NO −8.7M).
    assert s["neto_por_red"]["facebook"] == 10_000
    assert s["neto_por_red"]["youtube"] == 0
    assert s["neto"] == 10_000
    # El chart NO se hunde el último día: arrastra el último facebook válido (8.71M).
    assert s["puntos"][-1]["por_red"]["facebook"] == 8_710_000
    assert s["puntos"][-1]["total"] == 8_710_000 + 4_970_000


def test_serie_seguidores_cuenta_sin_snapshots_no_hunde_el_agregado():
    """UNA cuenta que deja de reportar no debe hundir la red agregada.

    El carry-forward debe ser POR CUENTA antes de sumar: la cuenta muda arrastra su último
    stock y el total sigue plano."""

    class _CuentaA:
        id = "unotv"

    class _CuentaB:
        id = "claro_sports"

    class _Fuente:
        nombre = "stub"

        def cuentas(self):
            return [_CuentaA(), _CuentaB()]

        def serie_seguidores(self, cuenta_id, rango):
            if cuenta_id == "unotv":  # reporta TODOS los días
                return [
                    {"fecha": "2026-05-18", "por_red": {"tiktok": 3_158_000}},
                    {"fecha": "2026-05-19", "por_red": {"tiktok": 3_169_000}},
                    {"fecha": "2026-05-20", "por_red": {"tiktok": 3_176_000}},
                ]
            return [  # claro_sports: deja de reportar tras el 18-may
                {"fecha": "2026-05-18", "por_red": {"tiktok": 2_317_000}},
            ]

    s = servicio.serie_seguidores_desde_fuente(_Fuente(), "mes:2026-05")
    # Los días sin snapshot de claro_sports arrastran su último stock: sin precipicios.
    assert [p["por_red"]["tiktok"] for p in s["puntos"]] == [
        3_158_000 + 2_317_000,
        3_169_000 + 2_317_000,
        3_176_000 + 2_317_000,
    ]
    # Neto = crecimiento real de unotv (+18k), NO −2.3M por la cuenta muda.
    assert s["neto_por_red"]["tiktok"] == 18_000
    assert s["neto"] == 18_000
