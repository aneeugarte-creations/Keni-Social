"""Tests PUROS (sin DB ni red) del dominio de clustering de historias (`dominio.clustering`).

Cubre la identidad de cluster (`clave_cluster`: url canónica sin query vs hash de título), la
asignación incremental (`asignar`: cruce por misma url, fuzzy de título, ventana/umbral, item
nuevo), el recálculo de agregados (`recalcular`: n_items/n_fuentes/idiomas/señal/representativo/
breaking) y el scoring (`puntuar`: fórmula documentada + monotonía por señal). Todo determinista,
con `ahora` inyectado: nunca se toca el reloj real, la BD ni la red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keni_consola.dominio import clustering

_T0 = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)


def _item(**campos):
    base = {
        "fuente_id": "f1",
        "titulo": "Titulo de prueba sobre algo",
        "resumen": "Resumen",
        "idioma": "es",
        "senal": 0,
        "marca": "unotv",
        "categoria": "mx",
        "geo": "MX",
        "url": "https://example.com/n",
        "publicado_en": _T0.isoformat(),
    }
    base.update(campos)
    return base


# --------------------------------------------------------------------------- #
# clave_cluster / url_canonica_clustering                                       #
# --------------------------------------------------------------------------- #


def test_clave_por_url_ignora_query_y_tracking():
    a = clustering.clave_cluster(_item(url="https://www.example.com/nota-1?utm_source=x&ref=y"))
    b = clustering.clave_cluster(_item(url="https://example.com/nota-1?pagina=2"))
    assert a == "url:example.com/nota-1"
    assert a == b  # misma nota, distinta query → misma clave


def test_clave_por_titulo_si_no_hay_url():
    k = clustering.clave_cluster(_item(url="", titulo="¡Selección Mexicana golea!"))
    assert k.startswith("t:")
    # Título equivalente (sin signos) colisiona.
    assert k == clustering.clave_cluster(_item(url="", titulo="seleccion mexicana golea"))


def test_clave_vacia_sin_url_ni_titulo():
    assert clustering.clave_cluster({"url": "", "titulo": ""}) == ""


# --------------------------------------------------------------------------- #
# asignar                                                                       #
# --------------------------------------------------------------------------- #


def test_asignar_une_por_misma_url():
    item = _item(url="https://example.com/nota-1?utm_source=tw", titulo="Algo distinto")
    cluster = {"id": "c1", "clave": "url:example.com/nota-1", "titulo": "Titular original"}
    assert clustering.asignar(item, [cluster]) == "c1"


def test_asignar_une_por_titulo_fuzzy():
    cluster = {
        "id": "c2",
        "clave": "t:abc",
        "titulo": "El presidente anuncia una nueva reforma para los estados",
    }
    item = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert clustering.asignar(item, [cluster], umbral=0.82) == "c2"


def test_asignar_cluster_nuevo_si_nada_casa():
    cluster = {"id": "c2", "clave": "t:abc", "titulo": "Reforma energética en el senado"}
    item = _item(url="", titulo="Resultados de la jornada de fútbol del domingo")
    assert clustering.asignar(item, [cluster], umbral=0.82) is None


def test_asignar_respeta_umbral():
    cluster = {"id": "c2", "clave": "t:abc", "titulo": "Gana el equipo local el partido de hoy"}
    item = _item(url="", titulo="Pierde el equipo local el partido de ayer")
    # Con umbral muy alto no une; con uno bajo sí.
    assert clustering.asignar(item, [cluster], umbral=0.99) is None
    assert clustering.asignar(item, [cluster], umbral=0.5) == "c2"


def test_asignar_titulos_muy_cortos_no_entran_fuzzy():
    cluster = {"id": "c2", "clave": "t:nfl", "titulo": "NFL"}
    item = _item(url="", titulo="F1")
    assert clustering.asignar(item, [cluster], umbral=0.3) is None


def test_asignar_gana_el_mas_parecido():
    c_lejos = {"id": "lejos", "clave": "t:1", "titulo": "Reforma fiscal en discusion general"}
    c_cerca = {"id": "cerca", "clave": "t:2", "titulo": "El presidente anuncia nueva reforma estados"}
    item = _item(url="", titulo="El presidente anuncia nueva reforma para los estados")
    assert clustering.asignar(item, [c_lejos, c_cerca], umbral=0.6) == "cerca"


# --------------------------------------------------------------------------- #
# recalcular                                                                    #
# --------------------------------------------------------------------------- #


def _base_cluster():
    return {"id": "c1", "estado": "nuevo", "contenido_id": "", "creado": ""}


def test_recalcular_agrega_fuentes_idiomas_y_senal():
    items = [
        _item(fuente_id="a", idioma="es", senal=100, publicado_en=_T0.isoformat()),
        _item(fuente_id="b", idioma="en", senal=5000, publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="a", idioma="es", senal=10, publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["n_items"] == 3
    assert r["n_fuentes"] == 2  # fuente_id distintos (a, b)
    assert r["idiomas"] == ["en", "es"]
    assert r["senal"] == 5000  # máximo
    assert r["primer_visto"] == _T0.isoformat()
    assert r["ultimo_visto"] == (_T0 + timedelta(hours=2)).isoformat()
    assert r["marca"] == "unotv"


def test_recalcular_titulo_representativo_prefiere_es():
    items = [
        _item(fuente_id="a", idioma="en", senal=9000, titulo="Big news in english today"),
        _item(fuente_id="b", idioma="es", senal=10, titulo="Gran noticia en español hoy"),
    ]
    r = clustering.recalcular(_base_cluster(), items)
    assert r["titulo"] == "Gran noticia en español hoy"


def test_recalcular_breaking_si_muchas_fuentes_en_poco_tiempo():
    items = [
        _item(fuente_id="a", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", publicado_en=(_T0 + timedelta(hours=1)).isoformat()),
        _item(fuente_id="c", publicado_en=(_T0 + timedelta(hours=2)).isoformat()),
    ]
    r = clustering.recalcular(_base_cluster(), items, breaking_fuentes=3, breaking_ventana_h=6)
    assert r["breaking"] == 1


def test_recalcular_no_breaking_si_fuentes_dispersas_en_el_tiempo():
    items = [
        _item(fuente_id="a", publicado_en=_T0.isoformat()),
        _item(fuente_id="b", publicado_en=(_T0 + timedelta(hours=10)).isoformat()),
        _item(fuente_id="c", publicado_en=(_T0 + timedelta(hours=30)).isoformat()),
    ]
    r = clustering.recalcular(_base_cluster(), items, breaking_fuentes=3, breaking_ventana_h=6)
    assert r["breaking"] == 0


def test_recalcular_conserva_identidad_del_cluster():
    base = {"id": "c9", "estado": "usado", "contenido_id": "x123", "creado": "2026-01-01"}
    r = clustering.recalcular(base, [_item(fuente_id="a")])
    assert r["id"] == "c9"
    assert r["estado"] == "usado"
    assert r["contenido_id"] == "x123"
    assert r["creado"] == "2026-01-01"


# --------------------------------------------------------------------------- #
# puntuar (fórmula + monotonía)                                                 #
# --------------------------------------------------------------------------- #


def _cluster(**campos):
    base = {"n_fuentes": 1, "senal": 0, "ultimo_visto": _T0.isoformat(), "breaking": 0, "titulo": "x"}
    base.update(campos)
    return base


def test_puntuar_en_rango_0_1():
    s, razon = clustering.puntuar(_cluster(n_fuentes=6, senal=1_000_000, breaking=1), ahora=_T0)
    assert 0.0 <= s <= 1.0
    assert isinstance(razon, str) and razon


def test_puntuar_monotono_en_corroboracion():
    ahora = _T0 + timedelta(hours=1)
    lo = clustering.puntuar(_cluster(n_fuentes=1), ahora=ahora)[0]
    hi = clustering.puntuar(_cluster(n_fuentes=6), ahora=ahora)[0]
    assert hi > lo


def test_puntuar_monotono_en_frescura():
    ahora = _T0 + timedelta(hours=1)
    fresca = clustering.puntuar(_cluster(ultimo_visto=ahora.isoformat()), ahora=ahora)[0]
    vieja = clustering.puntuar(
        _cluster(ultimo_visto=(ahora - timedelta(hours=60)).isoformat()), ahora=ahora
    )[0]
    assert fresca > vieja


def test_puntuar_monotono_en_viralidad():
    s_baja = clustering.puntuar(_cluster(senal=10), ahora=_T0)[0]
    s_alta = clustering.puntuar(_cluster(senal=500_000), ahora=_T0)[0]
    assert s_alta > s_baja


def test_puntuar_breaking_sube_el_score():
    sin = clustering.puntuar(_cluster(n_fuentes=3, breaking=0), ahora=_T0)[0]
    con = clustering.puntuar(_cluster(n_fuentes=3, breaking=1), ahora=_T0)[0]
    assert con > sin


def test_puntuar_relevancia_de_marca_sube_el_score():
    pal = frozenset({"reforma"})
    sin = clustering.puntuar(_cluster(titulo="Noticia cualquiera"), ahora=_T0)[0]
    con = clustering.puntuar(_cluster(titulo="Aprueban la reforma hoy"), palabras_marca=pal, ahora=_T0)[0]
    assert con > sin


def test_puntuar_pesos_inyectados_cambian_el_score():
    """Pesos inyectados (PesosScore) reemplazan los defaults: el ranking es configurable."""
    cl = _cluster(n_fuentes=6, senal=0, breaking=0, ultimo_visto=_T0.isoformat())
    solo_corro = clustering.PesosScore(
        corroboracion=1.0, frescura=0.0, viralidad=0.0, marca=0.0, breaking=0.0
    )
    todo_cero = clustering.PesosScore(
        corroboracion=0.0, frescura=0.0, viralidad=0.0, marca=0.0, breaking=0.0
    )
    assert clustering.puntuar(cl, ahora=_T0, pesos=solo_corro)[0] > 0.0
    assert clustering.puntuar(cl, ahora=_T0, pesos=todo_cero)[0] == 0.0


# --------------------------------------------------------------------------- #
# Auto-verificación por corroboración (Ola D)                                  #
# --------------------------------------------------------------------------- #


def test_verificacion_corroborada_con_dos_outlets_distintos():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n"),
        _item(fuente_id="b", url="https://medio-b.com/n"),
    ]
    assert clustering.clasificar_verificacion(items) == "corroborada"


def test_verificacion_dos_enlaces_del_mismo_outlet_no_corrobora():
    # Dos urls del MISMO host = una sola fuente real (no corroboración).
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n1"),
        _item(fuente_id="a2", url="https://medio-a.com/n2"),
    ]
    assert clustering.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_unica_fuente_fiable():
    items = [_item(fuente_id="a", url="https://medio-serio.com/n")]
    assert clustering.clasificar_verificacion(items) == "unica_fuente"


def test_verificacion_dudosa_si_unica_fuente_es_de_baja_confianza():
    baja = frozenset({"reddit.com"})
    items = [_item(fuente_id="r", url="https://reddit.com/r/x/post", fuente_nombre="Reddit")]
    assert clustering.clasificar_verificacion(items, fuentes_baja=baja) == "dudosa"


def test_verificacion_dudosa_por_clickbait():
    items = [_item(fuente_id="a", url="https://medio.com/n", titulo="No vas a creer lo que pasó")]
    assert clustering.clasificar_verificacion(items) == "dudosa"


def test_verificacion_corroborada_gana_a_baja_confianza():
    # Aunque una sea de baja confianza, dos outlets distintos = corroborada.
    baja = frozenset({"reddit.com"})
    items = [
        _item(fuente_id="r", url="https://reddit.com/r/x/post"),
        _item(fuente_id="b", url="https://medio-serio.com/n"),
    ]
    assert clustering.clasificar_verificacion(items, fuentes_baja=baja) == "corroborada"


def test_recalcular_fija_verificacion_e_idioma_representativo():
    items = [
        _item(fuente_id="a", url="https://medio-a.com/n", idioma="en", titulo="Foreign headline here"),
        _item(fuente_id="b", url="https://medio-b.com/n", idioma="en", titulo="Foreign headline here"),
    ]
    rec = clustering.recalcular({"id": "c1"}, items)
    assert rec["verificacion"] == "corroborada"
    # idioma del representativo (no hay 'es' -> el de mayor señal/título): inglés.
    assert rec["idioma"] == "en"
    assert "en" in rec["idiomas"]
